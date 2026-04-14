"""
db.py — SQLite database for WhatsApp user management.

Each user is identified by their WhatsApp phone number (e.g. "whatsapp:+919876543210").
The table stores:
  - name, resume_text, parsed_data (JSON), and a conversation state.

User states:
  NEW_USER          → just sent /new, no data yet
  WAITING_FOR_NAME  → we asked for their name
  WAITING_FOR_RESUME→ we asked for their resume text
  READY             → profile complete; can search jobs
"""

import json
import logging
import os
import sqlite3
from datetime import datetime

from config import DATABASE_PATH

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
#  Initialise database and create the `users` table if it doesn't exist
# ---------------------------------------------------------------------------

def _get_connection(db_path: str = DATABASE_PATH) -> sqlite3.Connection:
    """Return a new SQLite connection with row-factory enabled."""
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = DATABASE_PATH):
    """Create the users table if it doesn't exist yet."""
    conn = _get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number TEXT    UNIQUE NOT NULL,
            name         TEXT    DEFAULT '',
            resume_text  TEXT    DEFAULT '',
            parsed_data  TEXT    DEFAULT '{}',
            state        TEXT    DEFAULT 'NEW_USER',
            created_at   TEXT    NOT NULL,
            updated_at   TEXT    NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()
    logger.info("Database initialised at %s", db_path)


# ---------------------------------------------------------------------------
#  CRUD helpers
# ---------------------------------------------------------------------------

def get_user(phone_number: str) -> dict | None:
    """Fetch a user row by phone number.  Returns None if not found."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE phone_number = ?", (phone_number,))
    row = cursor.fetchone()
    conn.close()
    if row is None:
        return None
    user = dict(row)
    # Deserialise the JSON parsed_data field
    try:
        user["parsed_data"] = json.loads(user["parsed_data"])
    except (json.JSONDecodeError, TypeError):
        user["parsed_data"] = {}
    return user


def create_user(phone_number: str, state: str = "WAITING_FOR_NAME") -> dict:
    """Insert a new user and return the row as a dict."""
    now = datetime.utcnow().isoformat()
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO users (phone_number, state, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        """,
        (phone_number, state, now, now),
    )
    conn.commit()
    conn.close()
    logger.info("Created user %s with state %s", phone_number, state)
    return get_user(phone_number)


def update_user_state(phone_number: str, state: str):
    """Update only the conversation state for a user."""
    now = datetime.utcnow().isoformat()
    conn = _get_connection()
    conn.execute(
        "UPDATE users SET state = ?, updated_at = ? WHERE phone_number = ?",
        (state, now, phone_number),
    )
    conn.commit()
    conn.close()
    logger.info("User %s state → %s", phone_number, state)


def update_user_name(phone_number: str, name: str):
    """Store the user's name and advance state to WAITING_FOR_RESUME."""
    now = datetime.utcnow().isoformat()
    conn = _get_connection()
    conn.execute(
        "UPDATE users SET name = ?, state = 'WAITING_FOR_RESUME', updated_at = ? WHERE phone_number = ?",
        (name.strip(), now, phone_number),
    )
    conn.commit()
    conn.close()
    logger.info("User %s name set to '%s'", phone_number, name.strip())


def update_user_resume(phone_number: str, resume_text: str, parsed_data: dict):
    """Store resume text + parsed JSON and set state to READY."""
    now = datetime.utcnow().isoformat()
    conn = _get_connection()
    conn.execute(
        """
        UPDATE users
        SET resume_text  = ?,
            parsed_data  = ?,
            state        = 'READY',
            updated_at   = ?
        WHERE phone_number = ?
        """,
        (resume_text.strip(), json.dumps(parsed_data), now, phone_number),
    )
    conn.commit()
    conn.close()
    logger.info("User %s resume stored (%d chars), state → READY", phone_number, len(resume_text))


def delete_user(phone_number: str):
    """Remove a user entirely (useful for /reset)."""
    conn = _get_connection()
    conn.execute("DELETE FROM users WHERE phone_number = ?", (phone_number,))
    conn.commit()
    conn.close()
    logger.info("Deleted user %s", phone_number)
