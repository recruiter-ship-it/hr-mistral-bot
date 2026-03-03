#!/usr/bin/env python3
"""
HR Mistral Bot - Simplified for GitHub Actions
Без MCP, без сложных зависимостей - просто работает
"""
import logging
import os
import asyncio
import json
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

# API Ключи
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "AEE3rpaceKHZzBtbVKnN9CWoNdpjlp2l")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8399347076:AAFLtRxXEKESWuTQb19vc6mhMQph7rHxsLg")

# Системный промпт
SYSTEM_PROMPT = """Ты — HRик, экспертный ИИ-ассистент для HR-команды и рекрутеров.

Ты дружелюбный, профессиональный и всегда готов помочь. Отвечай на русском языке.

Ты можешь помочь с:
- Кандидатами (сохранение, поиск, статусы)
- Вакансиями (создание, список)
- Документами (офферы, welcome-письма)
- HR вопросами и консультациями

Используй Markdown для форматирования ответов."""

# Инициализация клиента Mistral
mistral_client = Mistral(api_key=MISTRAL_API_KEY)

# Хранилище conversation_id для каждого пользователя
user_conversations = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    chat_id = update.effective_chat.id
    if chat_id in user_conversations:
        del user_conversations[chat_id]
    
    await update.message.reply_text(
        "👋 Привет! Я **HRик** — твой ИИ-ассистент для HR!\n\n"
        "Я могу помочь с:\n"
        "• 👥 Кандидатами\n"
        "• 📋 Вакансиями\n"
        "• 📄 Документами\n"
        "• ❓ HR консультациями\n\n"
        "Просто напиши мне вопрос!",
        parse_mode='Markdown'
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений через Mistral Agent"""
    chat_id = update.effective_chat.id
    user_input = update.message.text
    
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    
    try:
        # Создаём или продолжаем conversation
        if chat_id in user_conversations:
            response = mistral_client.beta.conversations.append(
                conversation_id=user_conversations[chat_id],
                inputs=user_input
            )
        else:
            # Создаём агента и начинаем разговор
            agent = mistral_client.beta.agents.create(
                model="mistral-small-latest",
                name="HR Assistant",
                description="HR AI Assistant",
                instructions=SYSTEM_PROMPT,
                completion_args={"temperature": 0.7}
            )
            response = mistral_client.beta.conversations.start(
                agent_id=agent.id,
                inputs=user_input
            )
        
        # Сохраняем conversation_id
        user_conversations[chat_id] = response.conversation_id
        
        # Извлекаем ответ
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
            reply = "Не удалось получить ответ. Попробуйте ещё раз."
        
        # Отправляем ответ
        try:
            await update.message.reply_text(reply, parse_mode='Markdown')
        except BadRequest:
            # Если Markdown не работает
            await update.message.reply_text(reply)
            
    except Exception as e:
        logging.error(f"Error: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")


if __name__ == '__main__':
    logging.info("🚀 Starting HR Bot (GitHub Actions version)...")
    logging.info(f"Python: {os.sys.version}")
    logging.info(f"Mistral API Key: {'SET' if MISTRAL_API_KEY else 'NOT SET'}")
    logging.info(f"Telegram Token: {'SET' if TELEGRAM_BOT_TOKEN else 'NOT SET'}")
    
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Команды
    application.add_handler(CommandHandler('start', start))
    
    # Сообщения
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    logging.info("✅ Bot ready, starting polling...")
    application.run_polling()
