from dotenv import load_dotenv
import os
import asyncio
from datetime import datetime
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
    await update.message.reply_text(
        f"Hello! I am {BOT_USERNAME}, your reminder bot."
    )


async def add_reminder_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("What should I remind you about?")
    return WAITING_REMINDER


async def receive_reminder_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_text = update.message.text
    context.user_data['reminder_text'] = user_text
    
    reply_keyboard = [["09:00", "14:00"], ["18:00", "20:00"]]
    
    await update.message.reply_text(
        f"Attributes noted: {user_text}\nAt what time? (Please send in HH:MM format)",
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, one_time_keyboard=True, input_field_placeholder="HH:MM"
        ),
    )
    return WAITING_TIME


async def receive_reminder_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    time_text = update.message.text
    reminder_text = context.user_data.get('reminder_text', 'No text')
    telegram_user_id = update.effective_user.id
    
    # Save reminder to database
    add_reminder(telegram_user_id, reminder_text, time_text)
    
    print(f"User Reminder: {reminder_text} at {time_text}")
    
    await update.message.reply_text(f"✅ Reminder saved! I will remind you: {reminder_text} at {time_text}")
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
        await query.edit_message_text(f"🌍 Timezone set to: **{timezone}**", parse_mode="Markdown")


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
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"⏰ **Reminder!**\n\n{text}",
                    parse_mode="Markdown"
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

