import datetime
import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/calendar']

class GoogleCalendar:
    def __init__(self):
        self.creds = None
        # The file token.json stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        if os.path.exists('token.json'):
            self.creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        
    def get_service(self):
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
            else:
                # В контексте бота нам нужно будет реализовать OAuth через ссылку
                return None
            with open('token.json', 'w') as token:
                token.write(self.creds.to_json())
        
        return build('calendar', 'v3', credentials=self.creds)

    def add_event(self, summary, start_time, end_time, description=None):
        service = self.get_service()
        if not service:
            return "Ошибка авторизации Google Calendar"
        
        event = {
            'summary': summary,
            'description': description,
            'start': {
                'dateTime': start_time, # ISO format: '2023-05-28T09:00:00-07:00'
                'timeZone': 'UTC',
            },
            'end': {
                'dateTime': end_time,
                'timeZone': 'UTC',
            },
        }

        try:
            event = service.events().insert(calendarId='primary', body=event).execute()
            return f"Событие создано: {event.get('htmlLink')}"
        except HttpError as error:
            return f"Произошла ошибка: {error}"

    def list_events(self, max_results=10):
        service = self.get_service()
        if not service:
            return "Ошибка авторизации Google Calendar"
            
        now = datetime.datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
        events_result = service.events().list(calendarId='primary', timeMin=now,
                                              maxResults=max_results, singleEvents=True,
                                              orderBy='startTime').execute()
        events = events_result.get('items', [])

        if not events:
            return "Предстоящих событий не найдено."
        
        res = "Предстоящие события:\n"
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            res += f"- {start}: {event['summary']}\n"
        return res
