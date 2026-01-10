import sqlite3
import os
from datetime import datetime

# Database file path - stored in the db folder
DB_PATH = os.path.join(os.path.dirname(__file__), "reminders.db")


def get_connection():
    """Get a database connection."""
    return sqlite3.connect(DB_PATH)


def init_db():
    """Initialize the database and create the reminders table if it doesn't exist."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_user_id INTEGER NOT NULL,
            reminder_text TEXT NOT NULL,
            reminder_time TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            telegram_user_id INTEGER PRIMARY KEY,
            timezone TEXT DEFAULT 'UTC'
        )
    """)
    
    conn.commit()
    conn.close()
    print("✅ Database initialized successfully!")


def add_reminder(telegram_user_id: int, reminder_text: str, reminder_time: str) -> int:
    """
    Add a new reminder to the database.
    
    Args:
        telegram_user_id: The Telegram user ID
        reminder_text: The reminder message
        reminder_time: The time for the reminder (HH:MM format)
    
    Returns:
        The ID of the newly created reminder
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        """
        INSERT INTO reminders (telegram_user_id, reminder_text, reminder_time)
        VALUES (?, ?, ?)
        """,
        (telegram_user_id, reminder_text, reminder_time)
    )
    
    reminder_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    print(f"💾 Reminder saved: ID={reminder_id}, User={telegram_user_id}, Text='{reminder_text}', Time={reminder_time}")
    return reminder_id


def get_reminders(telegram_user_id: int) -> list:
    """
    Get all reminders for a specific user.
    
    Args:
        telegram_user_id: The Telegram user ID
    
    Returns:
        A list of tuples containing (id, reminder_text, reminder_time, created_at)
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        """
        SELECT id, reminder_text, reminder_time, created_at
        FROM reminders
        WHERE telegram_user_id = ?
        ORDER BY created_at DESC
        """,
        (telegram_user_id,)
    )
    
    reminders = cursor.fetchall()
    conn.close()
    
    return reminders


def delete_reminder(reminder_id: int, telegram_user_id: int) -> bool:
    """
    Delete a reminder by its ID, ensuring it belongs to the user.
    
    Args:
        reminder_id: The ID of the reminder to delete
        telegram_user_id: The Telegram user ID (for ownership verification)
    
    Returns:
        True if the reminder was deleted, False otherwise
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "DELETE FROM reminders WHERE id = ? AND telegram_user_id = ?",
        (reminder_id, telegram_user_id)
    )
    
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    
    if deleted:
        print(f"🗑️ Reminder deleted: ID={reminder_id}, User={telegram_user_id}")
    
    return deleted


def delete_all_reminders(telegram_user_id: int) -> int:
    """
    Delete all reminders for a specific user.
    
    Args:
        telegram_user_id: The Telegram user ID
    
    Returns:
        The number of reminders deleted
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "DELETE FROM reminders WHERE telegram_user_id = ?",
        (telegram_user_id,)
    )
    
    count = cursor.rowcount
    conn.commit()
    conn.close()
    
    print(f"🗑️ Deleted {count} reminder(s) for User={telegram_user_id}")
    return count


def get_due_reminders(current_time: str) -> list:
    """
    Get all reminders that are due at the specified time.
    
    Args:
        current_time: The current time in HH:MM format
    
    Returns:
        A list of tuples containing (id, telegram_user_id, reminder_text, reminder_time)
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        """
        SELECT id, telegram_user_id, reminder_text, reminder_time
        FROM reminders
        WHERE reminder_time = ?
        """,
        (current_time,)
    )
    
    reminders = cursor.fetchall()
    conn.close()
    
    return reminders


def set_user_timezone(telegram_user_id: int, timezone: str) -> None:
    """
    Set or update a user's timezone.
    
    Args:
        telegram_user_id: The Telegram user ID
        timezone: The timezone string (e.g., 'Asia/Kolkata', 'UTC')
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        """
        INSERT OR REPLACE INTO user_settings (telegram_user_id, timezone)
        VALUES (?, ?)
        """,
        (telegram_user_id, timezone)
    )
    
    conn.commit()
    conn.close()
    print(f"🌍 Timezone set: User={telegram_user_id}, Timezone={timezone}")


def get_user_timezone(telegram_user_id: int) -> str:
    """
    Get a user's timezone setting.
    
    Args:
        telegram_user_id: The Telegram user ID
    
    Returns:
        The user's timezone string, or 'UTC' if not set
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT timezone FROM user_settings WHERE telegram_user_id = ?",
        (telegram_user_id,)
    )
    
    result = cursor.fetchone()
    conn.close()
    
    return result[0] if result else 'UTC'


def get_all_reminders_with_timezone() -> list:
    """
    Get all reminders with their user's timezone.
    
    Returns:
        A list of tuples: (id, telegram_user_id, reminder_text, reminder_time, timezone)
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        """
        SELECT r.id, r.telegram_user_id, r.reminder_text, r.reminder_time,
               COALESCE(u.timezone, 'UTC') as timezone
        FROM reminders r
        LEFT JOIN user_settings u ON r.telegram_user_id = u.telegram_user_id
        """
    )
    
    reminders = cursor.fetchall()
    conn.close()
    
    return reminders
