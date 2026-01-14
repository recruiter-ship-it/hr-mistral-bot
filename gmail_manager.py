"""
Gmail API integration for reading and analyzing emails.
"""

import base64
from googleapiclient.discovery import build
from email.mime.text import MIMEText
from datetime import datetime
import google_auth


class GmailManager:
    """Manager for Gmail API operations."""
    
    def __init__(self):
        pass
    
    def _get_service(self, user_id: int):
        """Get Gmail API service for user."""
        credentials = google_auth.get_credentials(user_id)
        if not credentials:
            return None
        return build('gmail', 'v1', credentials=credentials)
    
    def get_recent_emails(self, user_id: int, max_results: int = 10) -> tuple:
        """
        Get recent emails from user's inbox.
        
        Args:
            user_id: Telegram user ID
            max_results: Maximum number of emails to retrieve
            
        Returns:
            Tuple of (message, data) where message is user-friendly text
        """
        service = self._get_service(user_id)
        if not service:
            return "❌ Ошибка: Gmail не подключен. Используйте /connect для авторизации.", None
        
        try:
            # Получаем список сообщений
            results = service.users().messages().list(
                userId='me',
                maxResults=max_results,
                labelIds=['INBOX']
            ).execute()
            
            messages = results.get('messages', [])
            
            if not messages:
                return "📭 Нет новых писем в почтовом ящике.", None
            
            emails_data = []
            response_text = f"📧 Последние {len(messages)} писем:\n\n"
            
            for msg in messages:
                # Получаем полную информацию о письме
                message = service.users().messages().get(
                    userId='me',
                    id=msg['id'],
                    format='full'
                ).execute()
                
                headers = message['payload']['headers']
                subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'Без темы')
                sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Неизвестно')
                date = next((h['value'] for h in headers if h['name'] == 'Date'), '')
                
                # Получаем snippet (краткое содержание)
                snippet = message.get('snippet', '')
                
                emails_data.append({
                    'id': msg['id'],
                    'subject': subject,
                    'from': sender,
                    'date': date,
                    'snippet': snippet
                })
                
                response_text += f"📨 **{subject}**\n"
                response_text += f"От: {sender}\n"
                response_text += f"Дата: {date}\n"
                response_text += f"Превью: {snippet[:100]}...\n\n"
            
            return response_text, emails_data
            
        except Exception as e:
            return f"❌ Ошибка при получении писем: {str(e)}", None
    
    def search_emails(self, user_id: int, query: str, max_results: int = 10) -> tuple:
        """
        Search emails by query.
        
        Args:
            user_id: Telegram user ID
            query: Search query (Gmail search syntax)
            max_results: Maximum number of results
            
        Returns:
            Tuple of (message, data)
        """
        service = self._get_service(user_id)
        if not service:
            return "❌ Ошибка: Gmail не подключен. Используйте /connect для авторизации.", None
        
        try:
            results = service.users().messages().list(
                userId='me',
                q=query,
                maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            
            if not messages:
                return f"🔍 Писем по запросу '{query}' не найдено.", None
            
            response_text = f"🔍 Найдено {len(messages)} писем по запросу '{query}':\n\n"
            
            for msg in messages:
                message = service.users().messages().get(
                    userId='me',
                    id=msg['id'],
                    format='full'
                ).execute()
                
                headers = message['payload']['headers']
                subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'Без темы')
                sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Неизвестно')
                
                response_text += f"📨 {subject}\n"
                response_text += f"От: {sender}\n\n"
            
            return response_text, messages
            
        except Exception as e:
            return f"❌ Ошибка при поиске писем: {str(e)}", None
    
    def get_email_body(self, user_id: int, message_id: str) -> str:
        """
        Get full email body for analysis.
        
        Args:
            user_id: Telegram user ID
            message_id: Gmail message ID
            
        Returns:
            Email body text
        """
        service = self._get_service(user_id)
        if not service:
            return None
        
        try:
            message = service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()
            
            # Извлекаем текст письма
            payload = message['payload']
            
            if 'parts' in payload:
                # Multipart message
                for part in payload['parts']:
                    if part['mimeType'] == 'text/plain':
                        data = part['body'].get('data', '')
                        if data:
                            return base64.urlsafe_b64decode(data).decode('utf-8')
            else:
                # Simple message
                data = payload['body'].get('data', '')
                if data:
                    return base64.urlsafe_b64decode(data).decode('utf-8')
            
            return message.get('snippet', '')
            
        except Exception as e:
            print(f"Error getting email body: {e}")
            return None
    
    def get_unread_count(self, user_id: int) -> int:
        """
        Get count of unread emails.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            Number of unread emails or -1 on error
        """
        service = self._get_service(user_id)
        if not service:
            return -1
        
        try:
            results = service.users().messages().list(
                userId='me',
                labelIds=['INBOX', 'UNREAD']
            ).execute()
            
            return results.get('resultSizeEstimate', 0)
            
        except Exception as e:
            print(f"Error getting unread count: {e}")
            return -1
