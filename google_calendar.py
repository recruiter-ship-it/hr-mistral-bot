import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime, timedelta


class GoogleCalendarManager:
    """
    Simple wrapper around the Google Calendar API for listing and creating
    events.

    The service account credentials are loaded from `credentials.json`. If
    the file does not exist or cannot be parsed, `get_service` will return
    None and the API methods will respond with a user-friendly error.
    """

    def __init__(self, credentials_path: str = 'credentials.json') -> None:
        self.credentials_path = credentials_path
        self.scopes = ['https://www.googleapis.com/auth/calendar']
        self.creds = None
        if os.path.exists(self.credentials_path):
            try:
                self.creds = service_account.Credentials.from_service_account_file(
                    self.credentials_path, scopes=self.scopes
                )
            except Exception as e:
                print(f"Error loading service account: {e}")

    def get_service(self):
        if not self.creds:
            return None
        return build('calendar', 'v3', credentials=self.creds)

    def list_events(self, calendar_id: str, max_results: int = 10):
        """
        List upcoming events for a given calendar.

        :param calendar_id: Calendar ID (in our bot, the Gmail address).
        :param max_results: Maximum number of events to return.
        :return: Tuple of (message, data). Data is always None; message is a
                 user-friendly string.
        """
        service = self.get_service()
        if not service:
            return "❌ Ошибка: Календарь не настроен.", None
        now = datetime.utcnow().isoformat() + 'Z'
        try:
            events_result = service.events().list(
                calendarId=calendar_id,
                timeMin=now,
                maxResults=max_results,
                singleEvents=True,
                orderBy='startTime',
            ).execute()
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

    def add_event(
        self,
        calendar_id: str,
        summary: str,
        start_time: str,
        end_time: str,
        description: str = "",
    ):
        """
        Create a new event on the user's calendar.

        :param calendar_id: Calendar ID (the Gmail address).
        :param summary: Title of the event.
        :param start_time: ISO formatted start time (UTC).
        :param end_time: ISO formatted end time (UTC).
        :param description: Optional description.
        :return: Tuple of (message, data). Data is None; message is a
                 user-friendly string.
        """
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
            created = service.events().insert(calendarId=calendar_id, body=event).execute()
            return f"Событие создано: {created.get('htmlLink')}", None
        except Exception as e:
            return f"❌ Ошибка при создании события: {str(e)}", None
