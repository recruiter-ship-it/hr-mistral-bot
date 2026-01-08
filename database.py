import sqlite3
import json

class Database:
    def __init__(self, db_path="bot_data.db"):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    google_token TEXT,
                    timezone TEXT DEFAULT 'UTC'
                )
            """)
            conn.commit()

    def save_token(self, user_id, token_data):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO users (user_id, google_token) VALUES (?, ?)",
                (user_id, json.dumps(token_data))
            )
            conn.commit()

    def get_token(self, user_id):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT google_token FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return json.loads(row[0]) if row and row[0] else None

    def delete_token(self, user_id):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE users SET google_token = NULL WHERE user_id = ?", (user_id,))
            conn.commit()
