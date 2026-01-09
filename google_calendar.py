import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime, timedelta

class GoogleCalendarManager:
    def __init__(self, credentials_path='credentials.json'):
        self.credentials_path = credentials_path
        self.scopes = ['https://www.googleapis.com/auth/calendar']
        self.creds = None
        if os.path.exists(self.credentials_path):
            try:
                self.creds = service_account.Credentials.from_service_account_file(
                    self.credentials_path, scopes=self.scopes)
            except Exception as e:
                print(f"Error loading service account: {e}")

    def get_service(self):
        if not self.creds:
            return None
        return build('calendar', 'v3', credentials=self.creds)

    def list_events(self, calendar_id, max_results=10):
        service = self.get_service()
        if not service:
            return "❌ Ошибка: Календарь не настроен.", None
        
        now = datetime.utcnow().isoformat() + 'Z'
        try:
            events_result = service.events().list(
                calendarId=calendar_id, timeMin=now,
                maxResults=max_results, singleEvents=True,
                orderBy='startTime').execute()
            events = events_result.get('items', [])
            
            if not events:
                return "Событий не найдено.", None
            
            res = "Ближайшие события в календаре:\n"
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                res += f"- {start}: {event['summary']}\n"
            return res, None
        except Exception as e:
            return f"❌ Ошибка при получении событий: {str(e)}", None

    def add_event(self, calendar_id, summary, start_time, end_time, description=""):
        service = self.get_service()
        if not service:
            return "❌ Ошибка: Календарь не настроен.", None
        
        event = {
            'summary': summary,
            'description': description,
            'start': {'dateTime': start_time, 'timeZone': 'UTC'},
            'end': {'dateTime': end_time, 'timeZone': 'UTC'},
        }
        try:
            event = service.events().insert(calendarId=calendar_id, body=event).execute()
            return f"Событие создано: {event.get('htmlLink')}", None
        except Exception as e:
            return f"❌ Ошибка при создании события: {str(e)}", None
