import logging
import os
import asyncio
import json
import fitz  # PyMuPDF
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from telegram.error import BadRequest
from mistralai.client import MistralClient
from mistralai.models.chat_completion import ToolCall

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
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "WOkX5dBJuq8I9sMkVqmlpNwjVrzX19i3")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8399347076:AAFLtRxXEKESWuTQb19vc6mhMQph7rHxsLg")

# Системный промпт
AGENT_INSTRUCTIONS = """
Ты — **HRик HуяRік**, экспертный ИИ-ассистент для HR-команды и рекрутеров. Твоя цель — повышать эффективность HR-процессов, помогать нанимать лучших талантов и развивать корпоративную культуру.

Твои знания ограничены началом 2024 года. Сейчас 2026 год.
ВАЖНО: Для любых вопросов о текущих событиях, ценах, курсах валют, политиках или новостях ты ОБЯЗАН использовать инструмент `web_search`. Не пытайся угадать ответ.

РАССУЖДЕНИЕ (Chain of Thought): Перед тем как дать ответ, проанализируй задачу, разбей её на шаги и убедись в актуальности данных.
"""

# Инициализация клиента Mistral
mistral_client = MistralClient(api_key=MISTRAL_API_KEY)

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

async def process_ai_request(update, context, user_input, is_file=False):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    message = await update.message.reply_text("Анализирую..." if is_file else "...")
    
    if chat_id not in user_conversations:
        user_conversations[chat_id] = []
    
    user_conversations[chat_id].append({"role": "user", "content": user_input})
    history = user_conversations[chat_id][-10:]
    
    # Определение доступных инструментов
    tools = [{"type": "web_search"}] # Всегда предлагаем поиск
    if db.is_calendar_connected(user_id):
        tools.append({
            "type": "function",
            "function": {
                "name": "get_calendar_events",
                "description": "Получить события из Google Календаря на указанное количество дней.",
                "parameters": {"type": "object", "properties": {"days": {"type": "integer", "description": "Количество дней для просмотра."}}}
            }
        })

    try:
        # Первый вызов для определения, нужен ли инструмент
        response = mistral_client.chat(
            model="mistral-large-latest",
            messages=[{"role": "system", "content": get_current_instructions()}] + history,
            tools=tools,
            tool_choice="any"
        )
        
        history.append(response.choices[0].message)
        tool_calls = response.choices[0].message.tool_calls

        # Если есть вызовы инструментов, обрабатываем их
        if tool_calls:
            tool_results = []
            for tool_call in tool_calls:
                if tool_call.function.name == "get_calendar_events":
                    # Безопасное извлечение аргументов
                    try:
                        args = json.loads(tool_call.function.arguments)
                        days = args.get('days', 7) # По умолчанию 7 дней
                        
                        # Исправленный вызов: GoogleCalendarManager() и list_events(user_id, days)
                        manager = GoogleCalendarManager()
                        result_text, _ = manager.list_events(user_id, days)
                        
                        # Передаем только текст, так как Mistral не нужен полный JSON
                        result = result_text 
                    except Exception as e:
                        result = f"Ошибка при вызове календаря: {e}"
                    
                    # Форматируем результат для Mistral
                    tool_results.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": "get_calendar_events",
                        "content": result
                    })
            
            history.extend(tool_results)

            # Финальный вызов с результатами инструментов
            final_response = mistral_client.chat(
                model="mistral-large-latest",
                messages=[{"role": "system", "content": get_current_instructions()}] + history
            )
            final_content = final_response.choices[0].message.content
            history.append(final_response.choices[0].message)
        else:
            # Если инструментов не было, используем первый ответ
            final_content = response.choices[0].message.content

        user_conversations[chat_id] = history
        await context.bot.edit_message_text(chat_id=chat_id, message_id=message.message_id, text=final_content, parse_mode='Markdown')

    except Exception as e:
        logging.error(f"AI Error: {e}")
        await context.bot.edit_message_text(chat_id=chat_id, message_id=message.message_id, text=f"❌ Ошибка: {str(e)}")

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
                    
                    tool_results.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": "get_calendar_events",
                        "content": json.dumps(result, ensure_ascii=False)
                    })
            
            history.extend(tool_results)

            # Финальный вызов с результатами инструментов
            final_response = mistral_client.chat(
                model="mistral-large-latest",
                messages=[{"role": "system", "content": get_current_instructions()}] + history
            )
            final_content = final_response.choices[0].message.content
            history.append(final_response.choices[0].message)
        else:
            # Если инструментов не было, используем первый ответ
            final_content = response.choices[0].message.content

        user_conversations[chat_id] = history
        await context.bot.edit_message_text(chat_id=chat_id, message_id=message.message_id, text=final_content, parse_mode='Markdown')

    except Exception as e:
        logging.error(f"AI Error: {e}")
        await context.bot.edit_message_text(chat_id=chat_id, message_id=message.message_id, text=f"❌ Ошибка: {str(e)}")

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
