import logging
import os
import asyncio
import json
import fitz  # PyMuPDF
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from telegram.error import BadRequest
from google import genai
from google.genai import types
from google.genai.errors import APIError

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
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8399347076:AAFLtRxXEKESWuTQb19vc6mhMQph7rHxsLg")

# Системный промпт
AGENT_INSTRUCTIONS = """
Ты — **HRик HуяRік**, экспертный ИИ-ассистент для HR-команды и рекрутеров. Твоя цель — повышать эффективность HR-процессов, помогать нанимать лучших талантов и развивать корпоративную культуру.

Твои знания ограничены началом 2024 года. Сейчас 2026 год.
ВАЖНО: Для любых вопросов о текущих событиях, ценах, курсах валют, политиках или новостях ты ОБЯЗАН использовать инструмент `google_search`. Не пытайся угадать ответ.

РАССУЖДЕНИЕ (Chain of Thought): Перед тем как дать ответ, проанализируй задачу, разбей её на шаги и убедись в актуальности данных.
"""

# Инициализация клиента Gemini
try:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
except Exception as e:
    logging.error(f"Failed to initialize Gemini client: {e}")
    gemini_client = None

# Хранилище для истории разговоров
user_conversations = {}

def get_current_instructions():
    current_date = datetime.now().strftime("%d.%m.%Y")
    return f"Сегодняшняя дата: {current_date}\n\n" + AGENT_INSTRUCTIONS

# --- Команды для Google Calendar ---
async def connect_google(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if db.is_calendar_connected(user_id):
        await update.message.reply_text("✅ Ваш Google Календарь уже подключен.")
        return
    
    auth_url = google_auth.get_auth_url(user_id)
    await update.message.reply_text(
        f"Для подключения Google Календаря перейдите по ссылке:\n{auth_url}\n\n"
        "Скопируйте код, который появится, и отправьте его мне в следующем сообщении."
    )
    context.user_data['waiting_for_auth_code'] = True

async def show_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not db.is_calendar_connected(user_id):
        await update.message.reply_text("❌ Google Календарь не подключен. Используйте команду /connect.")
        return
    await process_ai_request(update, context, "Покажи мне события в моем календаре на ближайшие 7 дней.")

async def disconnect_google(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if google_auth.clear_credentials(user_id):
        await update.message.reply_text("✅ Google Календарь успешно отключен.")
    else:
        await update.message.reply_text("❌ Ошибка при отключении. Возможно, он и не был подключен.")

# --- Основная логика бота ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in user_conversations:
        del user_conversations[chat_id]
    
    await update.message.reply_text(
        "👋 Привет! Я *HRик HуяRік* — твой экспертный ИИ-ассистент с поиском как в Le Chat.\n\n"
        "Я могу:\n"
        "✅ Искать актуальную информацию в интернете\n"
        "✅ Анализировать резюме (PDF)\n"
        "✅ Работать с Google Calendar (/connect, /calendar, /disconnect)\n\n"
        "Пришли мне вопрос или файл!",
        parse_mode='Markdown'
    )

async def send_long_message(context, chat_id, text, **kwargs):
    MAX_LENGTH = 4000
    try:
        await context.bot.send_message(chat_id=chat_id, text=text[:MAX_LENGTH], parse_mode='Markdown', **kwargs)
    except BadRequest:
        await context.bot.send_message(chat_id=chat_id, text=text[:MAX_LENGTH], parse_mode=None, **kwargs)

def get_gemini_tools(user_id):
    tools = [
        {"google_search": {}} # Встроенный Google Search
    ]
    
    if db.is_calendar_connected(user_id):
        tools.append({
            "function_declarations": [
                {
                    "name": "get_calendar_events",
                    "description": "Получить события из Google Календаря на указанное количество дней.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "days": {"type": "integer", "description": "Количество дней для просмотра."}
                        },
                        "required": ["days"]
                    }
                }
            ]
        })
    return tools

def get_gemini_messages(history):
    gemini_messages = []
    for msg in history:
        role = "user" if msg["role"] == "user" else "model"
        gemini_messages.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))
    return gemini_messages

async def process_ai_request(update, context, user_input, is_file=False):
    if not gemini_client:
        await update.message.reply_text("❌ Ошибка: Клиент Gemini не инициализирован. Проверьте GEMINI_API_KEY.")
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    message = await update.message.reply_text("Анализирую..." if is_file else "...")
    
    if chat_id not in user_conversations:
        user_conversations[chat_id] = []
    
    user_conversations[chat_id].append({"role": "user", "content": user_input})
    history = user_conversations[chat_id][-10:]
    
    # Инструменты для Gemini
    tools = get_gemini_tools(user_id)
    
    # Сообщения для Gemini
    gemini_messages = get_gemini_messages(history)
    
    try:
        # Первый вызов для определения, нужен ли инструмент
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=gemini_messages,
            config=types.GenerateContentConfig(
                system_instruction=get_current_instructions(),
                tools=tools
            )
        )
        
        # Обработка вызовов инструментов
        if response.function_calls:
            tool_results = []
            for call in response.function_calls:
                if call.name == "get_calendar_events":
                    try:
                        days = call.args.get('days', 7)
                        manager = GoogleCalendarManager()
                        result_text, _ = manager.list_events(user_id, days)
                        result = result_text
                    except Exception as e:
                        result = f"Ошибка при вызове календаря: {e}"
                    
                    tool_results.append(types.Part.from_function_response(
                        name="get_calendar_events",
                        response={"result": result}
                    ))
            
            # Добавляем ответ модели и результаты инструментов в историю
            gemini_messages.append(response.candidates[0].content)
            gemini_messages.append(types.Content(role="tool", parts=tool_results))

            # Финальный вызов с результатами инструментов
            final_response = gemini_client.models.generate_content(
                model='gemini-2.5-flash',
                contents=gemini_messages,
                config=types.GenerateContentConfig(
                    system_instruction=get_current_instructions(),
                    tools=tools
                )
            )
            final_content = final_response.text
        else:
            # Если инструментов не было, используем первый ответ
            final_content = response.text

        # Обновляем историю разговора (упрощенно для Gemini)
        user_conversations[chat_id].append({"role": "model", "content": final_content})
        
        await context.bot.edit_message_text(chat_id=chat_id, message_id=message.message_id, text=final_content, parse_mode='Markdown')

    except APIError as e:
        logging.error(f"Gemini API Error: {e}")
        await context.bot.edit_message_text(chat_id=chat_id, message_id=message.message_id, text=f"❌ Ошибка Gemini API: {str(e)}")
    except Exception as e:
        logging.error(f"General AI Error: {e}")
        await context.bot.edit_message_text(chat_id=chat_id, message_id=message.message_id, text=f"❌ Общая ошибка: {str(e)}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('waiting_for_auth_code'):
        code = update.message.text
        if google_auth.save_credentials(update.effective_user.id, code):
            await update.message.reply_text("✅ Календарь успешно подключен!")
        else:
            await update.message.reply_text("❌ Ошибка подключения. Проверьте код.")
        context.user_data['waiting_for_auth_code'] = False
        return
    
    await process_ai_request(update, context, update.message.text)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc.file_name.lower().endswith('.pdf'):
        await update.message.reply_text("Пожалуйста, пришлите резюме в формате PDF.")
        return
    
    file = await context.bot.get_file(doc.file_id)
    file_path = f"temp_{doc.file_id}.pdf"
    await file.download_to_drive(file_path)
    
    text = ""
    with fitz.open(file_path) as pdf:
        for page in pdf:
            text += page.get_text()
    
    os.remove(file_path)
    await process_ai_request(update, context, f"Проанализируй это резюме:\n\n{text}", is_file=True)

if __name__ == '__main__':
    db.init_db()
    
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("connect", connect_google))
    app.add_handler(CommandHandler("calendar", show_calendar))
    app.add_handler(CommandHandler("disconnect", disconnect_google))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    loop = asyncio.get_event_loop()
    loop.create_task(notification_loop(app))
    
    print("Бот запущен...")
    app.run_polling()
