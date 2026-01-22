import logging
import os
import asyncio
import json
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
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# API Ключи
MISTRAL_API_KEY = "WOkX5dBJuq8I9sMkVqmlpNwjVrzX19i3"
TELEGRAM_BOT_TOKEN = "8399347076:AAFLtRxXEKESWuTQb19vc6mhMQph7rHxsLg"

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
- Если тебе не хватает контекста (например, уровня сеньорности позиции, стека технологий или корпоративных ценностей), всегда задавай уточняющие вопросы перед генерацие71	- Когда нужна актуальная информация (зарплаты, новости компаний, технологии), используй веб-поиск автоматически.
72	- ВАЖНО: Твои внутренние знания ограничены началом 2024 года. Сейчас на дворе 2026 год. Если пользователь спрашивает о текущих событиях, политиках (например, кто президент), новостях или любой информации, которая могла измениться с 2024 года — ты ОБЯЗАН использовать инструмент `web_search`. Не пытайся угадать ответ из своей памяти.
73	- ОБЯЗАТЕЛЬНО используй Markdown форматирование для улучшения читаемости: **жирный текст**, *курсив*, списки, заголовки.
74	- Будь дружелюбным и поддерживающим, но сохраняй профессионализм.
75	"""# Инициализация клиента Mistral
mistral_client = Mistral(api_key=MISTRAL_API_KEY)

# Глобальные переменные
hr_agent = None
calendar_manager = GoogleCalendarManager()

# Хранилище conversation_id для каждого пользователя
user_conversations = {}

def get_current_instructions():
    """Возвращает инструкции с актуальной датой"""
    current_date = datetime.now().strftime("%d.%m.%Y")
    return f"Сегодняшняя дата: {current_date}\n\n" + AGENT_INSTRUCTIONS

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
    if not text:
        return ""
    # Базовая очистка для предотвращения ошибок парсинга Markdown
    # В Telegram Markdown (v1) наиболее критичны незакрытые * и _
    # Мы просто возвращаем текст, но в send_long_message добавим fallback на обычный текст
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
        "✅ Работать с твоим Google Calendar\n\n"
        "📅 Команды для календаря:\n"
        "/connect - подключить Google Calendar\n"
        "/calendar - показать события\n"
        "/disconnect - отключить календарь\n\n"
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

async def send_long_message(context, chat_id, text, parse_mode='Markdown', reply_to_message_id=None, edit_message_id=None):
    """Отправка длинных сообщений, разбивая их на части"""
    MAX_LENGTH = 4000
    
    async def safe_send(text_part, msg_id=None):
        try:
            if msg_id:
                return await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=text_part,
                    parse_mode=parse_mode,
                    disable_web_page_preview=True
                )
            else:
                return await context.bot.send_message(
                    chat_id=chat_id,
                    text=text_part,
                    parse_mode=parse_mode,
                    reply_to_message_id=reply_to_message_id,
                    disable_web_page_preview=True
                )
        except BadRequest as e:
            if "Can't parse entities" in str(e):
                # Если ошибка парсинга, отправляем как обычный текст без разметки
                logging.warning(f"Markdown parsing failed, falling back to plain text: {e}")
                if msg_id:
                    return await context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=msg_id,
                        text=text_part,
                        parse_mode=None,
                        disable_web_page_preview=True
                    )
                else:
                    return await context.bot.send_message(
                        chat_id=chat_id,
                        text=text_part,
                        parse_mode=None,
                        reply_to_message_id=reply_to_message_id,
                        disable_web_page_preview=True
                    )
            raise e

    if len(text) <= MAX_LENGTH:
        return await safe_send(text, edit_message_id)

    # Разбиваем текст на части
    parts = []
    while text:
        if len(text) <= MAX_LENGTH:
            parts.append(text)
            break
        
        # Ищем подходящее место для разрыва (конец предложения или абзаца)
        split_at = text.rfind('\n\n', 0, MAX_LENGTH)
        if split_at == -1:
            split_at = text.rfind('\n', 0, MAX_LENGTH)
        if split_at == -1:
            split_at = text.rfind('. ', 0, MAX_LENGTH)
        if split_at == -1:
            split_at = MAX_LENGTH
        
        parts.append(text[:split_at].strip())
        text = text[split_at:].strip()

    # Отправляем части
    first_msg = True
    for part in parts:
        if not part: continue
        
        if first_msg and edit_message_id:
            await safe_send(part, edit_message_id)
            first_msg = False
        else:
            await safe_send(part)
            await asyncio.sleep(0.1) # Небольшая задержка между сообщениями

async def process_ai_request(update, context, user_input, is_file=False):
    """Обработка запроса через Chat Completion API с function calling"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    
    message = await update.message.reply_text("Анализирую..." if is_file else "...")
    
    try:
        # Получаем или создаем историю сообщений для пользователя
        if chat_id not in user_conversations:
            user_conversations[chat_id] = []
        
        # Добавляем сообщение пользователя
        user_conversations[chat_id].append({
            "role": "user",
            "content": user_input
        })

        def get_valid_messages(history):
            """Фильтрует историю, чтобы она соответствовала правилам Mistral API"""
            valid = []
            for i, msg in enumerate(history):
                role = msg.get('role')
                # Роль 'tool' может идти только после 'assistant' с 'tool_calls'
                if role == 'tool':
                    if not valid or valid[-1].get('role') != 'assistant' or not valid[-1].get('tool_calls'):
                        logging.warning(f"Skipping orphaned tool message at index {i}")
                        continue
                valid.append(msg)
            return valid
        
        # Определяем доступные функции
        tools = []
        
        # Проверяем, подключен ли календарь
        if db.is_calendar_connected(user_id):
            tools.append({
                "type": "function",
                "function": {
                    "name": "get_calendar_events",
                    "description": "Получить события из Google Calendar пользователя на указанное количество дней вперед",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "days": {
                                "type": "integer",
                                "description": "Количество дней вперед для получения событий (по умолчанию 7)"
                            }
                        },
                        "required": []
                    }
                }
            })
        
        # Максимум 5 итераций для обработки tool calls
        max_iterations = 5
        current_instructions = get_current_instructions()
        
        for iteration in range(max_iterations):
            # Проверяем, нужно ли использовать агента
            # Мы используем Agents API, если есть доступные инструменты или запрос на поиск/актуальную информацию
            search_keywords = [
                "найди", "поиск", "интернет", "узнай", "google", "актуальн", 
                "сейчас", "сегодня", "дата", "новости", "кто", "президент", 
                "курс", "цена", "сколько", "события"
            ]
            use_agent = tools or any(word in user_input.lower() for word in search_keywords)
            
            # Фильтруем историю перед отправкой
            valid_history = get_valid_messages(user_conversations[chat_id])

            if use_agent:
                logging.info("Using Agents API for request")
                
                # Обновляем инструкции агента перед вызовом, чтобы он знал текущую дату
                try:
                    mistral_client.beta.agents.update(
                        agent_id=hr_agent.id,
                        instructions=current_instructions
                    )
                except Exception as update_error:
                    logging.error(f"Failed to update agent instructions: {update_error}")
                
                response = mistral_client.agents.complete(
                    agent_id=hr_agent.id,
                    messages=valid_history
                )
            else:
                logging.info("Using Chat Completion API (Mistral Large)")
                response = mistral_client.chat.complete(
                    model="mistral-large-latest",
                    messages=[
                        {"role": "system", "content": current_instructions}
                    ] + valid_history
                )
            
            assistant_message = response.choices[0].message
            
            # Проверяем, есть ли tool calls
            if assistant_message.tool_calls:
                logging.info(f"Tool calls detected: {len(assistant_message.tool_calls)}")
                
                # Добавляем сообщение ассистента с tool calls
                user_conversations[chat_id].append({
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        } for tc in assistant_message.tool_calls
                    ]
                })
                
                # Обрабатываем каждый tool call
                for tool_call in assistant_message.tool_calls:
                    function_name = tool_call.function.name
                    
                    # Проверяем, является ли это встроенным инструментом (web_search)
                    if not tool_call.function:
                        continue
                        
                    function_args = json.loads(tool_call.function.arguments)
                    
                    logging.info(f"Calling function: {function_name} with args: {function_args}")
                    
                    if function_name == "get_calendar_events":
                        days = function_args.get('days', 7)
                        result_text, events = calendar_manager.list_events(user_id, days=days)
                        
                        # Добавляем результат функции
                        user_conversations[chat_id].append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": function_name,
                            "content": result_text
                        })
                    else:
                        # Для неизвестных функций или встроенных инструментов, которые Mistral обрабатывает сам
                        # Если Mistral вернул tool_call для web_search, мы не должны его обрабатывать вручную здесь,
                        # но если он попал сюда, добавим пустой ответ, чтобы не нарушать порядок ролей
                        logging.warning(f"Unknown function call: {function_name}")
                        user_conversations[chat_id].append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": function_name,
                            "content": "Выполнено"
                        })
                
                # Продолжаем цикл для получения финального ответа
                continue
            else:
                # Нет tool calls - это финальный ответ
                assistant_content = assistant_message.content
                
                # Добавляем ответ ассистента в историю
                user_conversations[chat_id].append({
                    "role": "assistant",
                    "content": assistant_content
                })
                
                # Ограничиваем историю последними 20 сообщениями
                if len(user_conversations[chat_id]) > 20:
                    user_conversations[chat_id] = user_conversations[chat_id][-20:]
                
                # Форматируем и отправляем ответ
                formatted_response = format_markdown(assistant_content)
                
                await send_long_message(
                    context=context,
                    chat_id=chat_id,
                    text=formatted_response,
                    parse_mode='Markdown',
                    edit_message_id=message.message_id
                )
                
                return
        
        # Если достигли максимума итераций
        raise Exception("Превышено максимальное количество вызовов функций")
        
    except Exception as e:
        logging.error(f"Error in AI request: {e}", exc_info=True)
        error_message = f"❌ Извини, произошла ошибка: {str(e)}"
        
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message.message_id,
                text=error_message
            )
        except:
            await update.message.reply_text(error_message)

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
    
    logging.info("Бот запущен с Agents API, веб-поиском, Google Calendar и уведомлениями...")
    application.run_polling()
