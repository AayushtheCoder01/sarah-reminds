import sqlite3

conn = sqlite3.connect('db/reminders.db')
cursor = conn.cursor()

# Set timezone for user
cursor.execute(
    "INSERT OR REPLACE INTO user_settings (telegram_user_id, timezone) VALUES (?, ?)",
    (5366960721, 'Asia/Kolkata')
)

conn.commit()
print("✅ Timezone set to Asia/Kolkata for user 5366960721")

# Show current state
cursor.execute("SELECT * FROM user_settings")
print("User Settings:", cursor.fetchall())

cursor.execute("SELECT * FROM reminders")
print("Reminders:", cursor.fetchall())

conn.close()
