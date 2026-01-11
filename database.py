import sqlite3
import json

DB_PATH = "bot_data.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                google_token TEXT,
                timezone TEXT DEFAULT 'UTC'
            )
        """)
        conn.commit()

def save_token(user_id, token_data):
    with sqlite3.connect(DB_PATH) as conn:
        # Если token_data это строка (Gmail), сохраняем как есть, если нет - в JSON
        val = token_data if isinstance(token_data, str) else json.dumps(token_data)
        conn.execute(
            "INSERT OR REPLACE INTO users (user_id, google_token) VALUES (?, ?)",
            (user_id, val)
        )
        conn.commit()

def get_token(user_id):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute("SELECT google_token FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if not row or not row[0]:
            return None
        try:
            return json.loads(row[0])
        except:
            return row[0]

def delete_token(user_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE users SET google_token = NULL WHERE user_id = ?", (user_id,))
        conn.commit()
