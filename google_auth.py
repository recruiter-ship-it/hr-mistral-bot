"""
Simplified Google OAuth 2.0 authentication for Calendar only.
Uses out-of-band (OOB) flow for easier user experience.
"""

import os
import json
import base64
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
import database as db

# OAuth 2.0 scopes - только Calendar
SCOPES = [
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/calendar.events',
]

# OAuth client configuration
CLIENT_CONFIG = {
    "installed": {
        "client_id": os.getenv("GOOGLE_CLIENT_ID", "YOUR_CLIENT_ID"),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET", "YOUR_CLIENT_SECRET"),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob"]
    }
}

# Используем out-of-band flow для упрощения
REDIRECT_URI = "urn:ietf:wg:oauth:2.0:oob"


def get_auth_url(user_id: int) -> str:
    """
    Generate OAuth authorization URL for user.
    
    Args:
        user_id: Telegram user ID
        
    Returns:
        Authorization URL string
    """
    flow = Flow.from_client_config(
        CLIENT_CONFIG,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    
    # Используем user_id как state для идентификации пользователя
    auth_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        state=str(user_id),
        prompt='consent'  # Всегда запрашивать согласие для получения refresh token
    )
    
    return auth_url


def save_credentials_from_code(user_id: int, auth_code: str) -> bool:
    """
    Exchange authorization code for credentials and save to database.
    
    Args:
        user_id: Telegram user ID
        auth_code: Authorization code from OAuth callback
        
    Returns:
        True if successful, False otherwise
    """
    try:
        flow = Flow.from_client_config(
            CLIENT_CONFIG,
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI
        )
        
        flow.fetch_token(code=auth_code)
        credentials = flow.credentials
        
        # Сохраняем credentials в БД
        creds_data = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }
        
        # Кодируем в base64 для безопасности
        creds_json = json.dumps(creds_data)
        creds_encoded = base64.b64encode(creds_json.encode()).decode()
        
        db.save_token(user_id, creds_encoded)
        return True
        
    except Exception as e:
        print(f"Error saving credentials: {e}")
        return False


def get_credentials(user_id: int) -> Credentials:
    """
    Get Google credentials for user from database.
    
    Args:
        user_id: Telegram user ID
        
    Returns:
        Credentials object or None if not found
    """
    try:
        creds_encoded = db.get_token(user_id)
        if not creds_encoded:
            return None
        
        # Декодируем из base64
        if isinstance(creds_encoded, str):
            creds_json = base64.b64decode(creds_encoded.encode()).decode()
            creds_data = json.loads(creds_json)
        else:
            # Старый формат (для обратной совместимости)
            creds_data = creds_encoded
        
        credentials = Credentials(
            token=creds_data.get('token'),
            refresh_token=creds_data.get('refresh_token'),
            token_uri=creds_data.get('token_uri'),
            client_id=creds_data.get('client_id'),
            client_secret=creds_data.get('client_secret'),
            scopes=creds_data.get('scopes')
        )
        
        # Проверяем и обновляем токен если нужно
        if credentials.refresh_token:
            # Проверяем истечение токена или пытаемся обновить превентивно
            if credentials.expired or not credentials.valid:
                try:
                    credentials.refresh(Request())
                    # Сохраняем обновленный токен
                    save_credentials(user_id, credentials)
                    print(f"Token refreshed for user {user_id}")
                except Exception as e:
                    print(f"Error refreshing token for user {user_id}: {e}")
                    # Если refresh не удался, возвращаем None - пользователю нужно переподключиться
                    return None
        elif not credentials.valid:
            # Нет refresh token и токен недействителен - нужно переподключение
            print(f"No refresh token available for user {user_id}, credentials invalid")
            return None
        
        return credentials
        
    except Exception as e:
        print(f"Error getting credentials: {e}")
        return None


def save_credentials(user_id: int, credentials: Credentials):
    """
    Save credentials to database.
    
    Args:
        user_id: Telegram user ID
        credentials: Google Credentials object
    """
    creds_data = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }
    
    creds_json = json.dumps(creds_data)
    creds_encoded = base64.b64encode(creds_json.encode()).decode()
    
    db.save_token(user_id, creds_encoded)


def revoke_credentials(user_id: int):
    """
    Revoke user's Google credentials.
    
    Args:
        user_id: Telegram user ID
    """
    db.delete_token(user_id)
