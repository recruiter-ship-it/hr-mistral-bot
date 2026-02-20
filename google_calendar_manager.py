"""
Google Calendar API integration with OAuth 2.0 support.
"""

from googleapiclient.discovery import build
from datetime import datetime, timedelta
import google_auth


class GoogleCalendarManager:
    """Manager for Google Calendar API operations."""
    
    def __init__(self):
        pass
    
    def _get_service(self, user_id: int):
        """Get Calendar API service for user."""
        credentials = google_auth.get_credentials(user_id)
        if not credentials:
            return None
        return build('calendar', 'v3', credentials=credentials)
    
    def list_events(self, user_id: int, days: int = 7, max_results: int = 20) -> tuple:
        """
        List upcoming events from user's calendar.
        
        Args:
            user_id: Telegram user ID
            days: Number of days to look ahead
            max_results: Maximum number of events to return
            
        Returns:
            Tuple of (message, data) where message is user-friendly text
        """
        service = self._get_service(user_id)
        if not service:
            return "❌ Ошибка: Календарь не подключен. Используйте /connect для авторизации.", None
        
        try:
            now = datetime.utcnow()
            time_min = now.isoformat() + 'Z'
            time_max = (now + timedelta(days=days)).isoformat() + 'Z'
            
            events_result = service.events().list(
                calendarId='primary',
                timeMin=time_min,
                timeMax=time_max,
                maxResults=max_results,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            if not events:
                return f"📅 Нет событий в календаре на ближайшие {days} дней.", None
            
            response_text = f"📅 *События в календаре (следующие {days} дней)*\n\n"
            
            current_date = None
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                summary = event.get('summary', 'Без названия')
                event_link = event.get('htmlLink', '')
                location = event.get('location', '')
                
                # Форматируем дату и время
                try:
                    if 'T' in start:
                        dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                        date_str = dt.strftime('%d.%m.%Y')
                        time_str = dt.strftime('%H:%M')
                        
                        # Группируем по датам
                        if current_date != date_str:
                            if current_date is not None:
                                response_text += "\n"
                            # Определяем день недели
                            weekday = dt.strftime('%A')
                            weekday_ru = {
                                'Monday': 'Понедельник',
                                'Tuesday': 'Вторник',
                                'Wednesday': 'Среда',
                                'Thursday': 'Четверг',
                                'Friday': 'Пятница',
                                'Saturday': 'Суббота',
                                'Sunday': 'Воскресенье'
                            }.get(weekday, weekday)
                            response_text += f"📆 *{date_str} ({weekday_ru})*\n"
                            current_date = date_str
                        
                        # Событие
                        response_text += f"\n🕐 *{time_str}* - {summary}\n"
                    else:
                        # Целодневное событие
                        response_text += f"\n📅 *Целый день* - {summary}\n"
                except:
                    response_text += f"\n🕐 {start} - {summary}\n"
                
                # Местоположение
                if location:
                    # Проверяем, есть ли ссылка на видеоконференцию
                    if 'meet.google.com' in location or 'zoom.us' in location or 'teams.microsoft.com' in location:
                        response_text += f"📹 [Подключиться]({location})\n"
                    else:
                        response_text += f"📍 {location}\n"
                
                # Описание (убираем - слишком длинно)
                # if 'description' in event:
                #     desc = event['description'][:80].replace('\n', ' ').strip()
                #     if desc:
                #         response_text += f"📝 {desc}\n"
                
                if event_link:
                    response_text += f"[Открыть в календаре]({event_link})\n"
            
            return response_text, events
            
        except Exception as e:
            error_msg = str(e).lower()
            if 'invalid_grant' in error_msg or 'token' in error_msg or 'credentials' in error_msg:
                return "❌ Сессия истекла. Пожалуйста, переподключите календарь через /connect", None
            return f"❌ Ошибка при получении событий: {str(e)}", None
    
    def create_event(
        self,
        user_id: int,
        summary: str,
        start_time: str,
        end_time: str,
        description: str = "",
        attendees: list = None
    ) -> tuple:
        """
        Create a new event in user's calendar.
        
        Args:
            user_id: Telegram user ID
            summary: Event title
            start_time: ISO formatted start time
            end_time: ISO formatted end time
            description: Event description
            attendees: List of attendee emails
            
        Returns:
            Tuple of (message, event_data)
        """
        service = self._get_service(user_id)
        if not service:
            return "❌ Ошибка: Календарь не подключен. Используйте /connect для авторизации.", None
        
        try:
            event = {
                'summary': summary,
                'description': description,
                'start': {
                    'dateTime': start_time,
                    'timeZone': 'UTC',
                },
                'end': {
                    'dateTime': end_time,
                    'timeZone': 'UTC',
                },
            }
            
            if attendees:
                event['attendees'] = [{'email': email} for email in attendees]
            
            created_event = service.events().insert(
                calendarId='primary',
                body=event,
                sendUpdates='all' if attendees else 'none'
            ).execute()
            
            event_link = created_event.get('htmlLink', '')
            
            return f"✅ Событие создано: {summary}\n🔗 {event_link}", created_event
            
        except Exception as e:
            error_msg = str(e).lower()
            if 'invalid_grant' in error_msg or 'token' in error_msg or 'credentials' in error_msg:
                return "❌ Сессия истекла. Пожалуйста, переподключите календарь через /connect", None
            return f"❌ Ошибка при создании события: {str(e)}", None
    
    def find_free_slots(self, user_id: int, date: str, duration_minutes: int = 60) -> tuple:
        """
        Find free time slots on a specific date.
        
        Args:
            user_id: Telegram user ID
            date: Date in YYYY-MM-DD format
            duration_minutes: Desired duration in minutes
            
        Returns:
            Tuple of (message, slots_list)
        """
        service = self._get_service(user_id)
        if not service:
            return "❌ Ошибка: Календарь не подключен. Используйте /connect для авторизации.", None
        
        try:
            # Определяем временные границы дня
            start_of_day = datetime.fromisoformat(f"{date}T00:00:00")
            end_of_day = datetime.fromisoformat(f"{date}T23:59:59")
            
            # Получаем занятые слоты
            body = {
                "timeMin": start_of_day.isoformat() + 'Z',
                "timeMax": end_of_day.isoformat() + 'Z',
                "items": [{"id": "primary"}]
            }
            
            freebusy_result = service.freebusy().query(body=body).execute()
            busy_slots = freebusy_result['calendars']['primary'].get('busy', [])
            
            # Рабочие часы: 9:00 - 18:00
            work_start = start_of_day.replace(hour=9, minute=0)
            work_end = start_of_day.replace(hour=18, minute=0)
            
            free_slots = []
            current_time = work_start
            
            for busy in busy_slots:
                busy_start = datetime.fromisoformat(busy['start'].replace('Z', '+00:00'))
                busy_end = datetime.fromisoformat(busy['end'].replace('Z', '+00:00'))
                
                # Если есть свободное время до занятого слота
                if current_time < busy_start:
                    free_duration = (busy_start - current_time).total_seconds() / 60
                    if free_duration >= duration_minutes:
                        free_slots.append({
                            'start': current_time.isoformat(),
                            'end': (current_time + timedelta(minutes=duration_minutes)).isoformat()
                        })
                
                current_time = max(current_time, busy_end)
            
            # Проверяем оставшееся время до конца рабочего дня
            if current_time < work_end:
                free_duration = (work_end - current_time).total_seconds() / 60
                if free_duration >= duration_minutes:
                    free_slots.append({
                        'start': current_time.isoformat(),
                        'end': (current_time + timedelta(minutes=duration_minutes)).isoformat()
                    })
            
            if not free_slots:
                return f"❌ Нет свободных слотов на {date} (рабочие часы: 9:00-18:00)", None
            
            response_text = f"🕐 Свободные слоты на {date} (длительность {duration_minutes} мин):\n\n"
            for slot in free_slots:
                start_dt = datetime.fromisoformat(slot['start'].replace('Z', '+00:00'))
                response_text += f"✅ {start_dt.strftime('%H:%M')}\n"
            
            return response_text, free_slots
            
        except Exception as e:
            error_msg = str(e).lower()
            if 'invalid_grant' in error_msg or 'token' in error_msg or 'credentials' in error_msg:
                return "❌ Сессия истекла. Пожалуйста, переподключите календарь через /connect", None
            return f"❌ Ошибка при поиске свободных слотов: {str(e)}", None
    
    def get_today_events(self, user_id: int) -> tuple:
        """
        Get today's events.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            Tuple of (message, events)
        """
        service = self._get_service(user_id)
        if not service:
            return "❌ Ошибка: Календарь не подключен.", None
        
        try:
            now = datetime.utcnow()
            start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=999999)
            
            events_result = service.events().list(
                calendarId='primary',
                timeMin=start_of_day.isoformat() + 'Z',
                timeMax=end_of_day.isoformat() + 'Z',
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            if not events:
                return "📅 Сегодня нет запланированных событий.", None
            
            response_text = "🌅 *События на сегодня*\n\n"
            
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                summary = event.get('summary', 'Без названия')
                event_link = event.get('htmlLink', '')
                location = event.get('location', '')
                
                try:
                    dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                    time_str = dt.strftime('%H:%M')
                except:
                    time_str = start
                
                response_text += f"🕐 *{time_str}* - {summary}\n"
                
                # Местоположение/ссылка
                if location:
                    if 'meet.google.com' in location or 'zoom.us' in location or 'teams.microsoft.com' in location:
                        response_text += f"📹 [Подключиться]({location})\n"
                    else:
                        response_text += f"📍 {location}\n"
                
                if event_link:
                    response_text += f"[Открыть в календаре]({event_link})\n"
                
                response_text += "\n"
            
            return response_text, events
            
        except Exception as e:
            error_msg = str(e).lower()
            if 'invalid_grant' in error_msg or 'token' in error_msg or 'credentials' in error_msg:
                return "❌ Сессия истекла. Пожалуйста, переподключите календарь через /connect", None
            return f"❌ Ошибка: {str(e)}", None
