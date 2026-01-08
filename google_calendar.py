import datetime
import os
import json
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ['https://www.googleapis.com/auth/calendar']

class GoogleCalendarManager:
    def __init__(self, credentials_path='credentials.json'):
        self.credentials_path = credentials_path

    def get_flow(self, redirect_uri='urn:ietf:wg:oauth:2.0:oob'):
        return Flow.from_client_secrets_file(
            self.credentials_path,
            scopes=SCOPES,
            redirect_uri=redirect_uri
        )

    def get_service(self, token_data):
        creds = Credentials.from_authorized_user_info(token_data, SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                # Возвращаем обновленные токены, чтобы их сохранить
                token_data = json.loads(creds.to_json())
        
        service = build('calendar', 'v3', credentials=creds)
        return service, token_data

    def add_event(self, token_data, summary, start_time, end_time, description=None):
        try:
            service, updated_token = self.get_service(token_data)
            event = {
                'summary': summary,
                'description': description,
                'start': {'dateTime': start_time, 'timeZone': 'UTC'},
                'end': {'dateTime': end_time, 'timeZone': 'UTC'},
            }
            event = service.events().insert(calendarId='primary', body=event).execute()
            return f"Событие создано: {event.get('htmlLink')}", updated_token
        except Exception as e:
            return f"Ошибка: {str(e)}", None

    def list_events(self, token_data, max_results=10):
        try:
            service, updated_token = self.get_service(token_data)
            now = datetime.datetime.utcnow().isoformat() + 'Z'
            events_result = service.events().list(
                calendarId='primary', timeMin=now,
                maxResults=max_results, singleEvents=True,
                orderBy='startTime'
            ).execute()
            events = events_result.get('items', [])
            
            if not events:
                return "Событий не найдено.", updated_token
            
            res = "Ваши ближайшие события:\n"
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                res += f"- {start}: {event['summary']}\n"
            return res, updated_token
        except Exception as e:
            return f"Ошибка: {str(e)}", None
