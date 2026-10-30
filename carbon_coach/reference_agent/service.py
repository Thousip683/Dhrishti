"""CarbonCoachService — Python integration interface for FastAPI.

This module is the ONLY entry point the FastAPI teammate needs to import.
It wraps the Google ADK Runner and exposes async/sync methods for:
  - Conversational chat (via the ADK multi-agent pipeline)
  - Activity retrieval
  - Emission summaries
  - Personalised recommendations
  - Campus analytics

IMPORTANT DESIGN NOTES:
  - No global mutable state: each service instance owns its session service.
  - session_id must be managed by the caller (FastAPI generates + persists it).
  - user_id must be a pre-authenticated identity from FastAPI auth middleware.
  - The service never treats an arbitrary string as a trusted authenticated user.
  - All returned values are plain Python dicts — no ADK internal objects leak out.
  - Thread-safe: async methods use asyncio; sync wrappers provided for convenience.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from dotenv import load_dotenv
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types

# Load .env before importing agent (which reads CARBON_GEMINI_MODEL)
load_dotenv(
    dotenv_path=os.path.join(os.path.dirname(__file__), ".env"),
    override=False,
)

from .activity_tracker import (
    get_summary_data,
    get_summary_data_by_user,
    list_activities,
    list_activities_by_user,
)
from .campus_analytics import (
    get_campus_summary,
    get_department_comparison,
    get_hostel_leaderboard,
)
from .recommendations import get_recommendations

logger = logging.getLogger(__name__)


class CarbonCoachService:
    """High-level service wrapping the ADK multi-agent system.

    Lifecycle:
        service = CarbonCoachService()            # default InMemory sessions
        await service.start()                     # optional — no-op for InMemory
        response = await service.chat(...)
        await service.stop()                      # optional cleanup

    Dependency injection:
        service = CarbonCoachService(
            session_service=my_persistent_session_service,
        )

    The FastAPI lifespan pattern:
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            service = CarbonCoachService()
            await service.start()
            app.state.carbon_service = service
            yield
            await service.stop()
    """

    APP_NAME = "carbon_coach"

    def __init__(
        self,
        session_service=None,
        model: str | None = None,
    ) -> None:
        """Initialise the service.

        Args:
            session_service: An ADK BaseSessionService instance.
                             Defaults to InMemorySessionService (development only).
                             For production provide a persistent session service.
            model:           Override the Gemini model name.
                             Defaults to CARBON_GEMINI_MODEL env var → 'gemini-2.5-flash'.
        """
        if model:
            os.environ.setdefault("CARBON_GEMINI_MODEL", model)

        self._session_service = session_service or InMemorySessionService()

        # Import agent here so that env-vars are set before Agent() is constructed
        from .agent import root_agent  # noqa: PLC0415
        self._agent = root_agent

        self._runner = Runner(
            app_name=self.APP_NAME,
            agent=self._agent,
            session_service=self._session_service,
            auto_create_session=True,
        )
        logger.info(
            "CarbonCoachService initialised (model=%s, session_service=%s)",
            os.getenv("CARBON_GEMINI_MODEL", "gemini-2.5-flash"),
            type(self._session_service).__name__,
        )

    async def start(self) -> None:
        """Optional startup hook (no-op for InMemorySessionService)."""
        logger.info("CarbonCoachService started")

    async def stop(self) -> None:
        """Shutdown: close the ADK runner if it supports it."""
        try:
            await self._runner.close()
        except Exception:  # Runner.close may not exist in all versions
            pass
        logger.info("CarbonCoachService stopped")

    # ── Session management ────────────────────────────────────────────────────

    def ensure_session(self, user_id: str, session_id: str) -> str:
        """Create the ADK session if it does not already exist.

        Returns the session_id (unchanged).
        """
        try:
            self._session_service.get_session(
                app_name=self.APP_NAME,
                user_id=user_id,
                session_id=session_id,
            )
        except Exception:
            self._session_service.create_session(
                app_name=self.APP_NAME,
                user_id=user_id,
                session_id=session_id,
            )
        return session_id

    # ── Core chat ─────────────────────────────────────────────────────────────

    async def chat(
        self,
        message: str,
        session_id: str,
        user_id: str,
        language: str = "en",
    ) -> dict[str, Any]:
        """Send a message through the ADK agent pipeline and return the reply.

        Args:
            message:    The user's natural-language message.
            session_id: Caller-managed session identifier (persist across turns).
            user_id:    Pre-authenticated user identity from FastAPI auth middleware.
            language:   ISO language code hint ('en', 'te', 'hi').

        Returns:
            dict with keys:
              - session_id: str
              - user_id: str
              - reply: str  (the agent's final text response)
              - tool_calls_made: list[str]
              - raw_events: list[dict]  (serialised ADK events, for debugging)

        Raises:
            ValueError: if message or session_id is blank.
            RuntimeError: if the ADK runner encounters an unrecoverable error.
        """
        if not message or not message.strip():
            raise ValueError("message must be non-empty")
        if not session_id:
            raise ValueError("session_id is required")

        # Prepend a language hint so the agent responds in the right language
        lang_hints = {"te": "Telugu", "hi": "Hindi", "en": "English"}
        lang_name = lang_hints.get(language, "English")
        full_message = (
            f"[Language: {lang_name}] {message}"
            if language != "en"
            else message
        )

        new_message = genai_types.Content(
            role="user",
            parts=[genai_types.Part.from_text(text=full_message)],
        )

        reply_parts: list[str] = []
        tool_calls_made: list[str] = []
        raw_events: list[dict] = []

        try:
            async for event in self._runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=new_message,
            ):
                # Collect tool call names for the caller
                fn_calls = event.get_function_calls() or []
                for fc in fn_calls:
                    tool_calls_made.append(getattr(fc, "name", str(fc)))

                # Collect final agent reply text
                if event.is_final_response():
                    msg = event.message
                    if msg and hasattr(msg, "parts") and msg.parts:
                        for part in msg.parts:
                            text = getattr(part, "text", None)
                            if text:
                                reply_parts.append(text)

                # Serialise event for debug output (skip large binary fields)
                try:
                    raw_events.append(event.model_dump(exclude_none=True))
                except Exception:
                    raw_events.append({"event_type": type(event).__name__})

        except Exception as exc:
            logger.exception("ADK runner error for session=%s user=%s", session_id, user_id)
            raise RuntimeError(f"Agent pipeline error: {exc}") from exc

        reply = "\n".join(reply_parts).strip() or "(No response)"

        return {
            "session_id": session_id,
            "user_id": user_id,
            "reply": reply,
            "tool_calls_made": tool_calls_made,
            "raw_events": raw_events,
        }

    def chat_sync(
        self,
        message: str,
        session_id: str,
        user_id: str,
        language: str = "en",
    ) -> dict[str, Any]:
        """Synchronous wrapper around chat() for non-async callers."""
        return asyncio.run(
            self.chat(message, session_id, user_id, language)
        )

    # ── Activity data ─────────────────────────────────────────────────────────

    def get_activities(
        self,
        user_id: str,
        session_id: str | None = None,
        period: str = "all",
    ) -> list[dict]:
        """Return activity records for a user (or session).

        If session_id is provided, returns only that session's records.
        Otherwise, returns all cross-session records for the user.

        Args:
            user_id:    Pre-authenticated user identity.
            session_id: Optional ADK session identifier.
            period:     'today' | 'week' | 'month' | 'all'.
        """
        if session_id:
            return list_activities(session_id, period)
        return list_activities_by_user(user_id, period)

    def get_summary(
        self,
        user_id: str,
        period: str = "week",
        session_id: str | None = None,
    ) -> dict:
        """Return aggregated emission totals for a user or session.

        Args:
            user_id:    Pre-authenticated user identity.
            period:     'today' | 'week' | 'month' | 'all'.
            session_id: If provided, restricts summary to this session only.
        """
        if session_id:
            return get_summary_data(session_id, period)
        return get_summary_data_by_user(user_id, period)

    def get_recommendations(
        self,
        user_id: str,
        session_id: str | None = None,
        period: str = "week",
    ) -> list[dict]:
        """Return personalised emission-reduction recommendations.

        Args:
            user_id:    Pre-authenticated user identity.
            session_id: Optional; restricts analysis to this session.
            period:     Lookback window — 'today' | 'week' | 'month' | 'all'.
        """
        return get_recommendations(
            user_id=user_id if not session_id else None,
            session_id=session_id,
            period=period,
        )

    # ── Campus analytics ───────────────────────────────────────────────────────

    def get_campus_leaderboard(
        self,
        campus_id: str,
        hostels: list[str],
        period: str = "week",
    ) -> dict:
        """Return a privacy-aware hostel leaderboard for the given campus.

        Groups with fewer than CAMPUS_MIN_GROUP_SIZE opted-in participants
        are excluded from rankings.

        Args:
            campus_id: Campus identifier (e.g. "IIT_Hyderabad").
            hostels:   List of hostel sub-group names.
            period:    'today' | 'week' | 'month' | 'all'.
        """
        return get_hostel_leaderboard(campus_id, hostels, period)

    def get_campus_summary(
        self,
        campus_id: str,
        period: str = "week",
    ) -> dict:
        """Return aggregated campus-level opted-in emissions summary."""
        return get_campus_summary(campus_id, period)

    def get_department_comparison(
        self,
        campus_id: str,
        departments: list[str],
        period: str = "week",
    ) -> list[dict]:
        """Return per-department emission aggregates, privacy-suppressed."""
        return get_department_comparison(campus_id, departments, period)
