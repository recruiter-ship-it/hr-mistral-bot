"""
Zoom OAuth Authentication Module
Авторизация пользователей через Zoom OAuth 2.0
Аналогично google_auth.py
"""

import os
import json
import logging
import requests
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

# Конфигурация Zoom OAuth
ZOOM_CLIENT_ID = os.getenv("ZOOM_CLIENT_ID", "")
ZOOM_CLIENT_SECRET = os.getenv("ZOOM_CLIENT_SECRET", "")
ZOOM_REDIRECT_URI = os.getenv("ZOOM_REDIRECT_URI", "https://zoom.us/oauth/authorize")

# Файл для хранения токенов (аналогично Google)
ZOOM_TOKENS_FILE = Path(__file__).parent / "zoom_tokens.json"
ZOOM_STATES_FILE = Path(__file__).parent / "zoom_states.json"

# Scopes для Zoom
ZOOM_SCOPES = "meeting:write meeting:read user:read"


class ZoomAuth:
    """Класс для работы с Zoom OAuth"""
    
    def __init__(self):
        self._load_states()
    
    def _load_states(self):
        """Загрузить states для OAuth"""
        if ZOOM_STATES_FILE.exists():
            with open(ZOOM_STATES_FILE, 'r') as f:
                self._states = json.load(f)
        else:
            self._states = {}
    
    def _save_states(self):
        """Сохранить states"""
        with open(ZOOM_STATES_FILE, 'w') as f:
            json.dump(self._states, f)
    
    def _load_tokens(self) -> Dict:
        """Загрузить все токены"""
        if ZOOM_TOKENS_FILE.exists():
            with open(ZOOM_TOKENS_FILE, 'r') as f:
                return json.load(f)
        return {}
    
    def _save_tokens(self, tokens: Dict):
        """Сохранить все токены"""
        with open(ZOOM_TOKENS_FILE, 'w') as f:
            json.dump(tokens, f, indent=2)
    
    def get_auth_url(self, user_id: int) -> str:
        """
        Генерирует URL для OAuth авторизации Zoom
        
        Args:
            user_id: ID пользователя Telegram
            
        Returns:
            URL для авторизации
        """
        # Генерируем случайный state для защиты от CSRF
        state = secrets.token_urlsafe(32)
        
        # Сохраняем state с привязкой к user_id
        self._states[state] = {
            "user_id": user_id,
            "created": datetime.now().isoformat(),
            "expires": (datetime.now() + timedelta(minutes=10)).isoformat()
        }
        self._save_states()
        
        # Формируем URL
        auth_url = (
            f"https://zoom.us/oauth/authorize"
            f"?response_type=code"
            f"&client_id={ZOOM_CLIENT_ID}"
            f"&redirect_uri={ZOOM_REDIRECT_URI}"
            f"&scope={ZOOM_SCOPES}"
            f"&state={state}"
        )
        
        logger.info(f"Generated Zoom auth URL for user {user_id}")
        return auth_url
    
    def verify_state(self, state: str) -> Optional[int]:
        """
        Проверяет state и возвращает user_id если валидно
        
        Args:
            state: State из OAuth ответа
            
        Returns:
            user_id или None если невалидно
        """
        if state not in self._states:
            logger.warning(f"Invalid state: {state}")
            return None
        
        state_data = self._states[state]
        
        # Проверяем expiration
        expires = datetime.fromisoformat(state_data["expires"])
        if datetime.now() > expires:
            logger.warning(f"State expired: {state}")
            del self._states[state]
            self._save_states()
            return None
        
        # Удаляем использованный state
        user_id = state_data["user_id"]
        del self._states[state]
        self._save_states()
        
        return user_id
    
    def exchange_code_for_tokens(self, code: str) -> Optional[Dict]:
        """
        Обменивает authorization code на токены
        
        Args:
            code: Authorization code от Zoom
            
        Returns:
            Словарь с токенами или None при ошибке
        """
        token_url = "https://zoom.us/oauth/token"
        
        # Basic Auth с Client ID и Client Secret
        auth = (ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET)
        
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": ZOOM_REDIRECT_URI
        }
        
        try:
            response = requests.post(token_url, auth=auth, data=data)
            response.raise_for_status()
            
            tokens = response.json()
            
            # Добавляем время истечения
            tokens["expires_at"] = (
                datetime.now() + timedelta(seconds=tokens.get("expires_in", 3600))
            ).isoformat()
            
            logger.info("Successfully exchanged code for tokens")
            return tokens
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to exchange code: {e}")
            return None
    
    def refresh_token(self, user_id: int) -> Optional[Dict]:
        """
        Обновляет access token используя refresh token
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Новые токены или None при ошибке
        """
        tokens = self.get_tokens(user_id)
        if not tokens or "refresh_token" not in tokens:
            return None
        
        token_url = "https://zoom.us/oauth/token"
        auth = (ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET)
        
        data = {
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"]
        }
        
        try:
            response = requests.post(token_url, auth=auth, data=data)
            response.raise_for_status()
            
            new_tokens = response.json()
            new_tokens["expires_at"] = (
                datetime.now() + timedelta(seconds=new_tokens.get("expires_in", 3600))
            ).isoformat()
            
            # Сохраняем новые токены
            self.save_tokens(user_id, new_tokens)
            
            logger.info(f"Refreshed tokens for user {user_id}")
            return new_tokens
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to refresh token: {e}")
            # Если refresh не работает, удаляем токены
            self.revoke_tokens(user_id)
            return None
    
    def save_tokens(self, user_id: int, tokens: Dict):
        """
        Сохраняет токены для пользователя
        
        Args:
            user_id: ID пользователя Telegram
            tokens: Словарь с токенами
        """
        all_tokens = self._load_tokens()
        all_tokens[str(user_id)] = tokens
        self._save_tokens(all_tokens)
        logger.info(f"Saved tokens for user {user_id}")
    
    def get_tokens(self, user_id: int) -> Optional[Dict]:
        """
        Получает токены пользователя
        
        Args:
            user_id: ID пользователя Telegram
            
        Returns:
            Словарь с токенами или None
        """
        all_tokens = self._load_tokens()
        tokens = all_tokens.get(str(user_id))
        
        if not tokens:
            return None
        
        # Проверяем, не истёк ли токен
        expires_at = datetime.fromisoformat(tokens.get("expires_at", "2000-01-01"))
        if datetime.now() >= expires_at:
            # Пытаемся обновить
            logger.info(f"Token expired for user {user_id}, refreshing...")
            return self.refresh_token(user_id)
        
        return tokens
    
    def revoke_tokens(self, user_id: int) -> bool:
        """
        Удаляет токены пользователя
        
        Args:
            user_id: ID пользователя Telegram
            
        Returns:
            True если успешно
        """
        all_tokens = self._load_tokens()
        if str(user_id) in all_tokens:
            del all_tokens[str(user_id)]
            self._save_tokens(all_tokens)
            logger.info(f"Revoked tokens for user {user_id}")
            return True
        return False
    
    def has_valid_tokens(self, user_id: int) -> bool:
        """
        Проверяет, есть ли валидные токены у пользователя
        
        Args:
            user_id: ID пользователя Telegram
            
        Returns:
            True если есть валидные токены
        """
        tokens = self.get_tokens(user_id)
        return tokens is not None
    
    def save_credentials_from_code(self, user_id: int, code: str) -> bool:
        """
        Сохраняет credentials из authorization code
        
        Args:
            user_id: ID пользователя Telegram
            code: Authorization code от Zoom
            
        Returns:
            True если успешно
        """
        tokens = self.exchange_code_for_tokens(code)
        if tokens:
            self.save_tokens(user_id, tokens)
            return True
        return False


# Глобальный экземпляр
zoom_auth = ZoomAuth()


# Удобные функции (аналогично google_auth)
def get_auth_url(user_id: int) -> str:
    """Получить URL для авторизации Zoom"""
    return zoom_auth.get_auth_url(user_id)


def get_credentials(user_id: int) -> Optional[Dict]:
    """Получить токены пользователя"""
    return zoom_auth.get_tokens(user_id)


def save_credentials_from_code(user_id: int, code: str) -> bool:
    """Сохранить credentials из кода"""
    return zoom_auth.save_credentials_from_code(user_id, code)


def revoke_credentials(user_id: int) -> bool:
    """Отозвать токены"""
    return zoom_auth.revoke_tokens(user_id)


def has_valid_credentials(user_id: int) -> bool:
    """Проверить наличие валидных токенов"""
    return zoom_auth.has_valid_tokens(user_id)
