from dotenv import load_dotenv
import os
import asyncio
from datetime import datetime, timedelta
import pytz

from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    ConversationHandler,
    CallbackQueryHandler,
)

# Import database module
from db import (
    init_db, add_reminder, get_reminders, delete_reminder, delete_all_reminders,
    get_due_reminders, set_user_timezone, get_user_timezone, get_all_reminders_with_timezone
)

load_dotenv()

# --- Config ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME", )  # fallback

# --- States ---
WAITING_REMINDER = 1
WAITING_TIME = 2

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_tz = get_user_timezone(user_id)
    
    # If timezone not set, prompt user to set it
    if user_tz == 'UTC':  # Default means not set
        await show_timezone_selection(update, context, "Welcome! Please select your timezone to get started:")
    else:
        await update.message.reply_text(
            f"Hello! I am {BOT_USERNAME}, your reminder bot.\n\nYour timezone: {user_tz}"
        )


async def add_reminder_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    user_tz = get_user_timezone(user_id)
    
    # If timezone not set, prompt user to set it first
    if user_tz == 'UTC':  # Default means not set
        context.user_data['pending_action'] = 'add_reminder'
        await show_timezone_selection(update, context, "🌍 Please select your timezone first:")
        return ConversationHandler.END
    
    await update.message.reply_text("📝 What should I remind you about?")
    return WAITING_REMINDER


async def receive_reminder_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_text = update.message.text
    context.user_data['reminder_text'] = user_text
    
    # Get user's timezone to calculate times in their local time
    user_id = update.effective_user.id
    user_tz = get_user_timezone(user_id)
    tz = pytz.timezone(user_tz)
    now = datetime.now(tz)
    
    # Calculate dynamic times
    time_15min = (now + timedelta(minutes=15)).strftime("%H:%M")
    time_30min = (now + timedelta(minutes=30)).strftime("%H:%M")
    time_1hr = (now + timedelta(hours=1)).strftime("%H:%M")
    time_2hr = (now + timedelta(hours=2)).strftime("%H:%M")
    
    # Build keyboard with dynamic and fixed times
    reply_keyboard = [
        [f"⏱️ {time_15min} (15 min)", f"⏰ {time_30min} (30 min)"],
        [f"🕐 {time_1hr} (1 hour)", f"🕑 {time_2hr} (2 hours)"],
        ["🌅 09:00 AM", "🌇 12:00 PM"],
        ["🌆 06:00 PM", "🌃 09:00 PM"]
    ]
    
    await update.message.reply_text(
        f"✅ Got it! \"*{user_text}*\"\n\n⏰ When should I remind you?",
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, one_time_keyboard=True, input_field_placeholder="Select or type HH:MM"
        ),
    )
    return WAITING_TIME


async def receive_reminder_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    time_text = update.message.text
    
    # Extract just the time if user selected a button with label (e.g., "⏱️ 14:30 (15 min)")
    if '(' in time_text:
        # Extract HH:MM from "⏱️ 14:30 (15 min)" format
        time_text = time_text.split('(')[0].strip().split()[-1]
    
    reminder_text = context.user_data.get('reminder_text', 'No text')
    telegram_user_id = update.effective_user.id
    
    # Save reminder to database
    add_reminder(telegram_user_id, reminder_text, time_text)
    
    print(f"User Reminder: {reminder_text} at {time_text}")
    
    await update.message.reply_text(f"✅ Reminder saved! I'll remind you:\n\n📝 *{reminder_text}*\n⏰ at *{time_text}*")
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show available commands."""
    help_text = (
        "📋 **Available Commands:**\n\n"
        "/start - Start the bot\n"
        "/addreminder - Add a new reminder\n"
        "/reminders - View all your reminders\n"
        "/settimezone - Set your timezone\n"
        "/clear - Delete all reminders\n"
        "/help - Show this help message\n"
        "/cancel - Cancel current operation"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def list_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all reminders for the user with delete buttons."""
    user_id = update.effective_user.id
    reminders = get_reminders(user_id)
    
    if not reminders:
        await update.message.reply_text("📭 You have no reminders.")
        return
    
    message = "📝 **Your Reminders:**\n\n"
    
    for reminder in reminders:
        reminder_id, text, time, created_at = reminder
        message += f"• {text} at {time}\n"
        
        # Create inline keyboard with delete button for each reminder
        keyboard = [[InlineKeyboardButton("🗑️ Delete", callback_data=f"delete_{reminder_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"📌 {text} - {time}",
            reply_markup=reply_markup
        )


async def clear_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ask for confirmation before deleting all reminders."""
    keyboard = [
        [
            InlineKeyboardButton("✅ Yes, delete all", callback_data="clear_confirm"),
            InlineKeyboardButton("❌ Cancel", callback_data="clear_cancel")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "⚠️ Are you sure you want to delete ALL reminders?",
        reply_markup=reply_markup
    )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button clicks."""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    data = query.data
    
    if data.startswith("delete_"):
        # Delete specific reminder
        reminder_id = int(data.split("_")[1])
        success = delete_reminder(reminder_id, user_id)
        
        if success:
            await query.edit_message_text("✅ Reminder deleted!")
        else:
            await query.edit_message_text("❌ Reminder not found or already deleted.")
    
    elif data == "clear_confirm":
        # Delete all reminders
        count = delete_all_reminders(user_id)
        await query.edit_message_text(f"✅ Deleted {count} reminder(s)!")
    
    elif data == "clear_cancel":
        await query.edit_message_text("❌ Cancelled. Your reminders are safe.")
    
    elif data.startswith("tz_"):
        # Set user timezone
        timezone = data[3:]  # Remove 'tz_' prefix
        set_user_timezone(user_id, timezone)
        
        # Check if there's a pending action
        pending_action = context.user_data.get('pending_action')
        
        if pending_action == 'add_reminder':
            # Clear pending action
            context.user_data.pop('pending_action', None)
            await query.edit_message_text(f"✅ Timezone set to: {timezone}\n\nNow, what should I remind you about?")
            # Note: User will need to send /addreminder again, but timezone is now set
        else:
            await query.edit_message_text(f"🌍 Timezone set to: {timezone}")
    
    elif data.startswith("done_"):
        # Mark reminder as done
        reminder_id = int(data.split("_")[1])
        success = delete_reminder(reminder_id, user_id)
        
        if success:
            await query.edit_message_text(f"{query.message.text}\n\n✅ **Marked as done!**")
        else:
            await query.edit_message_text(f"{query.message.text}\n\n❌ Already completed.")
    
    elif data.startswith("snooze30_") or data.startswith("snooze60_"):
        # Snooze reminder
        parts = data.split("_")
        snooze_type = parts[0]
        reminder_id = int(parts[1])
        user_timezone = parts[2].replace("|", "/")  # Decode timezone
        
        # Get the reminder details
        from db.database import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT reminder_text FROM reminders WHERE id = ? AND telegram_user_id = ?",
            (reminder_id, user_id)
        )
        result = cursor.fetchone()
        conn.close()
        
        if result:
            reminder_text = result[0]
            
            # Calculate new time
            tz = pytz.timezone(user_timezone)
            now = datetime.now(tz)
            
            if snooze_type == "snooze30":
                new_time = (now + timedelta(minutes=30)).strftime("%H:%M")
                snooze_label = "30 minutes"
            else:  # snooze60
                new_time = (now + timedelta(hours=1)).strftime("%H:%M")
                snooze_label = "1 hour"
            
            # Update reminder time
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE reminders SET reminder_time = ? WHERE id = ?",
                (new_time, reminder_id)
            )
            conn.commit()
            conn.close()
            
            await query.edit_message_text(
                f"{query.message.text}\n\n⏰ **Snoozed for {snooze_label}!**\nNew time: {new_time}"
            )
            print(f"⏰ Reminder {reminder_id} snoozed to {new_time}")
        else:
            await query.edit_message_text(f"{query.message.text}\n\n❌ Reminder not found.")


def handle_response(text: str) -> str:
    processed = text.lower().strip()

    if "hello" in processed:
        return "Hi there! I am Sarah, your reminder bot."

    return "❌ I don't understand that."


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    user_text = update.message.text
    response = handle_response(user_text)

    await update.message.reply_text(response)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    print(f"⚠️ Error: {context.error}")


async def show_timezone_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str) -> None:
    """Show timezone selection keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("🇮🇳 India (IST)", callback_data="tz_Asia/Kolkata"),
            InlineKeyboardButton("🇺🇸 US East (EST)", callback_data="tz_America/New_York")
        ],
        [
            InlineKeyboardButton("🇺🇸 US West (PST)", callback_data="tz_America/Los_Angeles"),
            InlineKeyboardButton("🇬🇧 UK (GMT)", callback_data="tz_Europe/London")
        ],
        [
            InlineKeyboardButton("🇩🇪 Germany (CET)", callback_data="tz_Europe/Berlin"),
            InlineKeyboardButton("🇯🇵 Japan (JST)", callback_data="tz_Asia/Tokyo")
        ],
        [
            InlineKeyboardButton("🇦🇪 Dubai (GST)", callback_data="tz_Asia/Dubai"),
            InlineKeyboardButton("🇦🇺 Australia (AEST)", callback_data="tz_Australia/Sydney")
        ],
        [
            InlineKeyboardButton("🌐 UTC", callback_data="tz_UTC")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(message, reply_markup=reply_markup)


async def set_timezone_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show timezone selection keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("🇮🇳 India (IST)", callback_data="tz_Asia/Kolkata"),
            InlineKeyboardButton("🇺🇸 US East (EST)", callback_data="tz_America/New_York")
        ],
        [
            InlineKeyboardButton("🇺🇸 US West (PST)", callback_data="tz_America/Los_Angeles"),
            InlineKeyboardButton("🇬🇧 UK (GMT)", callback_data="tz_Europe/London")
        ],
        [
            InlineKeyboardButton("🇩🇪 Germany (CET)", callback_data="tz_Europe/Berlin"),
            InlineKeyboardButton("🇯🇵 Japan (JST)", callback_data="tz_Asia/Tokyo")
        ],
        [
            InlineKeyboardButton("🇦🇪 Dubai (GST)", callback_data="tz_Asia/Dubai"),
            InlineKeyboardButton("🇦🇺 Australia (AEST)", callback_data="tz_Australia/Sydney")
        ],
        [
            InlineKeyboardButton("🌐 UTC", callback_data="tz_UTC")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    current_tz = get_user_timezone(update.effective_user.id)
    await update.message.reply_text(
        f"🌍 **Set Your Timezone**\n\nCurrent: `{current_tz}`\n\nSelect your timezone:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )


async def check_reminders(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check for due reminders every minute and send them."""
    # Get all reminders with user timezones
    all_reminders = get_all_reminders_with_timezone()
    
    for reminder in all_reminders:
        reminder_id, user_id, text, reminder_time, user_timezone = reminder
        
        try:
            # Get current time in user's timezone
            tz = pytz.timezone(user_timezone)
            current_time = datetime.now(tz).strftime("%H:%M")
            
            # Check if reminder is due
            if current_time == reminder_time:
                # Create action buttons for the reminder
                # Encode timezone to avoid issues with special characters in callback data
                tz_encoded = user_timezone.replace("/", "|")  # Replace / with |
                
                keyboard = [
                    [
                        InlineKeyboardButton("✅ Done", callback_data=f"done_{reminder_id}"),
                        InlineKeyboardButton("⏰ +30 min", callback_data=f"snooze30_{reminder_id}_{tz_encoded}")
                    ],
                    [
                        InlineKeyboardButton("🕐 +1 hour", callback_data=f"snooze60_{reminder_id}_{tz_encoded}")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"⏰ **Reminder!**\n\n{text}",
                    reply_markup=reply_markup
                )
                print(f"✅ Sent reminder to {user_id}: {text} (TZ: {user_timezone})")
                
                # Don't delete yet - let user mark as done or snooze
        except Exception as e:
            print(f"❌ Failed to process reminder {reminder_id}: {e}")


if __name__ == "__main__":
    # Initialize database on startup
    init_db()
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Conversation Handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("addreminder", add_reminder_start)],
        states={
            WAITING_REMINDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_reminder_text)],
            WAITING_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_reminder_time)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("reminders", list_reminders))
    app.add_handler(CommandHandler("clear", clear_reminders))
    app.add_handler(CommandHandler("settimezone", set_timezone_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT, handle_message))
    app.add_error_handler(error_handler)

    # Start the reminder scheduler (runs every 60 seconds at :00 seconds)
    job_queue = app.job_queue
    
    # Calculate seconds until the next minute starts
    now = datetime.now()
    seconds_until_next_minute = 60 - now.second
    
    # Start checking at the next minute boundary, then every 60 seconds
    job_queue.run_repeating(check_reminders, interval=60, first=seconds_until_next_minute)
    print(f"⏰ Reminder scheduler started (first check in {seconds_until_next_minute}s, then every 60s at :00)")
    
    print("🤖 Bot is polling...")
    app.run_polling()

