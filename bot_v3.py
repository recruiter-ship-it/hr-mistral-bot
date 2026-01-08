import logging
import os
import asyncio
import base64
import json
import datetime
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from mistralai import Mistral
from collections import deque
from google_calendar import GoogleCalendarManager
from database import Database

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Конфигурация
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "WOkX5dBJuq8I9sMkVqmlpNwjVrzX19i3")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8399347076:AAFLtRxXEKESWuTQb19vc6mhMQph7rHxsLg")
GOOGLE_CREDENTIALS = os.getenv("GOOGLE_CREDENTIALS")

if GOOGLE_CREDENTIALS and not os.path.exists("credentials.json"):
    with open("credentials.json", "w") as f:
        f.write(GOOGLE_CREDENTIALS)
    logging.info("credentials.json restored")

# Инициализация
mistral_client = Mistral(api_key=MISTRAL_API_KEY)
db = Database()
calendar_mgr = GoogleCalendarManager()
user_memory = {}

# Системный промпт
SYSTEM_PROMPT = """Ты — экспертный ИИ-ассистент для HR. Ты помогаешь с рекрутингом, анализом резюме и планированием.
Если пользователь подключил Google Календарь, ты можешь создавать встречи и просматривать расписание.
"""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    keyboard = [
        [InlineKeyboardButton("📅 Подключить Google Календарь", callback_query_data='connect_calendar')],
        [InlineKeyboardButton("📋 Мои события", callback_query_data='list_events')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Привет! Я твой HR-ассистент. Я могу анализировать резюме, фото и помогать с календарем.\n\n"
        "Чтобы я мог управлять вашими встречами, нажмите кнопку ниже:",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == 'connect_calendar':
        if not os.path.exists('credentials.json'):
            await query.edit_message_text("Ошибка: Файл credentials.json не найден на сервере. Обратитесь к администратору.")
            return
        
        flow = calendar_mgr.get_flow()
        auth_url, _ = flow.authorization_url(prompt='consent')
        
        await query.edit_message_text(
            f"Для подключения календаря перейдите по ссылке и пришлите мне полученный код:\n\n[Авторизоваться в Google]({auth_url})",
            parse_mode='Markdown'
        )
        context.user_data['awaiting_auth_code'] = True

    elif query.data == 'list_events':
        token = db.get_token(user_id)
        if not token:
            await query.edit_message_text("Сначала подключите календарь через /start")
            return
        
        res, updated_token = calendar_mgr.list_events(token)
        if updated_token:
            db.save_token(user_id, updated_token)
        await query.edit_message_text(res)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    # Обработка кода авторизации
    if context.user_data.get('awaiting_auth_code'):
        try:
            flow = calendar_mgr.get_flow()
            flow.fetch_token(code=text)
            creds = flow.credentials
            db.save_token(user_id, json.loads(creds.to_json()))
            context.user_data['awaiting_auth_code'] = False
            await update.message.reply_text("✅ Календарь успешно подключен!")
            return
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка авторизации: {str(e)}")
            return

    # Обычный запрос к ИИ
    await process_ai_request(update, context, text)

async def process_ai_request(update, context, user_input, image_data=None):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    
    token = db.get_token(user_id)
    history = user_memory.get(chat_id, deque(maxlen=10))
    
    content = [{"type": "text", "text": user_input}]
    if image_data:
        content.append({"type": "image_url", "image_url": f"data:image/jpeg;base64,{image_data}"})

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + list(history) + [{"role": "user", "content": content}]
    
    try:
        # Инструменты добавляем только если есть токен
        tools = None
        if token:
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "add_calendar_event",
                        "description": "Добавить встречу в календарь",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "summary": {"type": "string"},
                                "start_time": {"type": "string", "description": "ISO format"},
                                "end_time": {"type": "string", "description": "ISO format"}
                            },
                            "required": ["summary", "start_time", "end_time"]
                        }
                    }
                }
            ]

        response = await mistral_client.chat.complete_async(
            model="pixtral-12b-2409" if image_data else "mistral-large-latest",
            messages=messages,
            tools=tools
        )
        
        msg = response.choices[0].message
        if msg.tool_calls and token:
            for tool_call in msg.tool_calls:
                args = json.loads(tool_call.function.arguments)
                res, updated_token = calendar_mgr.add_event(token, **args)
                if updated_token: db.save_token(user_id, updated_token)
                
                messages.append(msg)
                messages.append({"role": "tool", "name": tool_call.function.name, "content": res, "tool_call_id": tool_call.id})
            
            response = await mistral_client.chat.complete_async(model="mistral-large-latest", messages=messages)
            full_response = response.choices[0].message.content
        else:
            full_response = msg.content

        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": full_response})
        user_memory[chat_id] = history
        
        await update.message.reply_text(full_response, parse_mode='Markdown' if "```" in full_response else None)
    except Exception as e:
        logging.error(f"AI Error: {e}")
        await update.message.reply_text(f"Ошибка: {str(e)[:100]}")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    file_bytes = await file.download_as_bytearray()
    image_base64 = base64.b64encode(file_bytes).decode('utf-8')
    await process_ai_request(update, context, update.message.caption or "Анализ фото", image_data=image_base64)

async def reminder_task(context: ContextTypes.DEFAULT_TYPE):
    with sqlite3.connect("bot_data.db") as conn:
        cursor = conn.execute("SELECT user_id, google_token FROM users WHERE google_token IS NOT NULL")
        users = cursor.fetchall()
    
    for user_id, token_json in users:
        try:
            token = json.loads(token_json)
            service, updated_token = calendar_mgr.get_service(token)
            if updated_token:
                db.save_token(user_id, updated_token)
            
            now = datetime.datetime.utcnow().isoformat() + 'Z'
            ten_mins_later = (datetime.datetime.utcnow() + datetime.timedelta(minutes=10)).isoformat() + 'Z'
            
            events_result = service.events().list(
                calendarId='primary', timeMin=now, timeMax=ten_mins_later,
                singleEvents=True
            ).execute()
            
            for event in events_result.get('items', []):
                event_id = event['id']
                # Простая проверка, чтобы не спамить (можно улучшить через БД)
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"🔔 Напоминание: Скоро начнется встреча: *{event['summary']}*",
                    parse_mode='Markdown'
                )
        except Exception as e:
            logging.error(f"Reminder error for {user_id}: {e}")

if __name__ == '__main__':
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    job_queue = application.job_queue
    job_queue.run_repeating(reminder_task, interval=300, first=10) # Каждые 5 минут
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    logging.info("Бот запущен...")
    application.run_polling()
