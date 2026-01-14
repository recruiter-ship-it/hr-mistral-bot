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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                role TEXT,
                content TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

def save_message(user_id, role, content):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO history (user_id, role, content) VALUES (?, ?, ?)",
            (user_id, role, content)
        )
        # Ограничиваем историю последними 20 сообщениями на пользователя
        conn.execute("""
            DELETE FROM history WHERE id IN (
                SELECT id FROM history WHERE user_id = ? 
                ORDER BY timestamp DESC LIMIT -1 OFFSET 20
            )
        """, (user_id,))
        conn.commit()

def get_history(user_id, limit=10):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            "SELECT role, content FROM history WHERE user_id = ? ORDER BY timestamp ASC LIMIT ?",
            (user_id, limit)
        )
        return [{"role": row[0], "content": row[1]} for row in cursor.fetchall()]

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
