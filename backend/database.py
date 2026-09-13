import sqlite3
from backend.config import settings


def get_db_connection():
    #Create and return a SQLite database connection
    conn = sqlite3.connect(settings.DB_PATH)

    # Enable foreign key
    conn.execute("PRAGMA foreign_keys = ON")

    # Allow rows to be accessed like dictionaries
    conn.row_factory = sqlite3.Row

    return conn


def init_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Conversations - stores voice query and response history
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                user_query TEXT NOT NULL,
                ai_response TEXT NOT NULL,
                intent TEXT DEFAULT 'general',
                latency_ms REAL DEFAULT 0.0
            )
        """)

        # Caregiver feedback - stores ratings and notes for evaluation
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
                caregiver_notes TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id)
                    REFERENCES conversations (id)
                    ON DELETE CASCADE
            )
        """)

        # Child profile - stores profile settings such as age group and care notes
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS child_profile (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_key TEXT UNIQUE NOT NULL,
                profile_value TEXT NOT NULL
            )
        """)

        # Index for faster feedback lookups by conversation
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_feedback_conversation_id
            ON feedback (conversation_id)
        """)

    print("Database initialized successfully at:", settings.DB_PATH)


if __name__ == "__main__":
    init_db()
