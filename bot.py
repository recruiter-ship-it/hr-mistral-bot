import os
import json
import asyncio
import logging
import base64
import sqlite3
import requests
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from mistralai import Mistral
import fitz  # PyMuPDF
from google_calendar import GoogleCalendarManager
import database as db

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='bot.log'
)

# Инициализация API ключей
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
GOOGLE_CREDENTIALS_BASE64 = os.getenv("GOOGLE_CREDENTIALS")

# Восстановление credentials.json из секрета
if GOOGLE_CREDENTIALS_BASE64:
    with open("credentials.json", "wb") as f:
        f.write(base64.b64decode(GOOGLE_CREDENTIALS_BASE64))

# Инициализация клиентов
mistral_client = Mistral(api_key=MISTRAL_API_KEY)
calendar_mgr = GoogleCalendarManager()

async def send_long_message(update, text):
    """Разбивает длинные сообщения на части по 4096 символов."""
    if not text:
        return
    for i in range(0, len(text), 4096):
        await update.message.reply_text(text[i:i+4096])

def search_internet(query):
    """Поиск информации в интернете через Serper API."""
    if not SERPER_API_KEY:
        return "Ошибка: API ключ для поиска не настроен."
    
    url = "https://google.serper.dev/search"
    payload = json.dumps({"q": query, "gl": "ru", "hl": "ru"})
    headers = {
        'X-API-KEY': SERPER_API_KEY,
        'Content-Type': 'application/json'
    }
    
    try:
        response = requests.post(url, headers=headers, data=payload)
        results = response.json()
        search_text = "Результаты поиска:\n"
        for result in results.get('organic', [])[:3]:
            search_text += f"- {result.get('title')}: {result.get('snippet')}\n"
        return search_text
    except Exception as e:
        return f"Ошибка при поиске: {str(e)}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db.init_db()
    
    keyboard = [
        [InlineKeyboardButton("🔗 Как подключить Календарь", callback_data='how_to_connect')],
        [InlineKeyboardButton("📅 Моё расписание", callback_data='my_events')],
        [InlineKeyboardButton("❓ Помощь", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = (
        f"Привет, {update.effective_user.first_name}! 👋\n\n"
        "Я твой продвинутый HR-ассистент на базе Mistral AI.\n\n"
        "Что я умею:\n"
        "🔍 Анализировать резюме (PDF и фото)\n"
        "📅 Работать с твоим Google Календарем\n"
        "✍️ Составлять описания вакансий и вопросы для интервью\n"
        "🚀 Отвечать на любые вопросы по рекрутингу\n\n"
        "Чтобы я мог видеть твой календарь, нажми кнопку ниже!"
    )
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode=None)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🤖 Команды бота:\n\n"
        "/start - Главное меню\n"
        "/connect - Инструкция по подключению календаря\n"
        "/events - Показать ближайшие встречи\n"
        "/help - Список всех команд\n\n"
        "Возможности:\n"
        "• Пришли мне PDF или фото резюме для анализа\n"
        "• Попроси назначить встречу (например: 'Назначь интервью на завтра в 12:00')\n"
        "• Просто пиши вопросы по HR"
    )
    await update.effective_message.reply_text(help_text, parse_mode=None)

async def connect_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    service_email = "hr-bot-640@hr-bot-483711.iam.gserviceaccount.com"
    instructions = (
        "🔐 Как подключить ваш Google Календарь:\n\n"
        "1. Откройте ваш Google Календарь в браузере.\n"
        "2. Нажмите на шестеренку ⚙️ -> Настройки.\n"
        "3. В левом меню выберите ваш календарь в разделе 'Настройки моих календарей'.\n"
        "4. Найдите раздел 'Доступ для отдельных пользователей'.\n"
        "5. Нажмите '+ Добавить пользователей'.\n"
        f"6. Введите этот email: {service_email}\n"
        "7. В разрешениях выберите 'Внесение изменений и предоставление доступа'.\n"
        "8. Нажмите 'Отправить'.\n\n"
        "9. Финальный шаг: Пришлите мне ваш Gmail адрес (например: example@gmail.com), чтобы я знал, какой календарь проверять."
    )
    await update.message.reply_text(instructions, parse_mode=None)
    context.user_data['awaiting_gmail'] = True

async def events_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    gmail = db.get_token(user_id) # Используем поле token для хранения Gmail в этой версии
    
    if not gmail:
        await update.message.reply_text("❌ Календарь не подключен. Используйте /connect")
        return
    
    # В нашей БД gmail хранится как строка (ранее там был JSON токена)
    if isinstance(gmail, dict):
        gmail = gmail.get('email', '') # На случай если там старые данные
    
    res, _ = calendar_mgr.list_events(gmail)
    await update.message.reply_text(res)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    # Если ждем Gmail для подключения
    if context.user_data.get('awaiting_gmail'):
        if "@" in text:
            db.save_token(user_id, text) # Сохраняем Gmail адрес
            context.user_data['awaiting_gmail'] = False
            await update.message.reply_text(f"✅ Календарь `{text}` успешно привязан! Теперь я могу видеть ваши встречи.")
        else:
            await update.message.reply_text("❌ Пожалуйста, введите корректный Gmail адрес.")
        return

    # Обычный чат с Mistral
    try:
        # Простая логика: если в запросе есть слова про поиск или новости, используем Serper
        search_keywords = ['найди', 'поиск', 'новости', 'интернет', 'узнай', 'кто такой', 'что такое']
        context_text = ""
        if any(word in text.lower() for word in search_keywords):
            await update.message.reply_text("🔍 Ищу информацию в интернете...")
            context_text = search_internet(text)

        system_prompt = "Ты профессиональный HR-ассистент. Отвечай четко и по делу. НЕ используй Markdown разметку (звездочки, жирный шрифт). Используй только обычный текст и эмодзи."
        user_content = text
        if context_text:
            user_content = f"Используй эти данные из интернета для ответа:\n{context_text}\n\nВопрос пользователя: {text}"

        response = mistral_client.chat.complete(
            model="mistral-small-latest",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ]
        )
        await send_long_message(update, response.choices[0].message.content)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка ИИ: {str(e)}")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.document.get_file()
    file_path = f"temp_{update.message.document.file_name}"
    await file.download_to_drive(file_path)
    
    caption = update.message.caption if update.message.caption else ""
    
    if file_path.endswith('.pdf'):
        doc = fitz.open(file_path)
        pdf_text = "".join([page.get_text() for page in doc])
        
        system_prompt = "Ты профессиональный HR-ассистент. НЕ используй Markdown разметку (звездочки, жирный шрифт). Используй только обычный текст и эмодзи."
        user_prompt = f"Проанализируй это резюме. "
        if caption:
            user_prompt += f"Учти следующий комментарий/вопрос пользователя: {caption}\n\n"
        else:
            user_prompt += "Дай краткую оценку:\n\n"
        
        user_prompt += f"Текст резюме:\n{pdf_text}"
        
        response = mistral_client.chat.complete(
            model="mistral-small-latest",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        await send_long_message(update, response.choices[0].message.content)
    
    os.remove(file_path)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'how_to_connect':
        await connect_command(query, context)
    elif query.data == 'my_events':
        await events_command(query, context)
    elif query.data == 'help':
        await help_command(query, context)

if __name__ == '__main__':
    db.init_db()
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("connect", connect_command))
    app.add_handler(CommandHandler("events", events_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("Бот запущен...")
    app.run_polling()
