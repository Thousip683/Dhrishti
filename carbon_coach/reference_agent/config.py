"""Central configuration sourced from environment variables.

Load once at import time via python-dotenv. Values may be overridden by the
FastAPI application before importing CarbonCoachService by setting the
corresponding env-vars before the first import.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Resolve the .env file that lives next to this file (carbon_coach/.env).
_env_file = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=_env_file, override=False)

# ── Gemini ────────────────────────────────────────────────────────────────────
GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
GOOGLE_GENAI_USE_VERTEXAI: bool = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "FALSE").upper() == "TRUE"
GEMINI_MODEL: str = os.getenv("CARBON_GEMINI_MODEL", "gemini-2.5-flash")

# ── Storage ───────────────────────────────────────────────────────────────────
# Absolute path to the SQLite database file.  In Cloud Run, set this to a path
# on a mounted Filestore volume or leave empty and use a managed DB instead.
CARBON_DB_PATH: str = os.getenv(
    "CARBON_DB_PATH",
    str(Path(__file__).resolve().parent.parent / "carbon_activities.sqlite3"),
)

# ── Campus analytics ─────────────────────────────────────────────────────────
# Minimum number of opted-in participants required to publish a group aggregate.
CAMPUS_MIN_GROUP_SIZE: int = int(os.getenv("CAMPUS_MIN_GROUP_SIZE", "3"))

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("CARBON_LOG_LEVEL", "INFO")
