import logging
import os
import asyncio
import json
import fitz  # PyMuPDF
from docx import Document
import base64
from pathlib import Path
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from telegram.error import BadRequest
from mistralai import Mistral
import database as db
import google_auth
from google_calendar_manager import GoogleCalendarManager
from notifications import notification_loop
import google_sheets

# Импорт ядра агента
from agent_core import hr_agent as hr_agent_core, TaskStatus
from document_generator import (
    create_offer_document, create_welcome_document,
    create_scorecard_document, create_rejection_letter,
    create_interview_invite
)

# Импорт MCP системы (как в OpenClaw)
from mcp_client import mcp_orchestrator, MCPServerConfig, MCPTransport

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# API Ключи - используются переменные окружения или значения по умолчанию
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "AEE3rpaceKHZzBtbVKnN9CWoNdpjlp2l")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8399347076:AAFLtRxXEKESWuTQb19vc6mhMQph7rHxsLg")

# Системный промпт для агента - расширенный
AGENT_INSTRUCTIONS = """
Ты — **HRик HуяRік**, экспертный ИИ-ассистент для HR-команды и рекрутеров (Senior HR Business Partner & Lead Recruiter). 

Ты — **полноценный AI-агент** с доступом к инструментам, памяти и автономным рабочим процессам. Ты можешь выполнять многошаговые задачи, создавать документы и управлять HR-процессами.

Ты дружелюбный, профессиональный и всегда готов помочь. Используй эмодзи умеренно (1-2 на сообщение) для создания приятной атмосферы. Иногда можешь представляться своим именем - HRик HуяRік.

## 🎯 Твои ключевые возможности:

### 1. УПРАВЛЕНИЕ КАНДИДАТАМИ
- **save_candidate** - сохранить кандидата в базу данных
- **search_candidates** - поиск кандидатов по имени, статусу, позиции
- **update_candidate_status** - обновить статус кандидата (new → screening → interview → offer → hired/rejected)

### 2. УПРАВЛЕНИЕ ВАКАНСИЯМИ
- **create_vacancy** - создать новую вакансию
- **list_vacancies** - показать открытые вакансии

### 3. ТАБЛИЦА СОТРУДНИКОВ (Google Sheets)
- **add_employee** - добавить сотрудника в таблицу учёта
- **list_employees** - показать список сотрудников
- **search_employee** - найти сотрудника по имени
- **update_employee** - обновить данные сотрудника

### 4. КАЛЕНДАРЬ (Google Calendar)
- **get_calendar_events** - получить события календаря

### 5. СОЗДАНИЕ ДОКУМЕНТОВ
- **create_offer** - создать оффер о приёме на работу
- **create_welcome** - создать welcome-документ для нового сотрудника
- **create_scorecard** - создать карту оценки кандидата
- **create_rejection** - создать письмо с отказом
- **create_interview_invite** - создать приглашение на интервью

### 6. АВТОНОМНЫЕ ВОРКФЛОУ
- **onboard_employee** - полный процесс онбординга (добавление в таблицу + документы)
- **process_candidate** - обработка нового кандидата (сохранение + матчинг с вакансиями)
- **start_workflow** - запустить предопределённый рабочий процесс
- **get_workflow_status** - проверить статус выполнения воркфлоу

### 7. 🆕 РАСШИРЕННЫЕ НАВЫКИ (как в OpenClaw)

**📷 Генерация изображений:**
- **image_generate** - сгенерировать изображение через AI по описанию
- **image_describe** - описать содержимое изображения
- **image_list** - показать сгенерированные изображения

**📁 Работа с файлами:**
- **fs_read_file** - прочитать файл
- **fs_write_file** - записать в файл
- **fs_list_dir** - показать содержимое папки
- **fs_search** - найти файлы

**💻 Терминал:**
- **terminal_execute** - выполнить shell команду
- **terminal_run_script** - запустить Python/Bash скрипт

**🌐 Браузер:**
- **browser_search** - поиск в интернете
- **browser_fetch** - получить содержимое веб-страницы

**🧠 Память:**
- **memory_remember** - сохранить информацию в долгосрочную память
- **memory_recall** - вспомнить информацию из памяти

**📧 Коммуникация:**
- **comm_send_email** - отправить email
- **comm_slack_message** - отправить в Slack
- **comm_discord_message** - отправить в Discord

**📊 Аналитика:**
- **analytics_create_report** - создать отчёт
- **analytics_create_chart** - создать график

**🎤 Голосовые сообщения:**
- **voice_transcribe** - транскрибировать аудио в текст
- **voice_speak** - озвучить текст (TTS)

## 📋 Примеры запросов:

**Кандидаты:**
- "Сохрани кандидата Иван Петров, позиция Python Developer, email ivan@mail.ru"
- "Найди кандидатов на позицию разработчика"
- "Обнови статус кандидата Иван на 'interview'"

**Сотрудники:**
- "Добавь сотрудника Иван Иванов, должность Python Developer, дата выхода 01.03.2025"
- "Покажи список сотрудников за март"
- "Обнови рекомендацию для Иван: прошел ИС"

**Документы:**
- "Создай оффер для кандидата Иван Петров на позицию Senior Python Developer, зарплата 3000 USDT, выход 15 марта"
- "Создай welcome-документ для нового сотрудника Мария Иванова"
- "Создай приглашение на интервью для Алексей, завтра в 14:00"

**Изображения:**
- "Сгенерируй изображение: логотип компании в стиле минимализм"
- "Нарисуй картинку: команда разработчиков за работой"
- "Создай изображение: поздравительная открытка для сотрудника"

**Воркфлоу:**
- "Запусти онбординг для Иван Петров, позиция Developer, дата выхода 01.04.2025"
- "Запусти обработку кандидата: Сергей, позиция QA, email sergey@mail.ru"

**Файлы и память:**
- "Сохрани в память: мой любимый проект - Project X"
- "Что я говорил про проект?"
- "Создай файл notes.md с заметками"

## 🔄 Автономное поведение:
Когда пользователь просит выполнить сложную задачу (например, "оформи нового сотрудника"), ты **автоматически**:
1. Определяешь необходимые шаги
2. Вызываешь нужные функции последовательно
3. Сообщаешь о прогрессе
4. Предоставляешь финальный результат

## Формат общения:
- Тон: Дружелюбный, профессиональный, эмпатичный
- Используй **жирный текст** для ключевых моментов
- Используй списки для структурирования
- Эмодзи: 1-2 на сообщение (✅ 📊 💡 🎯 📄 🖼️)
- Markdown обязателен для улучшения читаемости
- Всегда задавай уточняющие вопросы если не хватает данных

## ВАЖНО:
- Для создания документов ОБЯЗАТЕЛЬНО нужны: имя кандидата, позиция, дата
- Для оффера ОБЯЗАТЕЛЬНО нужна зарплата
- Для генерации изображений используй **image_generate** с параметром prompt
- Если пользователь не указал все данные - спроси недостающее
- Всегда подтверждай выполнение действий
- Используй веб-поиск для актуальной информации о зарплатах и трендах
"""

# Инициализация клиента Mistral
mistral_client = Mistral(api_key=MISTRAL_API_KEY)

# Глобальные переменные
mistral_agent = None  # Mistral Agent (переименовано для избежания конфликта)
calendar_manager = GoogleCalendarManager()

# Хранилище conversation_id для каждого пользователя
user_conversations = {}


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
        
        # === Сотрудники (Google Sheets) ===
        {
            "type": "function",
            "function": {
                "name": "add_employee",
                "description": "Добавить нового сотрудника в таблицу учёта. Использовать когда пользователь хочет добавить нового сотрудника.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "employee_name": {"type": "string", "description": "Полное имя сотрудника"},
                        "role": {"type": "string", "description": "Должность"},
                        "recruiter": {"type": "string", "description": "Имя рекрутера (по умолчанию '-//-')"},
                        "start_date": {"type": "string", "description": "Дата выхода в формате DD/MM/YYYY"},
                        "salary": {"type": "string", "description": "Зарплата (например, '1500 USDT')"},
                        "card_link": {"type": "string", "description": "Ссылка на карточку сотрудника"}
                    },
                    "required": ["employee_name", "role"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "list_employees",
                "description": "Показать список сотрудников из таблицы. Можно фильтровать по месяцу.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "month": {"type": "string", "description": "Фильтр по месяцу (Март, Апрель и т.д.)"}
                    }
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "search_employee",
                "description": "Найти сотрудника по имени в таблице.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Имя или часть имени сотрудника"}
                    },
                    "required": ["name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "update_employee",
                "description": "Обновить данные сотрудника в таблице.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Имя сотрудника"},
                        "field": {"type": "string", "description": "Поле: 'рекрутер', 'дата выхода', 'сумма', 'рекомендация', 'карточка'"},
                        "value": {"type": "string", "description": "Новое значение"}
                    },
                    "required": ["name", "field", "value"]
                }
            }
        },
        
        # === Кандидаты (База данных) ===
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
                        "candidate_id": {"type": "integer", "description": "ID кандидата"},
                        "status": {"type": "string", "description": "Новый статус", "enum": ["new", "screening", "interview", "offer", "hired", "rejected"]}
                    },
                    "required": ["candidate_id", "status"]
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
                        "salary_range": {"type": "string", "description": "Зарплатная вилка"},
                        "hiring_manager": {"type": "string", "description": "Нанимающий менеджер"}
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
                "description": "Создать оффер о приёме на работу в Google Docs.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "candidate_name": {"type": "string", "description": "Имя кандидата"},
                        "position": {"type": "string", "description": "Должность"},
                        "salary": {"type": "string", "description": "Зарплата"},
                        "start_date": {"type": "string", "description": "Дата выхода"},
                        "department": {"type": "string", "description": "Отдел"},
                        "hr_name": {"type": "string", "description": "Имя HR"},
                        "company_name": {"type": "string", "description": "Название компании"}
                    },
                    "required": ["candidate_name", "position", "salary", "start_date"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "create_welcome",
                "description": "Создать welcome-документ для нового сотрудника в Google Docs.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "candidate_name": {"type": "string", "description": "Имя сотрудника"},
                        "position": {"type": "string", "description": "Должность"},
                        "start_date": {"type": "string", "description": "Дата выхода"},
                        "start_time": {"type": "string", "description": "Время выхода"},
                        "buddy_name": {"type": "string", "description": "Имя buddy"},
                        "manager_name": {"type": "string", "description": "Имя руководителя"},
                        "hr_name": {"type": "string", "description": "Имя HR"}
                    },
                    "required": ["candidate_name", "position", "start_date"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "create_scorecard",
                "description": "Создать карту оценки кандидата после интервью в Google Docs.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "candidate_name": {"type": "string", "description": "Имя кандидата"},
                        "position": {"type": "string", "description": "Должность"},
                        "interviewer": {"type": "string", "description": "Интервьюер"},
                        "competencies": {"type": "object", "description": "Оценки по компетенциям"}
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
                        "hr_name": {"type": "string", "description": "Имя HR"},
                        "keep_in_touch": {"type": "string", "description": "Продолжить ли общение"}
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
                "description": "Запустить полный процесс онбординга: добавление в таблицу + создание welcome-документа + создание оффера.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "employee_name": {"type": "string", "description": "Имя сотрудника"},
                        "position": {"type": "string", "description": "Должность"},
                        "start_date": {"type": "string", "description": "Дата выхода"},
                        "recruiter": {"type": "string", "description": "Рекрутер"},
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
                        "experience": {"type": "string", "description": "Опыт работы"},
                        "source": {"type": "string", "description": "Источник"}
                    },
                    "required": ["name", "position"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "start_workflow",
                "description": "Запустить предопределённый рабочий процесс. Доступные: 'onboard_employee', 'process_candidate', 'interview_pipeline', 'reject_candidate', 'make_offer'.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "workflow_name": {
                            "type": "string",
                            "description": "Название воркфлоу",
                            "enum": ["onboard_employee", "process_candidate", "interview_pipeline", "reject_candidate", "make_offer"]
                        }
                    },
                    "required": ["workflow_name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_workflow_status",
                "description": "Получить статус выполнения воркфлоу.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "description": "ID задачи"}
                    },
                    "required": ["task_id"]
                }
            }
        }
    ]
    return tools


def initialize_agent():
    """Создание Mistral агента при старте бота"""
    global mistral_agent
    
    # Инициализируем MCP оркестратор
    asyncio.get_event_loop().run_until_complete(mcp_orchestrator.initialize())
    
    # Настраиваем ToolExecutor (как в OpenClaw)
    from mcp_client import setup_tool_executor
    from tool_executor import tool_executor
    
    executor = setup_tool_executor()
    
    try:
        # Объединяем базовые инструменты с MCP инструментами через ToolExecutor
        base_tools = get_all_tools()
        mcp_tools = mcp_orchestrator.get_all_tools()
        executor_tools = executor.build_tools_for_mistral()
        all_tools = base_tools + mcp_tools
        
        # Добавляем промпт навыков к инструкциям (как buildWorkspaceSkillsPrompt в OpenClaw)
        skills_prompt = executor.get_skills_prompt()
        full_instructions = AGENT_INSTRUCTIONS + "\n\n" + skills_prompt
        
        mistral_agent = mistral_client.beta.agents.create(
            model="mistral-small-latest",
            name="HR Assistant Agent",
            description="Полноценный HR AI-агент с MCP инструментами как в OpenClaw",
            instructions=full_instructions,
            tools=all_tools,
            completion_args={
                "temperature": 0.7,
            }
        )
        logging.info(f"Mistral Agent created with ID: {mistral_agent.id}")
        logging.info(f"Loaded {len(mcp_orchestrator.list_skills())} MCP servers with {len(mcp_tools)} tools")
        logging.info(f"ToolExecutor registered {len(executor.registry.tools)} tools")
    except Exception as e:
        logging.error(f"Failed to create Mistral agent: {e}")
        raise


def format_markdown(text):
    """Форматирование текста для Telegram (поддержка Markdown)"""
    return text


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    # Очищаем conversation_id при /start
    if chat_id in user_conversations:
        del user_conversations[chat_id]
    
    await update.message.reply_text(
        "👋 Привет! Я *HRик HуяRік* — твой экспертный ИИ-агент для HR!\n\n"
        "🤖 **Я — полноценный AI-агент с инструментами:**\n\n"
        "👥 **Кандидаты:**\n"
        "• Сохранение и поиск кандидатов\n"
        "• Управление статусами\n\n"
        "📊 **Сотрудники (Google Sheets):**\n"
        "• Добавление в таблицу\n"
        "• Поиск и обновление данных\n\n"
        "📄 **Документы (Google Docs):**\n"
        "• Офферы и welcome-письма\n"
        "• Scorecards и приглашения\n\n"
        "🔄 **Автономные воркфлоу:**\n"
        "• Полный онбординг одной командой\n"
        "• Обработка кандидатов\n\n"
        "📅 **Календарь:**\n"
        "/connect - подключить Google Calendar\n"
        "/calendar - показать события\n\n"
        "💡 *Примеры:*\n"
        "• 'Запусти онбординг для Иван, Developer, 01.04.2025'\n"
        "• 'Создай оффер для Мария, QA, 2000 USDT'\n"
        "• 'Сохрани кандидата Алексей, Python Developer'\n\n"
        "Пришли мне PDF резюме или задай вопрос!",
        parse_mode='Markdown'
    )


async def connect_google(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для подключения Google Calendar"""
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
        "После получения кода просто отправьте его мне в чат (без команд)."
    )
    
    # Сохраняем состояние "ожидает код"
    context.user_data['waiting_for_auth_code'] = True


async def show_skills(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать доступные MCP навыки (как в OpenClaw)"""
    skills_list = mcp_orchestrator.list_skills()
    
    message = "🦞 **MCP Skills (как в OpenClaw):**\n\n"
    
    # Локальные серверы
    local_skills = [s for s in skills_list if s["type"] == "local"]
    if local_skills:
        message += "**📦 Встроенные MCP серверы:**\n"
        for skill in local_skills:
            status = "✅" if skill["enabled"] else "❌"
            message += f"{status} **{skill['name']}** - {skill['description']}\n"
            message += f"   └ {skill['tools_count']} инструментов\n"
    
    # Внешние серверы
    external_skills = [s for s in skills_list if s["type"] == "external"]
    if external_skills:
        message += "\n**🔌 Внешние MCP серверы:**\n"
        for skill in external_skills:
            status = "🟢" if skill.get("connected") else "🔴"
            message += f"{status} **{skill['name']}** - {skill['tools_count']} инструментов\n"
    
    message += "\n**📋 Доступные MCP серверы для подключения:**\n"
    message += "• **filesystem** - работа с файлами\n"
    message += "• **github** - интеграция с GitHub\n"
    message += "• **postgres** - работа с PostgreSQL\n"
    message += "• **office-mcp** - Office документы\n"
    
    message += "\n💡 *MCP (Model Context Protocol) — стандарт для подключения навыков.*\n"
    message += "Настройте mcp_config.json для добавления внешних серверов."
    message += "\n\n/mcp_add <name> <command> - добавить сервер"
    message += "\n/mcp_remove <name> - удалить сервер"
    
    await update.message.reply_text(message, parse_mode='Markdown')


async def show_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать события календаря"""
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
    user_id = update.effective_user.id
    
    google_auth.revoke_credentials(user_id)
    
    await update.message.reply_text(
        "✅ Google Calendar отключен.\n"
        "Используйте /connect для повторного подключения."
    )


async def mcp_add_server(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавить MCP сервер"""
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "📋 **Добавление MCP сервера:**\n\n"
            "Формат: `/mcp_add <name> <command>`\n\n"
            "Примеры:\n"
            "• `/mcp_add filesystem npx -y @modelcontextprotocol/server-filesystem /tmp`\n"
            "• `/mcp_add github npx -y @modelcontextprotocol/server-github`\n\n"
            "Или отредактируйте mcp_config.json напрямую.",
            parse_mode='Markdown'
        )
        return
    
    name = context.args[0]
    command = context.args[1]
    args = context.args[2:] if len(context.args) > 2 else []
    
    config = MCPServerConfig(
        name=name,
        command=command,
        args=args,
        transport=MCPTransport.STDIO,
        enabled=True
    )
    
    success = await mcp_orchestrator.add_external_server(config)
    
    if success:
        await update.message.reply_text(
            f"✅ MCP сервер **{name}** добавлен и подключён!",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            f"❌ Не удалось подключить сервер **{name}**. Проверьте команду.",
            parse_mode='Markdown'
        )


async def mcp_remove_server(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удалить MCP сервер"""
    if not context.args:
        await update.message.reply_text(
            "📋 Формат: `/mcp_remove <name>`",
            parse_mode='Markdown'
        )
        return
    
    name = context.args[0]
    success = mcp_orchestrator.remove_external_server(name)
    
    if success:
        await update.message.reply_text(f"✅ MCP сервер **{name}** удалён.", parse_mode='Markdown')
    else:
        await update.message.reply_text(f"❌ Сервер **{name}** не найден.", parse_mode='Markdown')


async def execute_mcp_tool(tool_name: str, params: dict) -> str:
    """Выполнение MCP инструмента через ToolExecutor (как в OpenClaw)"""
    from tool_executor import tool_executor
    
    result = await tool_executor.execute(tool_name, params)
    
    if result.success:
        if isinstance(result.result, dict):
            if result.result.get("success"):
                if "content" in result.result:
                    return result.result["content"]
                elif "message" in result.result:
                    return result.result["message"]
                elif "filename" in result.result:
                    return f"✅ Файл создан: {result.result['filename']}"
            return json.dumps(result.result, ensure_ascii=False, indent=2)
        return str(result.result)
    else:
        return f"❌ Ошибка: {result.error}"


async def execute_tool_async(tool_name: str, params: dict, user_id: int = None) -> str:
    """
    Асинхронное выполнение инструмента через ToolExecutor (как в OpenClaw pi-embedded-runner.ts)
    
    Это главный метод для выполнения всех инструментов агента.
    """
    from tool_executor import tool_executor
    
    # Сначала пробуем через ToolExecutor (MCP и extended skills)
    if tool_name in tool_executor.registry.get_tool_names():
        result = await tool_executor.execute(tool_name, params, user_id)
        if result.success:
            if isinstance(result.result, dict):
                if result.result.get("success"):
                    # Для image_generate возвращаем полный результат (с путём)
                    if "path" in result.result:
                        return result.result  # Возвращаем словарь!
                    if "content" in result.result:
                        return result.result["content"]
                    elif "message" in result.result:
                        return result.result["message"]
                    elif "filename" in result.result:
                        return f"✅ Файл создан: {result.result['filename']}"
                return json.dumps(result.result, ensure_ascii=False, indent=2)
            return str(result.result)
        return f"❌ Ошибка: {result.error}"
    
    # Затем пробуем MCP оркестратор напрямую
    mcp_tools = mcp_orchestrator.get_tool_names()
    if tool_name in mcp_tools:
        return await execute_mcp_tool(tool_name, params)
    
    # Встроенные HR инструменты
    return _execute_builtin_tool(tool_name, params, user_id)


def _execute_builtin_tool(function_name: str, function_params: dict, user_id: int = None) -> str:
    """Выполнение встроенных HR инструментов"""
    logging.info(f"Executing builtin tool: {function_name}")
    
    try:
        # === Календарь ===
        if function_name == "get_calendar_events":
            days = function_params.get('days', 7)
            if not user_id:
                return "❌ Календарь не подключён. Используйте /connect"
            message, events = calendar_manager.list_events(user_id, days=days)
            return message
        
        # === Сотрудники (Google Sheets) ===
        elif function_name == "add_employee":
            success, message = google_sheets.add_employee(
                employee_name=function_params.get('employee_name', ''),
                role=function_params.get('role', ''),
                recruiter=function_params.get('recruiter', '-//-'),
                start_date=function_params.get('start_date'),
                salary=function_params.get('salary', ''),
                card_link=function_params.get('card_link', '')
            )
            return message
        
        elif function_name == "list_employees":
            success, message = google_sheets.list_employees(
                month=function_params.get('month')
            )
            return message
        
        elif function_name == "search_employee":
            success, message = google_sheets.search_employee(
                name=function_params.get('name', '')
            )
            return message
        
        elif function_name == "update_employee":
            success, message = google_sheets.update_employee(
                name=function_params.get('name', ''),
                field=function_params.get('field', ''),
                value=function_params.get('value', '')
            )
            return message
        
        # === Кандидаты ===
        elif function_name == "save_candidate":
            candidate_id = hr_agent_core.memory.add_candidate({
                "name": function_params.get('name'),
                "email": function_params.get('email'),
                "phone": function_params.get('phone'),
                "position": function_params.get('position'),
                "skills": function_params.get('skills', []),
                "experience": function_params.get('experience'),
                "salary_expectation": function_params.get('salary_expectation'),
                "source": function_params.get('source'),
                "notes": function_params.get('notes'),
                "rating": function_params.get('rating')
            })
            return f"✅ Кандидат сохранён в базу (ID: {candidate_id})"
        
        elif function_name == "search_candidates":
            candidates = hr_agent_core.memory.search_candidates(
                query=function_params.get('query'),
                status=function_params.get('status'),
                position=function_params.get('position'),
                limit=function_params.get('limit', 10)
            )
            if not candidates:
                return "Кандидаты не найдены."
            result = f"📋 Найдено {len(candidates)} кандидатов:\n\n"
            for c in candidates:
                result += f"• **{c['name']}** - {c.get('position', 'N/A')} ({c.get('status', 'new')})\n"
            return result
        
        elif function_name == "update_candidate_status":
            success = hr_agent_core.memory.update_candidate(
                function_params.get('candidate_id'),
                {"status": function_params.get('status')}
            )
            return f"✅ Статус обновлён" if success else "❌ Ошибка обновления"
        
        # === Вакансии ===
        elif function_name == "create_vacancy":
            vacancy_id = hr_agent_core.memory.add_vacancy({
                "title": function_params.get('title'),
                "department": function_params.get('department'),
                "description": function_params.get('description'),
                "requirements": function_params.get('requirements'),
                "salary_range": function_params.get('salary_range'),
                "hiring_manager": function_params.get('hiring_manager')
            })
            return f"✅ Вакансия создана (ID: {vacancy_id})"
        
        elif function_name == "list_vacancies":
            vacancies = hr_agent_core.memory.get_open_vacancies()
            if not vacancies:
                return "Открытых вакансий нет."
            result = f"📋 Открытые вакансии ({len(vacancies)}):\n\n"
            for v in vacancies:
                result += f"• **{v['title']}** - {v.get('department', 'N/A')}\n"
            return result
        
        # === Документы ===
        elif function_name == "create_offer":
            result = create_offer_document(
                candidate_name=function_params.get('candidate_name'),
                position=function_params.get('position'),
                salary=function_params.get('salary'),
                start_date=function_params.get('start_date'),
                department=function_params.get('department'),
                hr_name=function_params.get('hr_name')
            )
            if result.get('success'):
                return f"✅ Оффер создан!\n📄 [Открыть документ]({result.get('url')})"
            return f"⚠️ Контент оффера готов, но не удалось создать Google Doc:\n{result.get('content', '')[:500]}"
        
        elif function_name == "create_welcome":
            result = create_welcome_document(
                candidate_name=function_params.get('candidate_name'),
                position=function_params.get('position'),
                start_date=function_params.get('start_date'),
                buddy_name=function_params.get('buddy_name'),
                manager_name=function_params.get('manager_name')
            )
            if result.get('success'):
                return f"✅ Welcome-документ создан!\n📄 [Открыть документ]({result.get('url')})"
            return f"⚠️ Контент welcome готов:\n{result.get('content', '')[:500]}"
        
        elif function_name == "create_scorecard":
            result = create_scorecard_document(
                candidate_name=function_params.get('candidate_name'),
                position=function_params.get('position'),
                interviewer=function_params.get('interviewer'),
                competencies=function_params.get('competencies', {})
            )
            if result.get('success'):
                return f"✅ Scorecard создан!\n📄 [Открыть документ]({result.get('url')})"
            return f"⚠️ Контент scorecard готов:\n{result.get('content', '')[:500]}"
        
        elif function_name == "create_rejection":
            result = create_rejection_letter(
                candidate_name=function_params.get('candidate_name'),
                position=function_params.get('position'),
                hr_name=function_params.get('hr_name')
            )
            return f"✅ Письмо с отказом готово:\n\n{result.get('content', '')}"
        
        elif function_name == "create_interview_invite":
            result = create_interview_invite(
                candidate_name=function_params.get('candidate_name'),
                position=function_params.get('position'),
                interview_date=function_params.get('interview_date'),
                interview_time=function_params.get('interview_time'),
                interview_type=function_params.get('interview_type'),
                duration=function_params.get('duration')
            )
            return f"✅ Приглашение на интервью готово:\n\n{result.get('content', '')}"
        
        # === Воркфлоу ===
        elif function_name == "onboard_employee":
            results = []
            add_result = google_sheets.add_employee(
                employee_name=function_params.get('employee_name'),
                role=function_params.get('position'),
                recruiter=function_params.get('recruiter', '-//-'),
                start_date=function_params.get('start_date'),
                salary=function_params.get('salary', '')
            )
            results.append(f"📋 Таблица: {add_result[1][:100]}")
            
            welcome_result = create_welcome_document(
                candidate_name=function_params.get('employee_name'),
                position=function_params.get('position'),
                start_date=function_params.get('start_date'),
                buddy_name=function_params.get('buddy_name'),
                manager_name=function_params.get('manager_name')
            )
            if welcome_result.get('success'):
                results.append(f"📄 Welcome: [Открыть]({welcome_result.get('url')})")
            else:
                results.append("📄 Welcome: контент готов")
            
            if function_params.get('salary'):
                offer_result = create_offer_document(
                    candidate_name=function_params.get('employee_name'),
                    position=function_params.get('position'),
                    salary=function_params.get('salary'),
                    start_date=function_params.get('start_date')
                )
                if offer_result.get('success'):
                    results.append(f"📄 Оффер: [Открыть]({offer_result.get('url')})")
            
            return f"✅ **Онбординг завершён!**\n\n" + "\n".join(results)
        
        elif function_name == "process_candidate":
            candidate_id = hr_agent_core.memory.add_candidate({
                "name": function_params.get('name'),
                "email": function_params.get('email'),
                "phone": function_params.get('phone'),
                "position": function_params.get('position'),
                "skills": function_params.get('skills', []),
                "experience": function_params.get('experience'),
                "source": function_params.get('source')
            })
            vacancies = hr_agent_core.memory.get_open_vacancies()
            matching = [v for v in vacancies if function_params.get('position', '').lower() in v.get('title', '').lower()]
            result = f"✅ Кандидат сохранён (ID: {candidate_id})\n"
            if matching:
                result += f"🔍 Найдено {len(matching)} подходящих вакансий"
            else:
                result += "📋 Подходящих вакансий пока нет"
            return result
        
        elif function_name == "start_workflow":
            task = hr_agent_core.workflows.start_workflow(
                function_params.get('workflow_name'),
                function_params
            )
            return f"🔄 Воркфлоу запущен (ID: {task.id})"
        
        elif function_name == "get_workflow_status":
            status = hr_agent_core.workflows.get_workflow_status(
                function_params.get('task_id')
            )
            return f"📊 Статус: {status.get('status', 'unknown')}\nПрогресс: {status.get('progress', 'N/A')}"
        
        else:
            return f"❌ Неизвестная функция: {function_name}"
    
    except Exception as e:
        logging.error(f"Error executing builtin tool {function_name}: {e}")
        return f"❌ Ошибка выполнения: {str(e)}"


async def execute_tool_function(function_name: str, function_params: dict, user_id: int = None) -> str:
    """Выполнение функции инструмента (асинхронная версия)"""
    logging.info(f"Executing tool: {function_name} with params: {function_params}")
    
    try:
        # Сначала проверяем ToolExecutor (как в OpenClaw)
        from tool_executor import tool_executor
        if function_name in tool_executor.registry.get_tool_names():
            return await execute_tool_async(function_name, function_params, user_id)
        
        # Затем проверяем MCP инструменты
        mcp_tools = mcp_orchestrator.get_tool_names()
        if function_name in mcp_tools:
            return await execute_mcp_tool(function_name, function_params)
        
        # Встроенные HR инструменты
        return _execute_builtin_tool(function_name, function_params, user_id)
    
    except Exception as e:
        logging.error(f"Error executing tool: {e}")
        return f"❌ Ошибка выполнения: {str(e)}"


async def process_ai_request(update, context, user_input, is_file=False):
    """Обработка запроса через Agents API"""
    global mistral_agent
    
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    
    message = await update.message.reply_text("Анализирую..." if is_file else "...")
    
    try:
        # Проверяем, есть ли уже conversation для этого пользователя
        if chat_id in user_conversations:
            # Продолжаем существующий разговор
            response = mistral_client.beta.conversations.append(
                conversation_id=user_conversations[chat_id],
                inputs=user_input
            )
        else:
            # Начинаем новый разговор
            response = mistral_client.beta.conversations.start(
                agent_id=mistral_agent.id,
                inputs=user_input
            )
        
        # Сохраняем conversation_id для следующих сообщений
        user_conversations[chat_id] = response.conversation_id
        
        # Обработка function calls
        tool_calls = [out for out in response.outputs if out.type == 'function.call']
        
        if tool_calls:
            # Обрабатываем каждый tool call
            tool_results = []
            
            for tool_call in tool_calls:
                function_name = tool_call.name
                
                # Arguments может быть строкой JSON или словарём
                raw_args = tool_call.arguments if hasattr(tool_call, 'arguments') else {}
                if isinstance(raw_args, str):
                    function_params = json.loads(raw_args)
                else:
                    function_params = raw_args if raw_args else {}
                
                logging.info(f"Tool call: {function_name} with params: {function_params}")
                
                # Выполняем функцию (await для async)
                result = await execute_tool_function(function_name, function_params, user_id)
                
                # Если сгенерировано изображение - отправляем его в Telegram
                image_path = None
                if function_name == "image_generate" and result:
                    # Парсим путь к изображению из результата
                    if isinstance(result, dict) and result.get("success") and result.get("path"):
                        image_path = result["path"]
                    elif isinstance(result, str) and "создано" in result.lower():
                        # Извлекаем имя файла из строки "✅ Изображение создано: filename.png"
                        import re
                        match = re.search(r'(generated_\d+\.png)', result)
                        if match:
                            image_path = f"/home/z/my-project/hr-mistral-bot/workspace/images/{match.group(1)}"
                
                if image_path and Path(image_path).exists():
                    try:
                        prompt_text = ""
                        if isinstance(result, dict):
                            prompt_text = result.get('prompt', '')
                        await context.bot.send_photo(
                            chat_id=chat_id,
                            photo=open(image_path, 'rb'),
                            caption=f"🎨 {prompt_text}" if prompt_text else "🎨 Сгенерированное изображение"
                        )
                        logging.info(f"Sent generated image: {image_path}")
                    except Exception as e:
                        logging.error(f"Failed to send image: {e}")
                
                # Преобразуем результат в строку для Mistral API
                if isinstance(result, dict):
                    # Для изображений - сообщаем что уже отправлено
                    if result.get("success") and result.get("path"):
                        result_str = f"✅ Изображение успешно создано и отправлено пользователю. Файл: {result.get('filename', 'image.png')}"
                    else:
                        result_str = result.get("message", json.dumps(result, ensure_ascii=False))
                else:
                    result_str = str(result)
                
                tool_results.append({
                    "type": "function.result",
                    "tool_call_id": tool_call.tool_call_id,
                    "result": result_str
                })
            
            # Отправляем результаты tool calls обратно в агента
            logging.info(f"Sending tool results: {tool_results}")
            
            response = mistral_client.beta.conversations.append(
                conversation_id=user_conversations[chat_id],
                inputs=tool_results
            )
        
        # Получаем ответ из outputs
        message_outputs = [out for out in response.outputs if out.type == 'message.output']
        
        if not message_outputs:
            message_outputs = [out for out in response.outputs if out.type == 'message.content']
        
        if not message_outputs:
            for out in response.outputs:
                if hasattr(out, 'content') and out.content:
                    message_outputs = [out]
                    break
        
        if not message_outputs:
            raise Exception("Нет ответа от агента. Попробуйте /start для сброса разговора.")
        
        # Извлекаем текст из content
        content = message_outputs[-1].content
        if isinstance(content, str):
            full_response = content
        elif isinstance(content, list):
            text_chunks = [chunk.text for chunk in content if hasattr(chunk, 'text')]
            full_response = ''.join(text_chunks)
        else:
            full_response = str(content)
        
        # Форматируем текст
        full_response = format_markdown(full_response)
        
        # Отправляем финальный ответ
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message.message_id,
            text=full_response,
            parse_mode='Markdown'
        )
                
    except Exception as e:
        logging.error(f"Error in process_ai_request: {e}")
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message.message_id,
            text=f"Извини, произошла ошибка: {str(e)[:200]}"
        )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    # Проверяем, ожидаем ли мы код авторизации
    if context.user_data.get('waiting_for_auth_code'):
        await update.message.reply_text("⏳ Проверяю код авторизации...")
        
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
    
    # Обычная обработка сообщения
    await process_ai_request(update, context, text)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle PDF and DOC/DOCX document uploads"""
    document = update.message.document
    caption = update.message.caption or "Проанализируй этот документ"
    chat_id = update.effective_chat.id
    
    logging.info(f"Received document: {document.file_name}, mime_type: {document.mime_type}")
    
    supported_types = [
        'application/pdf',
        'application/msword',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    ]
    
    if document.mime_type in supported_types or document.file_name.endswith(('.pdf', '.doc', '.docx')):
        try:
            file = await context.bot.get_file(document.file_id)
            file_path = f"temp_{chat_id}_{document.file_name}"
            await file.download_to_drive(file_path)
            
            logging.info(f"Downloaded document to {file_path}")
            
            text = ""
            
            if document.mime_type == 'application/pdf' or file_path.endswith('.pdf'):
                with fitz.open(file_path) as doc:
                    for page in doc:
                        text += page.get_text()
            else:
                doc = Document(file_path)
                for paragraph in doc.paragraphs:
                    text += paragraph.text + "\n"
            
            logging.info(f"Extracted {len(text)} characters from document")
            
            os.remove(file_path)
            
            user_prompt = f"{caption}\n\nСодержимое файла {document.file_name}:\n{text[:10000]}"
            await process_ai_request(update, context, user_prompt, is_file=True)
            
        except Exception as e:
            logging.error(f"Document Error: {e}", exc_info=True)
            await update.message.reply_text(
                f"❌ Ошибка при чтении документа: {str(e)}\n\n"
                "Попробуйте еще раз или отправьте текст вручную."
            )
    else:
        await update.message.reply_text("❌ Пожалуйста, отправьте PDF, DOC или DOCX файл.")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка фото - пока упрощенная версия без vision"""
    await update.message.reply_text(
        "Извини, обработка изображений временно недоступна. "
        "Пожалуйста, отправь текст резюме или PDF файл."
    )


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка голосовых сообщений - транскрибация в текст"""
    chat_id = update.effective_chat.id
    voice = update.message.voice
    
    if not voice:
        return
    
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    
    try:
        # Скачиваем голосовое сообщение
        new_file = await context.bot.get_file(voice.file_id)
        
        temp_dir = "/home/z/my-project/hr-mistral-bot/workspace/audio"
        os.makedirs(temp_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ogg_path = f"{temp_dir}/voice_{timestamp}.ogg"
        wav_path = f"{temp_dir}/voice_{timestamp}.wav"
        
        await new_file.download_to_drive(ogg_path)
        
        logging.info(f"Downloaded voice message to: {ogg_path}")
        
        # Конвертируем OGG в WAV (z-ai asr не поддерживает OGG)
        import subprocess
        convert_result = subprocess.run(
            ['ffmpeg', '-y', '-i', ogg_path, '-ar', '16000', '-ac', '1', wav_path],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if not os.path.exists(wav_path):
            await update.message.reply_text(
                "❌ Не удалось обработать аудио. Попробуйте ещё раз."
            )
            return
        
        logging.info(f"Converted to WAV: {wav_path}")
        
        # Транскрибируем через z-ai CLI
        result = subprocess.run(
            ['z-ai', 'asr', '-f', wav_path],
            capture_output=True,
            text=True,
            timeout=120
        )
        
        logging.info(f"ASR result: returncode={result.returncode}, stdout={result.stdout[:200] if result.stdout else 'empty'}")
        
        if result.returncode == 0 and result.stdout.strip():
            transcription = result.stdout.strip()
            
            # Убираем служебные сообщения из вывода
            if "Initializing Z-AI SDK" in transcription:
                lines = transcription.split('\n')
                transcription = '\n'.join([l for l in lines if "Initializing" not in l and "🚀" not in l]).strip()
            
            if transcription:
                # Сразу обрабатываем через AI без промежуточного сообщения
                await process_ai_request(update, context, transcription, is_file=False)
            else:
                await update.message.reply_text(
                    "❌ Не удалось распознать речь. Попробуйте записать сообщение чётче."
                )
        else:
            await update.message.reply_text(
                "❌ Не удалось распознать речь. Попробуйте ещё раз."
            )
        
        # Удаляем временные файлы
        for path in [ogg_path, wav_path]:
            try:
                os.remove(path)
            except:
                pass
            
    except Exception as e:
        logging.error(f"Error processing voice message: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ Ошибка обработки: {str(e)[:100]}"
        )


if __name__ == '__main__':
    # Инициализируем БД
    db.init_db()
    
    # Инициализируем Mistral агента
    logging.info("Initializing Mistral Agent with MCP support...")
    initialize_agent()
    
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Команды
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('connect', connect_google))
    application.add_handler(CommandHandler('calendar', show_calendar))
    application.add_handler(CommandHandler('disconnect', disconnect_google))
    application.add_handler(CommandHandler('skills', show_skills))
    application.add_handler(CommandHandler('mcp_add', mcp_add_server))
    application.add_handler(CommandHandler('mcp_remove', mcp_remove_server))
    
    # Обработчики сообщений
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    
    # Запускаем notification loop в фоне
    loop = asyncio.get_event_loop()
    loop.create_task(notification_loop(application.bot))
    
    logging.info("🚀 Бот запущен с полным набором инструментов AI-агента!")
    application.run_polling()
