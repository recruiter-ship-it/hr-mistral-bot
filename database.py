"""
Database helpers for the HR Mistral bot.

This module wraps simple SQLite operations used by the bot to persist
user configuration (Google calendar tokens and timezones) as well as
conversation history. Persisting chat history across sessions allows the
assistant to provide more coherent responses by leveraging previous
dialogue turns as context for future interactions.

When the module is imported, no tables are created until `init_db()` is
called. This gives callers control over when to initialize the database.
"""

import sqlite3
import json
from datetime import datetime

# Default path for the SQLite database file. This file will be created
# relative to the working directory where the bot is started.
DB_PATH = "bot_data.db"


def init_db() -> None:
    """
    Initialize the SQLite database. This will create two tables if they do not
    already exist:

    - `users`: stores the Google calendar token (or Gmail address) and the user's
       timezone. The `user_id` column is the primary key.
    - `conversations`: stores the chat history for each user. Each row records
       who (user or assistant) said what and when. Keeping chat history in the
       database allows the bot to recall previous exchanges across sessions,
       improving context and memory.

    The `timestamp` column is stored as text in ISO 8601 format.
    """
    with sqlite3.connect(DB_PATH) as conn:
        # Create users table for storing calendar tokens and timezone
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                google_token TEXT,
                timezone TEXT DEFAULT 'UTC'
            )
            """
        )

        # Create conversations table for storing chat history
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
            """
        )
        conn.commit()


def save_token(user_id: int, token_data) -> None:
    """
    Save or update the Google calendar token (or Gmail address) for a user.

    The `token_data` can either be a string (in which case it is stored as
    is) or any other Python object. Non-string objects are serialized to
    JSON. This makes the function flexible enough to store the Gmail
    address directly or the OAuth token dictionary for the legacy version of
    the bot.

    :param user_id: Telegram user ID.
    :param token_data: String or dictionary to store.
    """
    with sqlite3.connect(DB_PATH) as conn:
        # If token_data is a string (Gmail), save as is; otherwise, convert to JSON
        val = token_data if isinstance(token_data, str) else json.dumps(token_data)
        conn.execute(
            "INSERT OR REPLACE INTO users (user_id, google_token) VALUES (?, ?)",
            (user_id, val),
        )
        conn.commit()


def get_token(user_id: int):
    """
    Retrieve the stored token or Gmail address for a user. If no token is
    stored, returns `None`. If the stored value is valid JSON, it will
    automatically be deserialized back into a Python object.

    :param user_id: Telegram user ID.
    :return: A string, a dict, or `None` if nothing is stored.
    """
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            "SELECT google_token FROM users WHERE user_id = ?", (user_id,)
        )
        row = cursor.fetchone()
        if not row or not row[0]:
            return None
        try:
            return json.loads(row[0])
        except Exception:
            return row[0]


def delete_token(user_id: int) -> None:
    """
    Delete the stored token or Gmail address for a user.

    :param user_id: Telegram user ID.
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE users SET google_token = NULL WHERE user_id = ?", (user_id,),
        )
        conn.commit()


# -----------------------------------------------------------------------------
# Conversation history helpers
#
# These helper functions manage the chat history stored in the `conversations`
# table. Storing chat history in a database allows the bot to remember past
# conversations, improving context and enabling a more coherent dialogue over
# multiple interactions.


def add_conversation(user_id: int, role: str, content: str, timestamp: str = None) -> None:
    """
    Persist a single message in the conversation history.

    :param user_id: Telegram user ID.
    :param role: "user" or "assistant" to indicate who sent the message.
    :param content: The text content of the message.
    :param timestamp: Optional ISO timestamp. If omitted, the current UTC time
                      will be used.
    """
    if timestamp is None:
        timestamp = datetime.utcnow().isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO conversations (user_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            (user_id, role, content, timestamp),
        )
        conn.commit()


def get_conversation(user_id: int, limit: int = 10):
    """
    Retrieve the most recent chat history for a user.

    :param user_id: Telegram user ID.
    :param limit: Maximum number of conversation entries to return.
    :return: A list of dictionaries with keys: role, content, timestamp.
    """
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            "SELECT role, content, timestamp FROM conversations WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        )
        rows = cursor.fetchall()
        # Reverse to return chronological order (oldest first)
        rows.reverse()
        history = [
            {"role": row[0], "content": row[1], "timestamp": row[2]} for row in rows
        ]
        return history
