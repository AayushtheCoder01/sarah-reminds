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
BOT_USERNAME = os.getenv("BOT_USERNAME", "@sarahr_bot")  # fallback

# --- States ---
WAITING_REMINDER = 1
WAITING_TIME = 2
WAITING_DATE = 3
WAITING_TIME_AFTER_DATE = 4

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
    time_45min = (now + timedelta(minutes=45)).strftime("%H:%M")
    time_1hr = (now + timedelta(hours=1)).strftime("%H:%M")
    
    # Calculate nearest hours (next hour, +2hr, +3hr, +4hr)
    next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0).strftime("%H:%M")
    hour_plus2 = (now + timedelta(hours=2)).replace(minute=0, second=0).strftime("%H:%M")
    hour_plus3 = (now + timedelta(hours=3)).replace(minute=0, second=0).strftime("%H:%M")
    hour_plus4 = (now + timedelta(hours=4)).replace(minute=0, second=0).strftime("%H:%M")
    
    # Fixed times in 24-hour format
    fixed_times = ["09:00", "12:00", "18:00", "21:00"]
    
    # Build keyboard with 12 options (3 rows x 4 columns) + date button
    reply_keyboard = [
        [f"⏱️ {time_15min} (15 min)", f"⏰ {time_30min} (30 min)", f"⏲️ {time_45min} (45 min)", f"🕐 {time_1hr} (1 hr)"],
        [f"🕑 {next_hour} (Next hr)", f"🕒 {hour_plus2} (+2 hr)", f"🕓 {hour_plus3} (+3 hr)", f"🕔 {hour_plus4} (+4 hr)"],
        [f"🌅 {fixed_times[0]} (Morning)", f"🌇 {fixed_times[1]} (Noon)", f"🌆 {fixed_times[2]} (Evening)", f"🌃 {fixed_times[3]} (Night)"],
        ["📅 Choose Date"]
    ]
    
    await update.message.reply_text(
        f"✅ Got it! \"{user_text}\"\n\n⏰ When should I remind you?",
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, one_time_keyboard=True, input_field_placeholder="Select or type HH:MM"
        ),
    )
    return WAITING_TIME


async def receive_reminder_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    time_text = update.message.text
    
    # Check if user wants to choose a date
    if "📅" in time_text or "Choose Date" in time_text:
        # Show date picker
        user_id = update.effective_user.id
        user_tz = get_user_timezone(user_id)
        tz = pytz.timezone(user_tz)
        now = datetime.now(tz)
        
        today = now.strftime("%Y-%m-%d")
        tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        day_after = (now + timedelta(days=2)).strftime("%Y-%m-%d")
        
        reply_keyboard = [
            [f"📆 Today ({now.strftime('%b %d')})", f"📆 Tomorrow ({(now + timedelta(days=1)).strftime('%b %d')})"],
            [f"📆 {(now + timedelta(days=2)).strftime('%b %d')}", f"📆 {(now + timedelta(days=3)).strftime('%b %d')}"],
            [f"📆 {(now + timedelta(days=4)).strftime('%b %d')}", f"📆 {(now + timedelta(days=5)).strftime('%b %d')}"],
            [f"📆 {(now + timedelta(days=6)).strftime('%b %d')}", "🔙 Back to Time"]
        ]
        
        await update.message.reply_text(
            "📅 Select a date:",
            reply_markup=ReplyKeyboardMarkup(
                reply_keyboard, one_time_keyboard=True, input_field_placeholder="Select date"
            ),
        )
        return WAITING_DATE
    
    # Extract just the time (remove emoji and any extra text)
    time_parts = time_text.split()
    for part in reversed(time_parts):
        if ':' in part and len(part) == 5:  # HH:MM format
            time_text = part
            break
    
    reminder_text = context.user_data.get('reminder_text', 'No text')
    telegram_user_id = update.effective_user.id
    
    # Get user's timezone to check if time is in the past
    user_tz = get_user_timezone(telegram_user_id)
    tz = pytz.timezone(user_tz)
    now = datetime.now(tz)
    
    # Parse the reminder time
    reminder_hour, reminder_minute = map(int, time_text.split(':'))
    reminder_datetime = now.replace(hour=reminder_hour, minute=reminder_minute, second=0, microsecond=0)
    
    # If time is in the past, schedule for tomorrow
    reminder_date = None
    if reminder_datetime <= now:
        reminder_datetime = reminder_datetime + timedelta(days=1)
        reminder_date = reminder_datetime.strftime("%Y-%m-%d")
        date_display = "tomorrow"
    else:
        date_display = "today"
    
    # Save reminder to database
    add_reminder(telegram_user_id, reminder_text, time_text, reminder_date)
    
    print(f"User Reminder: {reminder_text} at {time_text} on {date_display}")
    
    await update.message.reply_text(f"✅ Reminder saved! I'll remind you:\n\n📝 {reminder_text}\n⏰ at {time_text} ({date_display})")
    return ConversationHandler.END


async def receive_reminder_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    date_text = update.message.text
    
    # Check if user wants to go back
    if "Back to Time" in date_text:
        # Re-show time selection
        return await receive_reminder_text(update, context)
    
    # Extract date from button text
    user_id = update.effective_user.id
    user_tz = get_user_timezone(user_id)
    tz = pytz.timezone(user_tz)
    now = datetime.now(tz)
    
    # Parse the selected date
    if "Today" in date_text:
        selected_date = now
    elif "Tomorrow" in date_text:
        selected_date = now + timedelta(days=1)
    else:
        # Extract date from format like "📆 Jan 23"
        try:
            date_str = date_text.replace("📆", "").strip().rstrip(")")
            selected_date = datetime.strptime(f"{date_str} {now.year}", "%b %d %Y")
            selected_date = tz.localize(selected_date)
        except:
            await update.message.reply_text("❌ Invalid date. Please try again.")
            return WAITING_DATE
    
    # Store the date and ask for time
    context.user_data['reminder_date'] = selected_date.strftime("%Y-%m-%d")
    
    # Show time selection
    reminder_text = context.user_data.get('reminder_text', 'No text')
    
    time_15min = (now + timedelta(minutes=15)).strftime("%H:%M")
    time_30min = (now + timedelta(minutes=30)).strftime("%H:%M")
    time_45min = (now + timedelta(minutes=45)).strftime("%H:%M")
    time_1hr = (now + timedelta(hours=1)).strftime("%H:%M")
    
    next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0).strftime("%H:%M")
    hour_plus2 = (now + timedelta(hours=2)).replace(minute=0, second=0).strftime("%H:%M")
    hour_plus3 = (now + timedelta(hours=3)).replace(minute=0, second=0).strftime("%H:%M")
    hour_plus4 = (now + timedelta(hours=4)).replace(minute=0, second=0).strftime("%H:%M")
    
    fixed_times = ["09:00", "12:00", "18:00", "21:00"]
    
    reply_keyboard = [
        [f"⏱️ {time_15min} (15 min)", f"⏰ {time_30min} (30 min)", f"⏲️ {time_45min} (45 min)", f"🕐 {time_1hr} (1 hr)"],
        [f"🕑 {next_hour} (Next hr)", f"🕒 {hour_plus2} (+2 hr)", f"🕓 {hour_plus3} (+3 hr)", f"🕔 {hour_plus4} (+4 hr)"],
        [f"🌅 {fixed_times[0]} (Morning)", f"🌇 {fixed_times[1]} (Noon)", f"🌆 {fixed_times[2]} (Evening)", f"🌃 {fixed_times[3]} (Night)"]
    ]
    
    await update.message.reply_text(
        f"📅 Date: {selected_date.strftime('%b %d, %Y')}\n\n⏰ What time?",
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, one_time_keyboard=True, input_field_placeholder="Select or type HH:MM"
        ),
    )
    return WAITING_TIME_AFTER_DATE


async def receive_time_after_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    time_text = update.message.text
    
    # Extract just the time
    time_parts = time_text.split()
    for part in reversed(time_parts):
        if ':' in part and len(part) == 5:
            time_text = part
            break
    
    reminder_text = context.user_data.get('reminder_text', 'No text')
    reminder_date = context.user_data.get('reminder_date')
    telegram_user_id = update.effective_user.id
    
    # Save reminder
    add_reminder(telegram_user_id, reminder_text, time_text, reminder_date)
    
    print(f"User Reminder: {reminder_text} at {time_text} on {reminder_date}")
    
    await update.message.reply_text(f"✅ Reminder saved! I'll remind you:\n\n📝 {reminder_text}\n📅 {reminder_date}\n⏰ at {time_text}")
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
        "/cancel - Cancel current operation\n"
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
        reminder_id, text, time, reminder_date, created_at = reminder
        
        # Format date display
        if reminder_date:
            date_display = f" on {reminder_date}"
        else:
            date_display = " (today)"
        
        # Create inline keyboard with delete button for each reminder
        keyboard = [[InlineKeyboardButton("🗑️ Delete", callback_data=f"delete_{reminder_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"📌 {text} - {time}{date_display}",
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
        reminder_id, user_id, text, reminder_time, reminder_date, user_timezone = reminder
        
        try:
            # Get current time and date in user's timezone
            tz = pytz.timezone(user_timezone)
            now = datetime.now(tz)
            current_time = now.strftime("%H:%M")
            current_date = now.strftime("%Y-%m-%d")
            
            # Check if reminder is due (match time and date)
            # If reminder_date is None, it's for today (or was scheduled for today)
            date_matches = (reminder_date is None or reminder_date == current_date)
            
            if current_time == reminder_time and date_matches:
                # Send reminder without action buttons
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"⏰ **Reminder!**\n\n{text}"
                )
                print(f"✅ Sent reminder to {user_id}: {text} (TZ: {user_timezone})")
                
                # Delete the reminder after sending
                delete_reminder(reminder_id, user_id)
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
            WAITING_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_reminder_date)],
            WAITING_TIME_AFTER_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_time_after_date)],
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

