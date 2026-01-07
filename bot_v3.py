import logging
import os
import asyncio
import base64
import json
import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from mistralai import Mistral
from collections import deque
from google_calendar import GoogleCalendar

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# API Ключи
MISTRAL_API_KEY = "WOkX5dBJuq8I9sMkVqmlpNwjVrzX19i3"
TELEGRAM_BOT_TOKEN = "8399347076:AAFLtRxXEKESWuTQb19vc6mhMQph7rHxsLg"

# Инициализация
mistral_client = Mistral(api_key=MISTRAL_API_KEY)
calendar_manager = GoogleCalendar()
user_memory = {}

SYSTEM_PROMPT = f"""
Ты — экспертный ИИ-ассистент для HR. Текущая дата: {datetime.datetime.now().strftime('%Y-%m-%d')}.
Ты можешь управлять Google Календарем пользователя.
Если пользователь просит назначить встречу или интервью, используй функцию `add_calendar_event`.
Если пользователь хочет посмотреть расписание, используй `list_calendar_events`.
"""

tools = [
    {
        "type": "function",
        "function": {
            "name": "add_calendar_event",
            "description": "Добавить событие в Google Календарь",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Заголовок встречи"},
                    "start_time": {"type": "string", "description": "Время начала в формате ISO (например, 2024-01-01T10:00:00Z)"},
                    "end_time": {"type": "string", "description": "Время окончания в формате ISO"},
                    "description": {"type": "string", "description": "Описание встречи"}
                },
                "required": ["summary", "start_time", "end_time"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_calendar_events",
            "description": "Показать список предстоящих событий из календаря",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_results": {"type": "integer", "default": 10}
                }
            }
        }
    }
]

def get_chat_history(chat_id):
    if chat_id not in user_memory:
        user_memory[chat_id] = deque(maxlen=10)
    return list(user_memory[chat_id])

def add_to_history(chat_id, role, content):
    if chat_id not in user_memory:
        user_memory[chat_id] = deque(maxlen=10)
    user_memory[chat_id].append({"role": role, "content": content})

async def process_ai_request(update, context, user_input, image_data=None):
    chat_id = update.effective_chat.id
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    
    status_msg = await update.message.reply_text("...")
    history = get_chat_history(chat_id)
    
    content = [{"type": "text", "text": user_input}]
    if image_data:
        content.append({"type": "image_url", "image_url": f"data:image/jpeg;base64,{image_data}"})

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history + [{"role": "user", "content": content}]
    
    try:
        model = "pixtral-12b-2409" if image_data else "mistral-large-latest"
        
        response = await mistral_client.chat.complete_async(
            model=model,
            messages=messages,
            tools=tools if not image_data else None # Vision модели могут не поддерживать tools в некоторых версиях
        )
        
        msg = response.choices[0].message
        
        if msg.tool_calls:
            for tool_call in msg.tool_calls:
                func_name = tool_call.function.name
                args = json.loads(tool_call.function.arguments)
                
                if func_name == "add_calendar_event":
                    result = calendar_manager.add_event(**args)
                elif func_name == "list_calendar_events":
                    result = calendar_manager.list_events(**args)
                else:
                    result = "Неизвестная функция"
                
                messages.append(msg)
                messages.append({
                    "role": "tool",
                    "name": func_name,
                    "content": result,
                    "tool_call_id": tool_call.id
                })
            
            # Повторный запрос после выполнения функции
            response = await mistral_client.chat.complete_async(
                model="mistral-large-latest",
                messages=messages
            )
            full_response = response.choices[0].message.content
        else:
            full_response = msg.content
        
        if full_response:
            add_to_history(chat_id, "user", user_input)
            add_to_history(chat_id, "assistant", full_response)
            await status_msg.edit_text(full_response, parse_mode='Markdown')
                    
    except Exception as e:
        logging.error(f"Error: {e}")
        await status_msg.edit_text(f"Ошибка: {str(e)[:100]}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Бот обновлен! Теперь я поддерживаю Google Календарь, PDF и фото.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text:
        await process_ai_request(update, context, update.message.text)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    file_bytes = await file.download_as_bytearray()
    image_base64 = base64.b64encode(file_bytes).decode('utf-8')
    await process_ai_request(update, context, update.message.caption or "Анализ фото", image_data=image_base64)

if __name__ == '__main__':
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.run_polling()
