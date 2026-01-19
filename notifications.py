"""
Notification system for calendar events.
Sends reminders 15 minutes before events and daily summaries at 9:00 AM MSK.
"""

import asyncio
import logging
from datetime import datetime, timedelta
import pytz
from telegram import Bot
from telegram.constants import ParseMode
import database as db
from google_calendar_manager import GoogleCalendarManager

# Timezone
MSK = pytz.timezone('Europe/Moscow')
UTC = pytz.UTC

calendar_manager = GoogleCalendarManager()

# Хранилище для отслеживания отправленных уведомлений
sent_notifications = set()


def get_upcoming_events(user_id: int, minutes_ahead: int = 15):
    """
    Get events starting in the next N minutes.
    
    Args:
        user_id: Telegram user ID
        minutes_ahead: Minutes to look ahead
        
    Returns:
        List of events or None
    """
    service = calendar_manager._get_service(user_id)
    if not service:
        return None
    
    try:
        now = datetime.utcnow()
        time_min = now.isoformat() + 'Z'
        time_max = (now + timedelta(minutes=minutes_ahead + 5)).isoformat() + 'Z'
        
        events_result = service.events().list(
            calendarId='primary',
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        return events_result.get('items', [])
    except Exception as e:
        logging.error(f"Error getting upcoming events for user {user_id}: {e}")
        return None


def should_send_reminder(event, minutes_before: int = 15) -> bool:
    """
    Check if we should send a reminder for this event.
    
    Args:
        event: Calendar event
        minutes_before: Minutes before event to send reminder
        
    Returns:
        True if reminder should be sent
    """
    start = event['start'].get('dateTime')
    if not start:
        return False  # Skip all-day events
    
    try:
        event_time = datetime.fromisoformat(start.replace('Z', '+00:00'))
        now = datetime.now(UTC)
        
        time_diff = (event_time - now).total_seconds() / 60
        
        # Send if event is between 15 and 16 minutes away
        return minutes_before <= time_diff <= minutes_before + 1
    except:
        return False


def format_reminder_message(event) -> str:
    """Format a reminder message for an event."""
    summary = event.get('summary', 'Без названия')
    start = event['start'].get('dateTime')
    location = event.get('location', '')
    event_link = event.get('htmlLink', '')
    
    try:
        dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
        time_str = dt.strftime('%H:%M')
    except:
        time_str = start
    
    message = f"⏰ *Напоминание о встрече!*\n\n"
    message += f"🕐 *{time_str}* - {summary}\n"
    
    if location:
        if 'meet.google.com' in location or 'zoom.us' in location or 'teams.microsoft.com' in location:
            message += f"📹 [Подключиться к встрече]({location})\n"
        else:
            message += f"📍 {location}\n"
    
    if event_link:
        message += f"🔗 [Открыть в календаре]({event_link})\n"
    
    message += f"\n_Встреча начнется через 15 минут_"
    
    return message


async def check_and_send_reminders(bot: Bot):
    """
    Check for upcoming events and send reminders.
    Should be called every minute.
    """
    # Получаем всех пользователей с подключенным календарем
    users = db.get_all_users_with_calendar()
    
    for user_id in users:
        try:
            events = get_upcoming_events(user_id, minutes_ahead=15)
            if not events:
                continue
            
            for event in events:
                event_id = event.get('id')
                notification_key = f"{user_id}_{event_id}_15min"
                
                # Проверяем, не отправляли ли уже это уведомление
                if notification_key in sent_notifications:
                    continue
                
                if should_send_reminder(event, minutes_before=15):
                    message = format_reminder_message(event)
                    
                    try:
                        await bot.send_message(
                            chat_id=user_id,
                            text=message,
                            parse_mode=ParseMode.MARKDOWN,
                            disable_web_page_preview=True
                        )
                        sent_notifications.add(notification_key)
                        logging.info(f"Sent reminder to user {user_id} for event {event_id}")
                    except Exception as e:
                        logging.error(f"Failed to send reminder to user {user_id}: {e}")
        
        except Exception as e:
            logging.error(f"Error processing reminders for user {user_id}: {e}")


async def send_daily_summary(bot: Bot):
    """
    Send daily summary of events at 9:00 AM MSK.
    """
    users = db.get_all_users_with_calendar()
    
    for user_id in users:
        try:
            message_text, events = calendar_manager.get_today_events(user_id)
            
            if events:  # Only send if there are events
                try:
                    await bot.send_message(
                        chat_id=user_id,
                        text=message_text,
                        parse_mode=ParseMode.MARKDOWN,
                        disable_web_page_preview=True
                    )
                    logging.info(f"Sent daily summary to user {user_id}")
                except Exception as e:
                    logging.error(f"Failed to send daily summary to user {user_id}: {e}")
        
        except Exception as e:
            logging.error(f"Error getting daily summary for user {user_id}: {e}")


async def notification_loop(bot: Bot):
    """
    Main notification loop.
    Checks for reminders every minute and daily summaries at 9:00 AM MSK.
    """
    logging.info("Notification loop started")
    
    last_daily_summary_date = None
    
    while True:
        try:
            # Check current time in MSK
            now_msk = datetime.now(MSK)
            
            # Send daily summary at 9:00 AM MSK
            if now_msk.hour == 9 and now_msk.minute == 0:
                if last_daily_summary_date != now_msk.date():
                    logging.info("Sending daily summaries...")
                    await send_daily_summary(bot)
                    last_daily_summary_date = now_msk.date()
            
            # Check for upcoming event reminders
            await check_and_send_reminders(bot)
            
            # Clean up old notifications (older than 24 hours)
            if len(sent_notifications) > 1000:
                sent_notifications.clear()
            
        except Exception as e:
            logging.error(f"Error in notification loop: {e}")
        
        # Wait 1 minute before next check
        await asyncio.sleep(60)
