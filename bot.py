import logging
import os
import asyncio
import fitz  # PyMuPDF
from docx import Document
import base64
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from telegram.error import BadRequest
from mistralai import Mistral
import database as db
import google_auth
from google_calendar_manager import GoogleCalendarManager
from notifications import notification_loop
import google_sheets

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# API Ключи - используются переменные окружения или значения по умолчанию
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "AEE3rpaceKHZzBtbVKnN9CWoNdpjlp2l")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8399347076:AAFLtRxXEKESWuTQb19vc6mhMQph7rHxsLg")

# Системный промпт для агента
AGENT_INSTRUCTIONS = """
Ты — **HRик HуяRік**, экспертный ИИ-ассистент для HR-команды и рекрутеров (Senior HR Business Partner & Lead Recruiter). Твоя цель — повышать эффективность HR-процессов, помогать нанимать лучших талантов и развивать корпоративную культуру.

Ты дружелюбный, профессиональный и всегда готов помочь. Используй эмодзи умеренно (1-2 на сообщение) для создания приятной атмосферы, но не переборщи. Иногда можешь представляться своим именем - HRик HуяRік.

Твои основные режимы работы и обязанности:

1. ГЕНЕРАЛИСТ И СТРАТЕГ (HR Strategy & Ops):
- Помогай разрабатывать HR-стратегии: от онбординга и удержания (retention) до L&D (обучение и развитие).
- Предлагай идеи для тимбилдингов, well-being программ и улучшения корпоративной культуры.
- При запросе политик или регламентов создавай структурированные черновики документов.
- Используй веб-поиск для анализа рынка зарплат и бенефитов (бенчмаркинг).

2. РЕКРУТИНГ И СОРСИНГ (Recruitment & Sourcing):
- Составление вакансий (JD): Пиши привлекательные, гендерно-нейтральные описания вакансий с фокусом на результаты, а не только обязанности.
- Сорсинг: Генерируй сложные Boolean Search строки (X-Ray запросы) для поиска кандидатов в LinkedIn, GitHub, Google и других платформах. Учитывай синонимы должностей и навыков.
- Скрининг резюме: Анализируй тексты резюме. Сравнивай их с описанием вакансии. Выделяй сильные стороны, красные флаги (red flags) и недостающие навыки. Оценивай релевантность кандидата по шкале от 1 до 10 с обоснованием.
- Письма кандидатам: Пиши персонализированные холодные письма (cold reach-outs) и фидбек (как положительный, так и отказ).

3. АНАЛИЗ ИНТЕРВЬЮ (Interview Intelligence):
- Подготовка: Составляй списки вопросов для интервью (скрининг, техническое, culture fit), основанные на компетенциях (STAR метод).
- Анализ: Если тебе загружают транскрипт или заметки с интервью, структурируй их. Оценивай ответы кандидата на предмет soft и hard skills. Ищи несостыковки.
- Scorecards: Помогай заполнять карты оценки кандидатов.

4. РАБОТА С КАЛЕНДАРЕМ:
- Ты можешь просматривать календарь пользователя и помогать планировать интервью.
- Когда пользователь просит посмотреть календарь, используй функцию get_calendar_events.
- Ты можешь помочь найти свободное время для встреч.

5. РАБОТА С ТАБЛИЦЕЙ СОТРУДНИКОВ:
- Ты можешь добавлять новых сотрудников в Google Таблицу.
- Ты можешь показывать список сотрудников из таблицы.
- Ты можешь искать сотрудников по имени.
- Ты можешь обновлять информацию о сотрудниках.

**Функции для работы с таблицей:**
- add_employee: добавляет нового сотрудника. Параметры: employee_name (имя), role (должность), recruiter (рекрутер), start_date (дата выхода), salary (сумма), card_link (ссылка на карточку).
- list_employees: показывает список сотрудников. Параметр: month (фильтр по месяцу, опционально).
- search_employee: ищет сотрудника по имени. Параметр: name (имя или часть имени).
- update_employee: обновляет данные сотрудника. Параметры: name (имя), field (поле: рекрутер, дата выхода, сумма, рекомендация, карточка), value (новое значение).

**Примеры запросов:**
- "Добавь сотрудника Иван Иванов, должность Python Developer, дата выхода 01.03.2025"
- "Покажи список сотрудников за март"
- "Найди сотрудника Иван"
- "Обнови рекомендацию для Иван: прошел ИС"

ФОРМАТ ОБЩЕНИЯ И СТИЛЬ:
- Тон: Дружелюбный, профессиональный и эмпатичный. Используй обращение на "ты" для создания доверительной атмосферы.
- Структура: Используй **жирный текст** для выделения ключевых моментов, заголовки и списки для удобства чтения. Избегай "воды".
- Эмодзи: Используй 1-2 эмодзи на сообщение для создания дружелюбной атмосферы (например: ✅ для успеха, 📊 для данных, 💡 для идей, 🎯 для целей).
- Markdown: Используй Markdown форматирование:
  * **жирный текст** для важных моментов
  * *курсив* для акцентов
  * Списки для структурирования
  * Заголовки для разделения тем
- Язык: Отвечай на том языке, на котором задан вопрос (преимущественно русский), но профессиональные термины (Boolean, Retention rate и т.д.) можешь оставлять на английском или давать в скобках.

ВАЖНО:
- Если тебе не хватает контекста (например, уровня сеньорности позиции, стека технологий или корпоративных ценностей), всегда задавай уточняющие вопросы перед генерацией ответа.
- Когда нужна актуальная информация (зарплаты, новости компаний, технологии), используй веб-поиск автоматически.
- ОБЯЗАТЕЛЬНО используй Markdown форматирование для улучшения читаемости: **жирный текст**, *курсив*, списки, заголовки.
- Будь дружелюбным и поддерживающим, но сохраняй профессионализм.
"""

# Инициализация клиента Mistral
mistral_client = Mistral(api_key=MISTRAL_API_KEY)

# Глобальные переменные
hr_agent = None
calendar_manager = GoogleCalendarManager()

# Хранилище conversation_id для каждого пользователя
user_conversations = {}

def initialize_agent():
    """Создание агента при старте бота"""
    global hr_agent
    try:
        hr_agent = mistral_client.beta.agents.create(
            model="mistral-small-latest",
            name="HR Assistant Bot",
            description="Экспертный HR-ассистент для рекрутинга, анализа резюме и HR-стратегий с автоматическим веб-поиском",
            instructions=AGENT_INSTRUCTIONS,
            tools=[
                {"type": "web_search"},
                {
                    "type": "function",
                    "function": {
                        "name": "get_calendar_events",
                        "description": "Get user's calendar events for specified number of days",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "days": {
                                    "type": "integer",
                                    "description": "Number of days to look ahead (default: 7)"
                                }
                            }
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "add_employee",
                        "description": "Add a new employee to the Google Sheets tracking table. Use this when user wants to add/register a new employee who is starting work.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "employee_name": {
                                    "type": "string",
                                    "description": "Full name of the employee"
                                },
                                "role": {
                                    "type": "string",
                                    "description": "Job title/position of the employee"
                                },
                                "recruiter": {
                                    "type": "string",
                                    "description": "Name of the recruiter who hired this person (default: '-//-')"
                                },
                                "start_date": {
                                    "type": "string",
                                    "description": "Start date in DD/MM/YYYY format (e.g., '15/03/2025')"
                                },
                                "salary": {
                                    "type": "string",
                                    "description": "Salary amount from the offer (e.g., '1500 USDT')"
                                },
                                "card_link": {
                                    "type": "string",
                                    "description": "Link to employee card/profile (optional)"
                                }
                            },
                            "required": ["employee_name", "role"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "list_employees",
                        "description": "List employees from the Google Sheets tracking table. Can filter by month.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "month": {
                                    "type": "string",
                                    "description": "Filter by month name in Russian (e.g., 'Март', 'Апрель'). Optional."
                                }
                            }
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "search_employee",
                        "description": "Search for an employee by name in the Google Sheets tracking table.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "description": "Employee name or part of the name to search for"
                                }
                            },
                            "required": ["name"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "update_employee",
                        "description": "Update employee information in the Google Sheets tracking table.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "description": "Employee name to update"
                                },
                                "field": {
                                    "type": "string",
                                    "description": "Field to update: 'рекрутер', 'дата выхода', 'сумма', 'рекомендация', 'карточка'"
                                },
                                "value": {
                                    "type": "string",
                                    "description": "New value for the field"
                                }
                            },
                            "required": ["name", "field", "value"]
                        }
                    }
                }
            ],
            completion_args={
                "temperature": 0.7,
            }
        )
        logging.info(f"Agent created successfully with ID: {hr_agent.id}")
    except Exception as e:
        logging.error(f"Failed to create agent: {e}")
        raise

def format_markdown(text):
    """Форматирование текста для Telegram (поддержка Markdown)"""
    # Telegram поддерживает MarkdownV2, но мы используем HTML для надежности
    # Конвертируем базовый Markdown в Telegram-совместимый формат
    return text

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    # Очищаем conversation_id при /start
    if chat_id in user_conversations:
        del user_conversations[chat_id]
    
    await update.message.reply_text(
        "👋 Привет! Я *HRик HуяRік* — твой экспертный ИИ-ассистент для HR с автоматическим веб-поиском.\n\n"
        "Я могу:\n"
        "✅ Анализировать резюме (PDF)\n"
        "✅ Искать актуальную информацию в интернете\n"
        "✅ Помогать с рекрутингом и HR-стратегиями\n"
        "✅ Работать с твоим Google Calendar\n"
        "✅ Вести учёт новых сотрудников в Google Таблице\n\n"
        "📅 *Календарь:*\n"
        "/connect - подключить Google Calendar\n"
        "/calendar - показать события\n\n"
        "📊 *Таблица сотрудников:*\n"
        "Просто попроси: 'Добавь сотрудника...' или 'Покажи список сотрудников'\n\n"
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

async def process_ai_request(update, context, user_input, is_file=False):
    """Обработка запроса через Agents API"""
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
                agent_id=hr_agent.id,
                inputs=user_input
            )
        
        # Сохраняем conversation_id для следующих сообщений
        user_conversations[chat_id] = response.conversation_id
        
        # Обработка tool calls (если агент хочет вызвать функцию)
        tool_calls = [out for out in response.outputs if out.type == 'tool.call']
        
        if tool_calls:
            # Обрабатываем каждый tool call
            tool_results = []
            
            for tool_call in tool_calls:
                function_name = tool_call.name
                function_params = tool_call.arguments if hasattr(tool_call, 'arguments') else {}
                
                logging.info(f"Tool call: {function_name} with params: {function_params}")
                
                if function_name == "get_calendar_events":
                    # Получаем данные календаря
                    days = function_params.get('days', 7)
                    message_text, events = calendar_manager.list_events(user_id, days=days)
                    
                    tool_results.append({
                        "type": "function.result",
                        "tool_call_id": tool_call.id,
                        "result": message_text
                    })
                
                elif function_name == "add_employee":
                    # Добавляем сотрудника в таблицу
                    success, message = google_sheets.add_employee(
                        employee_name=function_params.get('employee_name', ''),
                        role=function_params.get('role', ''),
                        recruiter=function_params.get('recruiter', '-//-'),
                        start_date=function_params.get('start_date'),
                        salary=function_params.get('salary', ''),
                        card_link=function_params.get('card_link', '')
                    )
                    
                    tool_results.append({
                        "type": "function.result",
                        "tool_call_id": tool_call.id,
                        "result": message
                    })
                
                elif function_name == "list_employees":
                    # Показываем список сотрудников
                    success, message = google_sheets.list_employees(
                        month=function_params.get('month')
                    )
                    
                    tool_results.append({
                        "type": "function.result",
                        "tool_call_id": tool_call.id,
                        "result": message
                    })
                
                elif function_name == "search_employee":
                    # Ищем сотрудника
                    success, message = google_sheets.search_employee(
                        name=function_params.get('name', '')
                    )
                    
                    tool_results.append({
                        "type": "function.result",
                        "tool_call_id": tool_call.id,
                        "result": message
                    })
                
                elif function_name == "update_employee":
                    # Обновляем данные сотрудника
                    success, message = google_sheets.update_employee(
                        name=function_params.get('name', ''),
                        field=function_params.get('field', ''),
                        value=function_params.get('value', '')
                    )
                    
                    tool_results.append({
                        "type": "function.result",
                        "tool_call_id": tool_call.id,
                        "result": message
                    })
            
            # Отправляем результаты tool calls обратно в агента
            logging.info(f"Sending tool results: {tool_results}")
            
            response = mistral_client.beta.conversations.append(
                conversation_id=user_conversations[chat_id],
                inputs=tool_results
            )
            
            logging.info(f"Response after tool calls - full object: {response}")
            logging.info(f"Response outputs types: {[out.type for out in response.outputs]}")
            
            # Детальное логирование каждого output
            for i, out in enumerate(response.outputs):
                logging.info(f"Output {i}: type={out.type}, has_content={hasattr(out, 'content')}, content={getattr(out, 'content', None)}")
        
        # Получаем ответ из outputs
        # Пробуем разные типы outputs
        message_outputs = []
        
        # 1. Пробуем message.output
        message_outputs = [out for out in response.outputs if out.type == 'message.output']
        
        # 2. Если нет, пробуем message.content
        if not message_outputs:
            message_outputs = [out for out in response.outputs if out.type == 'message.content']
            if message_outputs:
                logging.info("Using message.content instead of message.output")
        
        # 3. Если нет, пробуем любой output с content
        if not message_outputs:
            logging.error(f"No message.output or message.content found. Available outputs: {[(out.type, hasattr(out, 'content')) for out in response.outputs]}")
            
            for out in response.outputs:
                if hasattr(out, 'content') and out.content:
                    message_outputs = [out]
                    logging.info(f"Using fallback output type: {out.type}")
                    break
        
        if not message_outputs:
            logging.error("FULL RESPONSE DUMP:")
            logging.error(f"{response}")
            raise Exception("Нет ответа от агента. Попробуйте /start для сброса разговора.")
        
        # Извлекаем текст из content (может быть строкой или списком chunks)
        content = message_outputs[-1].content
        if isinstance(content, str):
            full_response = content
        elif isinstance(content, list):
            # Собираем только текстовые чанки
            text_chunks = [chunk.text for chunk in content if hasattr(chunk, 'text')]
            full_response = ''.join(text_chunks)
        else:
            full_response = str(content)
        
        # Форматируем текст (оставляем Markdown)
        full_response = format_markdown(full_response)
        
        # Отправляем финальный ответ с поддержкой Markdown
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
        # Пытаемся использовать текст как код авторизации
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
    
    # Поддерживаемые типы
    supported_types = [
        'application/pdf',
        'application/msword',  # .doc
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document'  # .docx
    ]
    
    if document.mime_type in supported_types or document.file_name.endswith(('.pdf', '.doc', '.docx')):
        try:
            # Скачиваем файл
            file = await context.bot.get_file(document.file_id)
            file_path = f"temp_{chat_id}_{document.file_name}"
            await file.download_to_drive(file_path)
            
            logging.info(f"Downloaded document to {file_path}")
            
            # Извлекаем текст в зависимости от типа
            text = ""
            
            if document.mime_type == 'application/pdf' or file_path.endswith('.pdf'):
                # PDF
                with fitz.open(file_path) as doc:
                    for page in doc:
                        text += page.get_text()
            else:
                # DOC/DOCX
                doc = Document(file_path)
                for paragraph in doc.paragraphs:
                    text += paragraph.text + "\n"
            
            logging.info(f"Extracted {len(text)} characters from document")
            
            # Удаляем временный файл
            os.remove(file_path)
            
            # Обрабатываем через AI
            user_prompt = f"{caption}\n\nСодержимое файла {document.file_name}:\n{text[:10000]}"  # Ограничиваем 10k символов
            await process_ai_request(update, context, user_prompt, is_file=True)
            
        except Exception as e:
            logging.error(f"PDF Error: {e}", exc_info=True)
            await update.message.reply_text(
                f"❌ Ошибка при чтении PDF: {str(e)}\n\n"
                "Попробуйте еще раз или отправьте текст вручную."
            )
    else:
        await update.message.reply_text("❌ Пожалуйста, отправьте PDF, DOC или DOCX файл.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка фото - пока упрощенная версия без vision"""
    await update.message.reply_text(
        "Извини, обработка изображений временно недоступна в режиме Agents API. "
        "Пожалуйста, отправь текст резюме или PDF файл."
    )

if __name__ == '__main__':
    # Инициализируем БД
    db.init_db()
    
    # Инициализируем агента перед запуском бота
    logging.info("Initializing Mistral Agent...")
    initialize_agent()
    
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Команды
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('connect', connect_google))
    application.add_handler(CommandHandler('calendar', show_calendar))
    application.add_handler(CommandHandler('disconnect', disconnect_google))
    
    # Обработчики сообщений
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    # Запускаем notification loop в фоне
    loop = asyncio.get_event_loop()
    loop.create_task(notification_loop(application.bot))
    
    logging.info("Бот запущен с Agents API, веб-поиском, Google Calendar, Google Sheets и уведомлениями...")
    application.run_polling()
