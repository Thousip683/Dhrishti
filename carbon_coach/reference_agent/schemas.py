"""Pydantic schemas for public API payloads exchanged with FastAPI.

All classes here are plain data models — no ADK or SQLite dependencies.
They are the serialisation boundary between internal agent logic and the
FastAPI layer.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ── Emission calculation result ───────────────────────────────────────────────

class EmissionResult(BaseModel):
    """Output of any single deterministic carbon calculation."""
    category: str
    factor_id: str
    quantity: float
    factor_value: float
    factor_unit: str
    emissions_kg: float
    emissions_unit: str  # "kg CO2" or "kg CO2e"
    geography: str
    version: str
    boundary: str
    source: str


# ── Activity record ───────────────────────────────────────────────────────────

class ActivityRecord(BaseModel):
    """A single logged activity as stored in (and returned from) the ledger."""
    activity_id: str
    created_at: str  # ISO-8601 UTC
    calculation: EmissionResult


# ── Summary ───────────────────────────────────────────────────────────────────

class SummaryTotal(BaseModel):
    emissions_unit: str
    boundary: str
    emissions_kg: float


class ActivitySummary(BaseModel):
    period: str
    activity_count: int
    totals: list[SummaryTotal]
    note: str


# ── Recommendation ────────────────────────────────────────────────────────────

class Recommendation(BaseModel):
    title: str
    explanation: str
    estimated_saving_kg: float | None = None
    emissions_unit: str | None = None
    time_period: str | None = None
    factor_ids: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    confidence: str = "low"       # "high" | "medium" | "low"
    verified_by_tool: bool = False


# ── Campus analytics ─────────────────────────────────────────────────────────

class GroupEmissions(BaseModel):
    group_id: str
    group_type: str            # "department" | "hostel" | "campus"
    participant_count: int
    total_emissions_kg: float
    emissions_unit: str
    boundary: str
    period: str
    privacy_suppressed: bool = False
    note: str = ""


class CampusSummary(BaseModel):
    campus_id: str
    period: str
    total_opted_in_users: int
    total_emissions_kg: float
    emissions_unit: str
    boundary: str
    groups: list[GroupEmissions]
    note: str


# ── Chat I/O ──────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: str
    user_id: str
    language: str = "en"


class ChatResponse(BaseModel):
    session_id: str
    user_id: str
    reply: str
    tool_calls_made: list[str] = Field(default_factory=list)
    raw_events: list[dict[str, Any]] = Field(default_factory=list)
