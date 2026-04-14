"""
config.py — Central configuration for the WhatsApp AI Job Agent.

All secrets and tunables are read from environment variables with sensible defaults.
"""

import os


def _get_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _get_float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


# ---------------------------------------------------------------------------
#  Twilio WhatsApp settings
# ---------------------------------------------------------------------------
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
# Must be in the format "whatsapp:+14155238886" (Twilio Sandbox number)
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER", "").strip()

# ---------------------------------------------------------------------------
#  Adzuna API credentials
# ---------------------------------------------------------------------------
ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID", "").strip()
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY", "").strip()
ADZUNA_COUNTRY_CODE = os.getenv("ADZUNA_COUNTRY_CODE", "in").strip().lower()

# ---------------------------------------------------------------------------
#  Job search defaults
# ---------------------------------------------------------------------------
JOB_ROLE_QUERY = os.getenv("JOB_ROLE_QUERY", "").strip()
JOB_LOCATION_QUERY = os.getenv("JOB_LOCATION_QUERY", "").strip()
MAX_ADZUNA_PAGES = _get_int("MAX_ADZUNA_PAGES", 3)
RESULTS_PER_PAGE = _get_int("RESULTS_PER_PAGE", 20)
DEFAULT_FALLBACK_CSV = os.getenv("DEFAULT_FALLBACK_CSV", "").strip()

# ---------------------------------------------------------------------------
#  Skill keywords (used by matcher.py)
# ---------------------------------------------------------------------------
SKILL_KEYWORDS = [
    "python",
    "machine learning",
    "deep learning",
    "nlp",
    "natural language processing",
    "computer vision",
    "data science",
    "pytorch",
    "tensorflow",
    "transformers",
    "scikit-learn",
    "sql",
    "cloud",
    "aws",
    "azure",
    "gcp",
    "model deployment",
    "recommendation",
    "ai",
    "ml",
    "llm",
    "data engineering",
]

# ---------------------------------------------------------------------------
#  Scoring weights
# ---------------------------------------------------------------------------
KEYWORD_WEIGHT = _get_float("KEYWORD_WEIGHT", 0.40)
SEMANTIC_WEIGHT = _get_float("SEMANTIC_WEIGHT", 0.60)
MINIMUM_SCORE = _get_float("MINIMUM_SCORE", 0.30)

# ---------------------------------------------------------------------------
#  Database
# ---------------------------------------------------------------------------
DATABASE_PATH = os.getenv("DATABASE_PATH", "whatsapp_job_agent.db").strip()

# ---------------------------------------------------------------------------
#  LLM settings (optional — set GROQ_API_KEY to enable LLM-powered parsing)
# ---------------------------------------------------------------------------
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()

# ---------------------------------------------------------------------------
#  App settings
# ---------------------------------------------------------------------------
MAX_WHATSAPP_MESSAGE_LENGTH = 1500  # WhatsApp has ~1600 char limit; keep some buffer
TOP_JOBS_TO_RETURN = _get_int("TOP_JOBS_TO_RETURN", 5)
MAX_RESUME_LENGTH = _get_int("MAX_RESUME_LENGTH", 50000)  # ~8000 words
