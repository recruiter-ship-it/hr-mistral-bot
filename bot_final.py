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

# Восстановление credentials.json
if GOOGLE_CREDENTIALS and not os.path.exists('credentials.json'):
    with open('credentials.json', 'w') as f:
        f.write(GOOGLE_CREDENTIALS)
    logging.info("credentials.json restored from environment variable")

# Инициализация
mistral_client = Mistral(api_key=MISTRAL_API_KEY)
db = Database()
calendar_mgr = GoogleCalendarManager()
user_memory = {}

SYSTEM_PROMPT = "Ты — экспертный ИИ-ассистент для HR. Ты помогаешь с рекрутингом, анализом резюме и планированием."

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔗 Подключить Календарь", callback_query_data='connect_calendar')],
        [InlineKeyboardButton("📅 Моё расписание", callback_query_data='list_events')],
        [InlineKeyboardButton("❓ Помощь", callback_query_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = (
        "👋 *Привет! Я твой персональный HR-ассистент.*\n\n"
        "🚀 **Что я умею:**\n"
        "• Анализировать резюме и фото (просто пришли файл)\n"
        "• Планировать встречи в твоем календаре\n"
        "• Напоминать о важных событиях\n\n"
        "Чтобы начать работу с календарем, нажми кнопку ниже 👇"
    )
    
    if update.message:
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.callback_query.edit_message_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📖 *Доступные команды:*\n\n"
        "🔗 /connect — Подключить Google Календарь\n"
        "📅 /events — Посмотреть мои ближайшие события\n"
        "❓ /help — Показать это сообщение\n\n"
        "💡 *Также ты можешь:*\n"
        "• Прислать PDF резюме или фото для анализа\n"
        "• Просто писать вопросы по HR и рекрутингу"
    )
    await update.effective_message.reply_text(help_text, parse_mode='Markdown')

async def connect_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not os.path.exists('credentials.json'):
        await update.message.reply_text("❌ Ошибка: Система не настроена. Пожалуйста, загрузите credentials.json.")
        return
    
    flow = calendar_mgr.get_flow()
    # Указываем Redirect URI явно для Web Application
    flow.redirect_uri = 'https://google.com'
    auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')
    
    instructions = (
        "🔐 **Подключение календаря:**\n\n"
        f"1. Перейдите по ссылке: [Авторизоваться в Google]({auth_url})\n"
        "2. Войдите в аккаунт и нажмите 'Разрешить'\n"
        "3. **Скопируйте код** из адресной строки (после `code=...`) или со страницы и отправьте его мне сюда."
    )
    await update.message.reply_text(instructions, parse_mode='Markdown')
    context.user_data['awaiting_auth_code'] = True

async def events_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    token = db.get_token(user_id)
    if not token:
        await update.message.reply_text("❌ Сначала подключите календарь через /connect")
        return
    
    res, updated_token = calendar_mgr.list_events(token)
    if updated_token:
        db.save_token(user_id, updated_token)
    await send_long_message(update, res)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == 'connect_calendar':
        if not os.path.exists('credentials.json'):
            await query.edit_message_text("❌ Ошибка: Система не настроена. Пожалуйста, загрузите credentials.json.")
            return
        
        flow = calendar_mgr.get_flow()
        auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')
        
        instructions = (
            "🔐 **Шаги для подключения:**\n\n"
            "1. Нажми на кнопку '👉 Авторизоваться' ниже\n"
            "2. Войди в свой Google-аккаунт\n"
            "3. Нажми 'Разрешить'\n"
            "4. **Скопируй полученный код** и отправь его мне в ответном сообщении."
        )
        
        keyboard = [[InlineKeyboardButton("👉 Авторизоваться", url=auth_url)]]
        await query.edit_message_text(instructions, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        context.user_data['awaiting_auth_code'] = True

    elif query.data == 'help':
        await help_command(update, context)

    elif query.data == 'list_events':
        token = db.get_token(user_id)
        if not token:
            await query.edit_message_text("Сначала подключите календарь через /start")
            return
        res, updated_token = calendar_mgr.list_events(token)
        if updated_token: db.save_token(user_id, updated_token)
        await query.edit_message_text(res)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if context.user_data.get('awaiting_auth_code'):
        try:
            flow = calendar_mgr.get_flow()
            flow.redirect_uri = 'https://google.com'
            flow.fetch_token(code=text)
            db.save_token(user_id, json.loads(flow.credentials.to_json()))
            context.user_data['awaiting_auth_code'] = False
            await update.message.reply_text("✅ Календарь успешно подключен!")
            return
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка авторизации: {str(e)}")
            return

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
        tools = None
        if token:
            tools = [{"type": "function", "function": {"name": "add_calendar_event", "description": "Добавить встречу", "parameters": {"type": "object", "properties": {"summary": {"type": "string"}, "start_time": {"type": "string"}, "end_time": {"type": "string"}}, "required": ["summary", "start_time", "end_time"]}}}]

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
        await send_long_message(update, full_response, parse_mode='Markdown' if "```" in full_response else None)
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {str(e)[:100]}")

async def send_long_message(update, text, parse_mode=None):
    if len(text) <= 4096:
        await update.message.reply_text(text, parse_mode=parse_mode)
    else:
        for i in range(0, len(text), 4096):
            await update.message.reply_text(text[i:i+4096], parse_mode=parse_mode)

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
            if updated_token: db.save_token(user_id, updated_token)
            now = datetime.datetime.utcnow().isoformat() + 'Z'
            ten_mins_later = (datetime.datetime.utcnow() + datetime.timedelta(minutes=10)).isoformat() + 'Z'
            events_result = service.events().list(calendarId='primary', timeMin=now, timeMax=ten_mins_later, singleEvents=True).execute()
            for event in events_result.get('items', []):
                await context.bot.send_message(chat_id=user_id, text=f"🔔 Напоминание: *{event['summary']}*", parse_mode='Markdown')
        except: pass

if __name__ == '__main__':
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    application.job_queue.run_repeating(reminder_task, interval=300, first=10)
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('connect', connect_command))
    application.add_handler(CommandHandler('events', events_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.run_polling()
