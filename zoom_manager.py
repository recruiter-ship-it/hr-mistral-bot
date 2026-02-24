"""
Zoom Manager Module
Управление Zoom митингами через Zoom API
"""

import logging
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
import zoom_auth

logger = logging.getLogger(__name__)


class ZoomManager:
    """Класс для управления Zoom митингами"""
    
    BASE_URL = "https://api.zoom.us/v2"
    
    def _get_headers(self, user_id: int) -> Optional[Dict]:
        """
        Получить заголовки с токеном авторизации
        
        Args:
            user_id: ID пользователя Telegram
            
        Returns:
            Словарь заголовков или None если нет токена
        """
        tokens = zoom_auth.get_tokens(user_id)
        if not tokens:
            return None
        
        return {
            "Authorization": f"Bearer {tokens['access_token']}",
            "Content-Type": "application/json"
        }
    
    def _make_request(
        self, 
        user_id: int, 
        method: str, 
        endpoint: str, 
        data: Dict = None
    ) -> Tuple[bool, Any]:
        """
        Выполнить запрос к Zoom API
        
        Args:
            user_id: ID пользователя Telegram
            method: HTTP метод (GET, POST, PATCH, DELETE)
            endpoint: Endpoint API (например, /users/me/meetings)
            data: Данные для отправки
            
        Returns:
            Кортеж (success, result_or_error)
        """
        headers = self._get_headers(user_id)
        if not headers:
            return False, "Zoom не подключён. Используйте /zoom_connect"
        
        url = f"{self.BASE_URL}{endpoint}"
        
        try:
            if method == "GET":
                response = requests.get(url, headers=headers)
            elif method == "POST":
                response = requests.post(url, headers=headers, json=data)
            elif method == "PATCH":
                response = requests.patch(url, headers=headers, json=data)
            elif method == "DELETE":
                response = requests.delete(url, headers=headers)
            else:
                return False, f"Unsupported method: {method}"
            
            # Обработка ошибок авторизации
            if response.status_code == 401:
                # Токен истёк, пытаемся обновить
                zoom_auth.refresh_token(user_id)
                headers = self._get_headers(user_id)
                if not headers:
                    return False, "Ошибка авторизации Zoom. Подключите заново: /zoom_connect"
                
                # Повторяем запрос
                if method == "GET":
                    response = requests.get(url, headers=headers)
                elif method == "POST":
                    response = requests.post(url, headers=headers, json=data)
                elif method == "PATCH":
                    response = requests.patch(url, headers=headers, json=data)
                elif method == "DELETE":
                    response = requests.delete(url, headers=headers)
            
            if response.status_code in (200, 201, 204):
                if response.content:
                    return True, response.json()
                return True, None
            else:
                error_msg = response.json().get("message", response.text)
                logger.error(f"Zoom API error: {response.status_code} - {error_msg}")
                return False, f"Ошибка Zoom: {error_msg}"
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Zoom API request failed: {e}")
            return False, f"Ошибка запроса: {str(e)}"
    
    def get_user_info(self, user_id: int) -> Tuple[str, Dict]:
        """
        Получить информацию о пользователе Zoom
        
        Args:
            user_id: ID пользователя Telegram
            
        Returns:
            Кортеж (сообщение, данные)
        """
        success, result = self._make_request(user_id, "GET", "/users/me")
        
        if success:
            return "✅ Zoom подключён!", result
        else:
            return result, {}
    
    def create_meeting(
        self,
        user_id: int,
        topic: str = "Встреча",
        duration: int = 60,
        start_time: datetime = None,
        password: str = None,
        settings: Dict = None
    ) -> Tuple[str, Dict]:
        """
        Создать Zoom митинг
        
        Args:
            user_id: ID пользователя Telegram
            topic: Тема митинга
            duration: Длительность в минутах
            start_time: Время начала (если None - Instant meeting)
            password: Пароль для входа
            settings: Дополнительные настройки
            
        Returns:
            Кортеж (сообщение, данные митинга)
        """
        # Данные для создания митинга
        meeting_data = {
            "topic": topic,
            "type": 2,  # Scheduled meeting (или 1 для instant)
            "duration": duration,
            "timezone": "Europe/Moscow",
            "settings": {
                "join_before_host": False,
                "mute_upon_entry": True,
                "waiting_room": True,
                "auto_recording": "none"
            }
        }
        
        # Если указано время начала
        if start_time:
            meeting_data["start_time"] = start_time.strftime("%Y-%m-%dT%H:%M:%S")
        else:
            # Instant meeting
            meeting_data["type"] = 1
        
        # Пароль
        if password:
            meeting_data["password"] = password
        
        # Дополнительные настройки
        if settings:
            meeting_data["settings"].update(settings)
        
        success, result = self._make_request(
            user_id, "POST", "/users/me/meetings", meeting_data
        )
        
        if success:
            meeting_info = {
                "id": result.get("id"),
                "topic": result.get("topic"),
                "join_url": result.get("join_url"),
                "start_url": result.get("start_url"),
                "password": result.get("password"),
                "duration": result.get("duration"),
                "start_time": result.get("start_time"),
                "host_email": result.get("host_email")
            }
            
            message = (
                f"✅ **Митинг создан!**\n\n"
                f"📋 **Тема:** {meeting_info['topic']}\n"
                f"🔗 **Ссылка для участников:**\n{meeting_info['join_url']}\n"
            )
            
            if meeting_info.get("password"):
                message += f"🔑 **Пароль:** {meeting_info['password']}\n"
            
            return message, meeting_info
        else:
            return result, {}
    
    def create_instant_meeting(
        self, 
        user_id: int, 
        topic: str = "Быстрая встреча"
    ) -> Tuple[str, Dict]:
        """
        Создать мгновенный митинг (начинается сразу)
        
        Args:
            user_id: ID пользователя Telegram
            topic: Тема митинга
            
        Returns:
            Кортеж (сообщение, данные митинга)
        """
        return self.create_meeting(
            user_id=user_id,
            topic=topic,
            start_time=None,  # Instant meeting
            duration=60
        )
    
    def list_meetings(
        self, 
        user_id: int, 
        limit: int = 10
    ) -> Tuple[str, list]:
        """
        Получить список митингов пользователя
        
        Args:
            user_id: ID пользователя Telegram
            limit: Максимальное количество
            
        Returns:
            Кортеж (сообщение, список митингов)
        """
        success, result = self._make_request(
            user_id, "GET", f"/users/me/meetings?page_size={limit}"
        )
        
        if success:
            meetings = result.get("meetings", [])
            
            if not meetings:
                return "У вас нет запланированных митингов.", []
            
            message = f"📅 **Ваши митинги ({len(meetings)}):**\n\n"
            
            for i, m in enumerate(meetings[:limit], 1):
                start_time = m.get("start_time", "N/A")
                if start_time and start_time != "N/A":
                    try:
                        dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                        start_time = dt.strftime("%d.%m.%Y %H:%M")
                    except:
                        pass
                
                message += (
                    f"{i}. **{m.get('topic', 'Без темы')}**\n"
                    f"   📅 {start_time}\n"
                    f"   🔗 {m.get('join_url', 'N/A')}\n\n"
                )
            
            return message, meetings
        else:
            return result, []
    
    def delete_meeting(self, user_id: int, meeting_id: str) -> Tuple[str, bool]:
        """
        Удалить митинг
        
        Args:
            user_id: ID пользователя Telegram
            meeting_id: ID митинга Zoom
            
        Returns:
            Кортеж (сообщение, успех)
        """
        success, result = self._make_request(
            user_id, "DELETE", f"/meetings/{meeting_id}"
        )
        
        if success:
            return "✅ Митинг удалён.", True
        else:
            return result, False
    
    def get_meeting(self, user_id: int, meeting_id: str) -> Tuple[str, Dict]:
        """
        Получить информацию о митинге
        
        Args:
            user_id: ID пользователя Telegram
            meeting_id: ID митинга Zoom
            
        Returns:
            Кортеж (сообщение, данные митинга)
        """
        success, result = self._make_request(
            user_id, "GET", f"/meetings/{meeting_id}"
        )
        
        if success:
            meeting_info = {
                "id": result.get("id"),
                "topic": result.get("topic"),
                "join_url": result.get("join_url"),
                "start_url": result.get("start_url"),
                "password": result.get("password"),
                "duration": result.get("duration"),
                "start_time": result.get("start_time"),
                "status": result.get("status")
            }
            
            message = (
                f"📋 **{meeting_info['topic']}**\n"
                f"🆔 ID: {meeting_info['id']}\n"
                f"🔗 {meeting_info['join_url']}\n"
                f"⏱ Длительность: {meeting_info['duration']} мин\n"
            )
            
            if meeting_info.get("password"):
                message += f"🔑 Пароль: {meeting_info['password']}\n"
            
            return message, meeting_info
        else:
            return result, {}


# Глобальный экземпляр
zoom_manager = ZoomManager()
