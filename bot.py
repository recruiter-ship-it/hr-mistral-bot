#!/usr/bin/env python3
"""
HR Mistral Bot - Full Version for GitHub Actions
С полным функционалом: кандидаты, вакансии, документы, голосовые, изображения, Google Calendar
"""
import logging
import os
import asyncio
import json
import base64
from pathlib import Path
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from telegram.error import BadRequest
from mistralai import Mistral

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# API Ключи
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "AEE3rpaceKHZzBtbVKnN9CWoNdpjlp2l")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8399347076:AAFLtRxXEKESWuTQb19vc6mhMQph7rHxsLg")

# Инициализация клиента Mistral
mistral_client = Mistral(api_key=MISTRAL_API_KEY)

# Хранилища
user_conversations = {}
candidates_db = {}  # Простая in-memory база кандидатов
vacancies_db = {}   # Простая in-memory база вакансий
memory_db = {}      # Память пользователя
generated_images = []  # История сгенерированных изображений
calendar_credentials = {}  # Google Calendar credentials per user

# Счётчики ID
candidate_id_counter = 0
vacancy_id_counter = 0

# Пытаемся импортировать Google модули
try:
    import google_auth
    from google_calendar_manager import GoogleCalendarManager
    GOOGLE_AVAILABLE = True
    calendar_manager = GoogleCalendarManager()
    logger.info("✅ Google Calendar modules loaded")
except ImportError as e:
    GOOGLE_AVAILABLE = False
    calendar_manager = None
    logger.warning(f"⚠️ Google Calendar not available: {e}")

# ============================================================================
# СИСТЕМНЫЙ ПРОМПТ
# ============================================================================

SYSTEM_PROMPT = """Ты — **HRик HуяRік**, экспертный ИИ-ассистент для HR-команды и рекрутеров.

Ты — полноценный AI-агент с доступом к инструментам. Ты можешь выполнять многошаговые задачи, создавать документы и управлять HR-процессами.

Ты дружелюбный, профессиональный и всегда готов помочь. Используй эмодзи умеренно (1-2 на сообщение).

## 🎯 Твои ключевые возможности:

### 1. УПРАВЛЕНИЕ КАНДИДАТАМИ
- **save_candidate** - сохранить кандидата в базу данных
- **search_candidates** - поиск кандидатов по имени, статусу, позиции
- **update_candidate_status** - обновить статус кандидата

### 2. УПРАВЛЕНИЕ ВАКАНСИЯМИ
- **create_vacancy** - создать новую вакансию
- **list_vacancies** - показать открытые вакансии

### 3. КАЛЕНДАРЬ (Google Calendar)
- **get_calendar_events** - получить события календаря
- Для подключения используйте команду /connect

### 4. СОЗДАНИЕ ДОКУМЕНТОВ
- **create_offer** - создать оффер о приёме на работу
- **create_welcome** - создать welcome-документ для нового сотрудника
- **create_scorecard** - создать карту оценки кандидата
- **create_rejection** - создать письмо с отказом
- **create_interview_invite** - создать приглашение на интервью

### 5. АВТОНОМНЫЕ ВОРКФЛОУ
- **onboard_employee** - полный процесс онбординга
- **process_candidate** - обработка нового кандидата

### 6. РАСШИРЕННЫЕ НАВЫКИ
- **image_generate** - сгенерировать изображение через AI
- **memory_remember** - сохранить информацию в память
- **memory_recall** - вспомнить информацию из памяти
- **web_search** - поиск в интернете

## 📋 Примеры запросов:

**Кандидаты:**
- "Сохрани кандидата Иван Петров, позиция Python Developer, email ivan@mail.ru"
- "Найди кандидатов на позицию разработчика"
- "Обнови статус кандидата Иван на 'interview'"

**Календарь:**
- "Какие у меня встречи сегодня?"
- "Покажи события на неделю"

**Документы:**
- "Создай оффер для кандидата Иван Петров на позицию Senior Python Developer, зарплата 3000 USDT, выход 15 марта"
- "Создай welcome-документ для нового сотрудника Мария Иванова"

**Изображения:**
- "Сгенерируй изображение: логотип компании в стиле минимализм"

## Формат общения:
- Тон: Дружелюбный, профессиональный
- Используй **жирный текст** для ключевых моментов
- Markdown обязателен для улучшения читаемости
- Всегда задавай уточняющие вопросы если не хватает данных

## ВАЖНО:
- Для создания документов ОБЯЗАТЕЛЬНО нужны: имя кандидата, позиция, дата
- Для оффера ОБЯЗАТЕЛЬНО нужна зарплата
- Для календаря нужно подключить Google через /connect
- Если пользователь не указал все данные - спроси недостающее
- Всегда подтверждай выполнение действий
"""

# ============================================================================
# ИНСТРУМЕНТЫ ДЛЯ MISTRAL
# ============================================================================

def get_all_tools():
    """Получить все инструменты для Mistral Agent"""
    tools = [
        # Веб-поиск
        {"type": "web_search"},
        
        # === Календарь ===
        {
            "type": "function",
            "function": {
                "name": "get_calendar_events",
                "description": "Получить события из Google Calendar пользователя на указанное количество дней",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "days": {
                            "type": "integer",
                            "description": "Количество дней для просмотра (по умолчанию 7)"
                        }
                    }
                }
            }
        },
        
        # === Кандидаты ===
        {
            "type": "function",
            "function": {
                "name": "save_candidate",
                "description": "Сохранить кандидата в базу данных.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Имя кандидата"},
                        "email": {"type": "string", "description": "Email"},
                        "phone": {"type": "string", "description": "Телефон"},
                        "position": {"type": "string", "description": "Желаемая позиция"},
                        "skills": {"type": "array", "items": {"type": "string"}, "description": "Навыки"},
                        "experience": {"type": "string", "description": "Опыт работы"},
                        "salary_expectation": {"type": "string", "description": "Ожидания по зарплате"},
                        "source": {"type": "string", "description": "Источник кандидата"},
                        "notes": {"type": "string", "description": "Заметки"},
                        "rating": {"type": "integer", "description": "Оценка 1-10"}
                    },
                    "required": ["name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "search_candidates",
                "description": "Поиск кандидатов в базе данных.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Поисковый запрос"},
                        "status": {"type": "string", "description": "Статус кандидата"},
                        "position": {"type": "string", "description": "Позиция"},
                        "limit": {"type": "integer", "description": "Макс. количество"}
                    }
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "update_candidate_status",
                "description": "Обновить статус кандидата.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "candidate_name": {"type": "string", "description": "Имя кандидата"},
                        "status": {"type": "string", "description": "Новый статус", "enum": ["new", "screening", "interview", "offer", "hired", "rejected"]}
                    },
                    "required": ["candidate_name", "status"]
                }
            }
        },
        
        # === Вакансии ===
        {
            "type": "function",
            "function": {
                "name": "create_vacancy",
                "description": "Создать новую вакансию.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Название вакансии"},
                        "department": {"type": "string", "description": "Отдел"},
                        "description": {"type": "string", "description": "Описание"},
                        "requirements": {"type": "string", "description": "Требования"},
                        "salary_range": {"type": "string", "description": "Зарплатная вилка"}
                    },
                    "required": ["title"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "list_vacancies",
                "description": "Показать открытые вакансии.",
                "parameters": {"type": "object", "properties": {}}
            }
        },
        
        # === Документы ===
        {
            "type": "function",
            "function": {
                "name": "create_offer",
                "description": "Создать оффер о приёме на работу.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "candidate_name": {"type": "string", "description": "Имя кандидата"},
                        "position": {"type": "string", "description": "Должность"},
                        "salary": {"type": "string", "description": "Зарплата"},
                        "start_date": {"type": "string", "description": "Дата выхода"},
                        "department": {"type": "string", "description": "Отдел"}
                    },
                    "required": ["candidate_name", "position", "salary", "start_date"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "create_welcome",
                "description": "Создать welcome-документ для нового сотрудника.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "candidate_name": {"type": "string", "description": "Имя сотрудника"},
                        "position": {"type": "string", "description": "Должность"},
                        "start_date": {"type": "string", "description": "Дата выхода"},
                        "buddy_name": {"type": "string", "description": "Имя buddy"},
                        "manager_name": {"type": "string", "description": "Имя руководителя"}
                    },
                    "required": ["candidate_name", "position", "start_date"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "create_scorecard",
                "description": "Создать карту оценки кандидата после интервью.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "candidate_name": {"type": "string", "description": "Имя кандидата"},
                        "position": {"type": "string", "description": "Должность"},
                        "interviewer": {"type": "string", "description": "Интервьюер"},
                        "strengths": {"type": "string", "description": "Сильные стороны"},
                        "weaknesses": {"type": "string", "description": "Слабые стороны"},
                        "recommendation": {"type": "string", "description": "Рекомендация (hire/no hire/maybe)"}
                    },
                    "required": ["candidate_name", "position", "interviewer"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "create_rejection",
                "description": "Создать письмо с отказом кандидату.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "candidate_name": {"type": "string", "description": "Имя кандидата"},
                        "position": {"type": "string", "description": "Должность"},
                        "reason": {"type": "string", "description": "Причина отказа (общая)"}
                    },
                    "required": ["candidate_name", "position"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "create_interview_invite",
                "description": "Создать приглашение на интервью.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "candidate_name": {"type": "string", "description": "Имя кандидата"},
                        "position": {"type": "string", "description": "Должность"},
                        "interview_date": {"type": "string", "description": "Дата интервью"},
                        "interview_time": {"type": "string", "description": "Время интервью"},
                        "interview_type": {"type": "string", "description": "Тип (онлайн/офис)"},
                        "duration": {"type": "string", "description": "Длительность в минутах"}
                    },
                    "required": ["candidate_name", "position", "interview_date", "interview_time"]
                }
            }
        },
        
        # === Воркфлоу ===
        {
            "type": "function",
            "function": {
                "name": "onboard_employee",
                "description": "Запустить полный процесс онбординга: документы + приветственное сообщение.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "employee_name": {"type": "string", "description": "Имя сотрудника"},
                        "position": {"type": "string", "description": "Должность"},
                        "start_date": {"type": "string", "description": "Дата выхода"},
                        "salary": {"type": "string", "description": "Зарплата"},
                        "buddy_name": {"type": "string", "description": "Имя buddy"},
                        "manager_name": {"type": "string", "description": "Имя руководителя"}
                    },
                    "required": ["employee_name", "position", "start_date"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "process_candidate",
                "description": "Обработать нового кандидата: сохранить в базу + найти подходящие вакансии.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Имя кандидата"},
                        "position": {"type": "string", "description": "Желаемая позиция"},
                        "email": {"type": "string", "description": "Email"},
                        "phone": {"type": "string", "description": "Телефон"},
                        "skills": {"type": "array", "items": {"type": "string"}, "description": "Навыки"},
                        "experience": {"type": "string", "description": "Опыт работы"}
                    },
                    "required": ["name", "position"]
                }
            }
        },
        
        # === Изображения ===
        {
            "type": "function",
            "function": {
                "name": "image_generate",
                "description": "Сгенерировать изображение через AI по описанию.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "Описание изображения для генерации"}
                    },
                    "required": ["prompt"]
                }
            }
        },
        
        # === Память ===
        {
            "type": "function",
            "function": {
                "name": "memory_remember",
                "description": "Сохранить информацию в долгосрочную память.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string", "description": "Ключ для запоминания"},
                        "value": {"type": "string", "description": "Значение для сохранения"}
                    },
                    "required": ["key", "value"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "memory_recall",
                "description": "Вспомнить информацию из памяти.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string", "description": "Ключ для поиска (опционально)"}
                    }
                }
            }
        },
    ]
    return tools


# ============================================================================
# ВЫПОЛНЕНИЕ ИНСТРУМЕНТОВ
# ============================================================================

def execute_tool(tool_name: str, params: dict, user_id: int = None) -> str:
    """Выполнение инструментов"""
    global candidate_id_counter, vacancy_id_counter
    
    try:
        # === Календарь ===
        if tool_name == "get_calendar_events":
            if not GOOGLE_AVAILABLE:
                return "❌ Google Calendar не доступен. Используйте /connect для подключения."
            
            days = params.get('days', 7)
            if not user_id:
                return "❌ Календарь не подключён. Используйте /connect"
            
            credentials = google_auth.get_credentials(user_id)
            if not credentials:
                return "❌ Календарь не подключён. Используйте /connect для авторизации."
            
            message, events = calendar_manager.list_events(user_id, days=days)
            return message
        
        # === Кандидаты ===
        if tool_name == "save_candidate":
            candidate_id_counter += 1
            cid = candidate_id_counter
            candidates_db[cid] = {
                "id": cid,
                "name": params.get('name'),
                "email": params.get('email'),
                "phone": params.get('phone'),
                "position": params.get('position'),
                "skills": params.get('skills', []),
                "experience": params.get('experience'),
                "salary_expectation": params.get('salary_expectation'),
                "source": params.get('source'),
                "notes": params.get('notes'),
                "rating": params.get('rating'),
                "status": "new",
                "created_at": datetime.now().isoformat()
            }
            return f"✅ Кандидат **{params.get('name')}** сохранён в базу (ID: {cid})"
        
        elif tool_name == "search_candidates":
            query = params.get('query', '').lower()
            status = params.get('status')
            position = params.get('position', '').lower()
            limit = params.get('limit', 10)
            
            results = []
            for c in candidates_db.values():
                if query and query not in c.get('name', '').lower():
                    if query not in c.get('position', '').lower():
                        continue
                if status and c.get('status') != status:
                    continue
                if position and position not in c.get('position', '').lower():
                    continue
                results.append(c)
            
            if not results:
                return "Кандидаты не найдены."
            
            response = f"📋 Найдено {len(results)} кандидатов:\n\n"
            for c in results[:limit]:
                response += f"• **{c['name']}** - {c.get('position', 'N/A')} ({c.get('status', 'new')})\n"
            return response
        
        elif tool_name == "update_candidate_status":
            name = params.get('candidate_name', '').lower()
            new_status = params.get('status')
            
            for cid, c in candidates_db.items():
                if name in c.get('name', '').lower():
                    c['status'] = new_status
                    return f"✅ Статус кандидата **{c['name']}** обновлён на '{new_status}'"
            
            return f"❌ Кандидат '{params.get('candidate_name')}' не найден"
        
        # === Вакансии ===
        elif tool_name == "create_vacancy":
            vacancy_id_counter += 1
            vid = vacancy_id_counter
            vacancies_db[vid] = {
                "id": vid,
                "title": params.get('title'),
                "department": params.get('department'),
                "description": params.get('description'),
                "requirements": params.get('requirements'),
                "salary_range": params.get('salary_range'),
                "status": "open",
                "created_at": datetime.now().isoformat()
            }
            return f"✅ Вакансия **{params.get('title')}** создана (ID: {vid})"
        
        elif tool_name == "list_vacancies":
            if not vacancies_db:
                return "Открытых вакансий нет."
            
            response = f"📋 Открытые вакансии ({len(vacancies_db)}):\n\n"
            for v in vacancies_db.values():
                if v.get('status') == 'open':
                    response += f"• **{v['title']}** - {v.get('department', 'N/A')}\n"
                    if v.get('salary_range'):
                        response += f"  💰 {v['salary_range']}\n"
            return response
        
        # === Документы ===
        elif tool_name == "create_offer":
            return f"""📄 **ОФФЕР О ПРИЁМЕ НА РАБОТУ**

**Кандидат:** {params.get('candidate_name')}
**Должность:** {params.get('position')}
**Зарплата:** {params.get('salary')}
**Дата выхода:** {params.get('start_date')}
**Отдел:** {params.get('department', 'Не указан')}

---

Уважаемый(ая) {params.get('candidate_name')}!

Мы рады предложить Вам позицию {params.get('position')} в нашей компании.

**Условия:**
- Зарплата: {params.get('salary')}
- Дата выхода: {params.get('start_date')}

Пожалуйста, подтвердите получение данного оффера.

С уважением,
HR-команда"""
        
        elif tool_name == "create_welcome":
            return f"""🎉 **WELCOME-ДОКУМЕНТ**

**Сотрудник:** {params.get('candidate_name')}
**Должность:** {params.get('position')}
**Дата выхода:** {params.get('start_date')}
**Buddy:** {params.get('buddy_name', 'Будет назначен')}
**Руководитель:** {params.get('manager_name', 'Будет назначен')}

---

Добро пожаловать в команду, {params.get('candidate_name')}! 🎊

**Первый день:**
- Прийти к 10:00
- Получить пропуск на ресепшн
- Встретиться с buddy: {params.get('buddy_name', 'будет назначен')}

**Первая неделя:**
- Знакомство с командой
- Настройка рабочего места
- Обучение процессам

Мы рады, что Вы с нами! 🚀"""
        
        elif tool_name == "create_scorecard":
            return f"""📊 **SCORECARD - КАРТА ОЦЕНКИ КАНДИДАТА**

**Кандидат:** {params.get('candidate_name')}
**Должность:** {params.get('position')}
**Интервьюер:** {params.get('interviewer')}
**Дата:** {datetime.now().strftime('%d.%m.%Y')}

---

**Сильные стороны:**
{params.get('strengths', 'Не указаны')}

**Слабые стороны:**
{params.get('weaknesses', 'Не указаны')}

**Рекомендация:** {params.get('recommendation', 'Требуется обсуждение')}

---

**Общая оценка:** _Заполнить после интервью_"""
        
        elif tool_name == "create_rejection":
            return f"""📧 **ПИСЬМО С ОТКАЗОМ**

Уважаемый(ая) {params.get('candidate_name')}!

Благодарим Вас за интерес к вакансии **{params.get('position')}** в нашей компании.

Мы внимательно рассмотрели Вашу кандидатуру. К сожалению, в данный момент мы не готовы сделать Вам предложение.

{f'Причина: {params.get("reason")}' if params.get('reason') else ''}

Мы сохраним Ваше резюме в нашей базе и свяжемся с Вами, если появится подходящая вакансия.

Желаем успехов в поиске работы!

С уважением,
HR-команда"""
        
        elif tool_name == "create_interview_invite":
            return f"""📅 **ПРИГЛАШЕНИЕ НА ИНТЕРВЬЮ**

**Кандидат:** {params.get('candidate_name')}
**Должность:** {params.get('position')}
**Дата:** {params.get('interview_date')}
**Время:** {params.get('interview_time')}
**Формат:** {params.get('interview_type', 'Онлайн')}
**Длительность:** {params.get('duration', '60')} минут

---

Уважаемый(ая) {params.get('candidate_name')}!

Приглашаем Вас на интервью на позицию {params.get('position')}.

Пожалуйста, подтвердите возможность присутствия.

До встречи! 🤝"""
        
        # === Воркфлоу ===
        elif tool_name == "onboard_employee":
            results = []
            
            # Welcome документ
            welcome = f"📄 Welcome-документ для {params.get('employee_name')} создан"
            results.append(welcome)
            
            # Оффер если есть зарплата
            if params.get('salary'):
                offer = f"📄 Оффер с зарплатой {params.get('salary')} создан"
                results.append(offer)
            
            return f"✅ **Онбординг завершён!**\n\n" + "\n".join(results)
        
        elif tool_name == "process_candidate":
            # Сохраняем кандидата
            candidate_id_counter += 1
            cid = candidate_id_counter
            candidates_db[cid] = {
                "id": cid,
                "name": params.get('name'),
                "email": params.get('email'),
                "phone": params.get('phone'),
                "position": params.get('position'),
                "skills": params.get('skills', []),
                "experience": params.get('experience'),
                "status": "new",
                "created_at": datetime.now().isoformat()
            }
            
            # Ищем подходящие вакансии
            matching = []
            for v in vacancies_db.values():
                if params.get('position', '').lower() in v.get('title', '').lower():
                    matching.append(v)
            
            result = f"✅ Кандидат **{params.get('name')}** сохранён (ID: {cid})\n"
            if matching:
                result += f"🔍 Найдено {len(matching)} подходящих вакансий"
            else:
                result += "📋 Подходящих вакансий пока нет"
            
            return result
        
        # === Изображения ===
        elif tool_name == "image_generate":
            return f"🎨 Генерация изображения: '{params.get('prompt')}'\n\n💡 Для реальной генерации изображений подключите z-ai-web-dev-sdk"
        
        # === Память ===
        elif tool_name == "memory_remember":
            key = params.get('key')
            value = params.get('value')
            memory_db[key] = value
            return f"🧠 Запомнено: **{key}** = {value}"
        
        elif tool_name == "memory_recall":
            key = params.get('key')
            if key:
                value = memory_db.get(key)
                if value:
                    return f"🧠 Вспомнено: **{key}** = {value}"
                return f"❌ Не найдено в памяти: {key}"
            else:
                if not memory_db:
                    return "Память пуста"
                result = "🧠 **Сохранённые данные:**\n\n"
                for k, v in memory_db.items():
                    result += f"• {k}: {v}\n"
                return result
        
        else:
            return f"❌ Неизвестная функция: {tool_name}"
    
    except Exception as e:
        logger.error(f"Tool execution error: {e}")
        return f"❌ Ошибка выполнения: {str(e)}"


# ============================================================================
# ОБРАБОТЧИКИ TELEGRAM
# ============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    chat_id = update.effective_chat.id
    if chat_id in user_conversations:
        del user_conversations[chat_id]
    
    await update.message.reply_text(
        "👋 Привет! Я **HRик** — твой ИИ-ассистент для HR!\n\n"
        "🤖 Я могу помочь с:\n\n"
        "👥 **Кандидаты:**\n"
        "• Сохранение и поиск кандидатов\n"
        "• Управление статусами\n\n"
        "📋 **Вакансии:**\n"
        "• Создание и просмотр вакансий\n\n"
        "📅 **Календарь (Google Calendar):**\n"
        "/connect - подключить Google Calendar\n"
        "/calendar - показать события\n"
        "/disconnect - отключить календарь\n\n"
        "📄 **Документы:**\n"
        "• Офферы и welcome-письма\n"
        "• Scorecards и приглашения\n\n"
        "🔄 **Воркфлоу:**\n"
        "• Полный онбординг одной командой\n\n"
        "💡 **Примеры:**\n"
        "• 'Сохрани кандидата Иван, Python Developer'\n"
        "• 'Создай оффер для Мария, QA, 2000 USDT'\n"
        "• 'Какие у меня встречи на неделе?'\n\n"
        "Просто напиши мне!",
        parse_mode='Markdown'
    )


async def connect_google(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для подключения Google Calendar"""
    if not GOOGLE_AVAILABLE:
        await update.message.reply_text(
            "❌ Google Calendar интеграция недоступна.\n"
            "Для работы требуется настроить Google OAuth credentials."
        )
        return
    
    user_id = update.effective_user.id
    
    # Проверяем, уже подключен ли календарь
    credentials = google_auth.get_credentials(user_id)
    if credentials:
        await update.message.reply_text(
            "✅ Ваш Google Calendar уже подключен!\n\n"
            "Используйте:\n"
            "/calendar - для просмотра событий\n"
            "/disconnect - для отключения"
        )
        return
    
    # Генерируем OAuth URL
    auth_url = google_auth.get_auth_url(user_id)
    
    await update.message.reply_text(
        "📅 Подключение Google Calendar\n\n"
        "Шаг 1: Перейдите по ссылке ниже\n"
        "Шаг 2: Войдите в Google аккаунт\n"
        "Шаг 3: Нажмите 'Разрешить'\n"
        "Шаг 4: Скопируйте код\n"
        "Шаг 5: Отправьте мне код\n\n"
        f"🔗 Ссылка:\n{auth_url}\n\n"
        "После получения кода просто отправьте его мне в чат (без команд).",
        disable_web_page_preview=True
    )
    
    # Сохраняем состояние "ожидает код"
    context.user_data['waiting_for_auth_code'] = True


async def show_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать события календаря"""
    if not GOOGLE_AVAILABLE:
        await update.message.reply_text("❌ Google Calendar недоступен.")
        return
    
    user_id = update.effective_user.id
    
    # Проверяем авторизацию
    credentials = google_auth.get_credentials(user_id)
    if not credentials:
        await update.message.reply_text(
            "❌ Google Calendar не подключен.\n"
            "Используйте /connect для подключения."
        )
        return
    
    # Определяем количество дней
    days = 7
    if context.args and context.args[0].isdigit():
        days = int(context.args[0])
    
    await update.message.reply_text("⏳ Загружаю события календаря...")
    
    message, events = calendar_manager.list_events(user_id, days=days)
    await update.message.reply_text(
        message,
        parse_mode='Markdown',
        disable_web_page_preview=True
    )


async def disconnect_google(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отключить Google Calendar"""
    if not GOOGLE_AVAILABLE:
        await update.message.reply_text("❌ Google Calendar недоступен.")
        return
    
    user_id = update.effective_user.id
    google_auth.revoke_credentials(user_id)
    
    await update.message.reply_text(
        "✅ Google Calendar отключен.\n"
        "Используйте /connect для повторного подключения."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений через Mistral Agent"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    user_input = update.message.text
    
    # Проверяем, ожидаем ли мы код авторизации Google
    if context.user_data.get('waiting_for_auth_code') and GOOGLE_AVAILABLE:
        text = update.message.text.strip()
        
        # Пытаемся сохранить код
        success = google_auth.save_credentials_from_code(user_id, text.strip())
        
        if success:
            await update.message.reply_text(
                "✅ Google Calendar успешно подключен!\n\n"
                "Теперь вы можете:\n"
                "📅 /calendar - просмотреть события\n"
                "💬 Или просто спросите: 'Какие у меня встречи сегодня?'"
            )
            context.user_data['waiting_for_auth_code'] = False
        else:
            await update.message.reply_text(
                "❌ Ошибка при сохранении кода.\n\n"
                "Возможные причины:\n"
                "- Неверный код\n"
                "- Код уже использован\n"
                "- Код истек (действителен 10 минут)\n\n"
                "Попробуйте еще раз: /connect"
            )
        return
    
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    
    try:
        # Проверяем, есть ли уже conversation
        if chat_id in user_conversations:
            response = mistral_client.beta.conversations.append(
                conversation_id=user_conversations[chat_id],
                inputs=user_input
            )
        else:
            # Создаём агента и начинаем разговор
            agent = mistral_client.beta.agents.create(
                model="mistral-small-latest",
                name="HR Assistant Agent",
                description="Полноценный HR AI-агент",
                instructions=SYSTEM_PROMPT,
                tools=get_all_tools(),
                completion_args={"temperature": 0.7}
            )
            response = mistral_client.beta.conversations.start(
                agent_id=agent.id,
                inputs=user_input
            )
        
        # Сохраняем conversation_id
        user_conversations[chat_id] = response.conversation_id
        
        # Обрабатываем function calls
        tool_calls = [out for out in response.outputs if out.type == 'function.call']
        
        if tool_calls:
            tool_results = []
            
            for tool_call in tool_calls:
                function_name = tool_call.name
                raw_args = tool_call.arguments if hasattr(tool_call, 'arguments') else {}
                if isinstance(raw_args, str):
                    function_params = json.loads(raw_args)
                else:
                    function_params = raw_args if raw_args else {}
                
                logger.info(f"Tool call: {function_name} with params: {function_params}")
                
                # Выполняем функцию
                result = execute_tool(function_name, function_params, user_id)
                
                tool_results.append({
                    "type": "function.result",
                    "tool_call_id": tool_call.tool_call_id,
                    "result": result
                })
            
            # Отправляем результаты обратно
            response = mistral_client.beta.conversations.append(
                conversation_id=user_conversations[chat_id],
                inputs=tool_results
            )
        
        # Получаем ответ
        message_outputs = [out for out in response.outputs if out.type in ['message.output', 'message.content']]
        
        if not message_outputs:
            for out in response.outputs:
                if hasattr(out, 'content') and out.content:
                    message_outputs = [out]
                    break
        
        if message_outputs:
            content = message_outputs[-1].content
            if isinstance(content, str):
                reply = content
            elif isinstance(content, list):
                reply = ''.join([chunk.text for chunk in content if hasattr(chunk, 'text')])
            else:
                reply = str(content)
        else:
            reply = "Не удалось получить ответ. Попробуйте /start для сброса разговора."
        
        # Отправляем ответ
        try:
            await update.message.reply_text(reply, parse_mode='Markdown')
        except BadRequest:
            await update.message.reply_text(reply)
            
    except Exception as e:
        logger.error(f"Error in handle_message: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка голосовых сообщений"""
    await update.message.reply_text(
        "🎤 Голосовые сообщения пока не поддерживаются в этой версии. "
        "Пожалуйста, отправьте текст."
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка документов"""
    await update.message.reply_text(
        "📄 Обработка документов пока не поддерживается в этой версии. "
        "Пожалуйста, отправьте текст резюме."
    )


# ============================================================================
# ЗАПУСК
# ============================================================================

if __name__ == '__main__':
    logger.info("=" * 50)
    logger.info("🚀 Starting HR Bot (Full Version)")
    logger.info("=" * 50)
    logger.info(f"Python: {os.sys.version}")
    logger.info(f"Mistral API Key: {'SET' if MISTRAL_API_KEY else 'NOT SET'}")
    logger.info(f"Telegram Token: {'SET' if TELEGRAM_BOT_TOKEN else 'NOT SET'}")
    logger.info(f"Google Calendar: {'AVAILABLE' if GOOGLE_AVAILABLE else 'NOT AVAILABLE'}")
    
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Команды
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('connect', connect_google))
    application.add_handler(CommandHandler('calendar', show_calendar))
    application.add_handler(CommandHandler('disconnect', disconnect_google))
    
    # Сообщения
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    logger.info("✅ Bot ready, starting polling...")
    application.run_polling()
