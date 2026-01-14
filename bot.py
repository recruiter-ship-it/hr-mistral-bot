"""
Telegram bot entrypoint for the HR Mistral assistant.

This module wires together all of the bot's capabilities: PDF and image
analysis, Google Calendar integration, internet search via Mistral Web Search, and
interaction with the Mistral AI chat API. It also persists conversation
history to a SQLite database to provide context-aware responses across
multiple interactions with the same user.

The bot responds to simple commands (/start, /connect, /events, /help,
/cancel) and free-form HR questions. When the user asks something that
requires external information (for example, "найди" or "что такое"), the bot
performs a web search via the integrated Mistral Web Search tool and incorporates the results into its
response.
"""

import os
import json
import asyncio
import logging
import base64
try:
    import requests
except ImportError:
    # Lazily install requests if it's not available. This fallback is useful
    # when the bot is packaged into environments that do not preinstall
    # requests. Note that this will block the event loop briefly.
    import os as _os
    _os.system("pip install requests")
    import requests
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
)
from mistralai import Mistral
import fitz  # PyMuPDF
from google_calendar import GoogleCalendarManager
import database as db


# Configure logging to both file and stdout
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='bot.log'
)


# Retrieve API keys from environment variables. These should be provided via
# GitHub Actions secrets or a .env file when running locally.
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
GOOGLE_CREDENTIALS_BASE64 = os.getenv("GOOGLE_CREDENTIALS")


# Restore credentials.json from base64 secret if present. This is used by
# google_calendar.GoogleCalendarManager. Padding is corrected if needed.
if GOOGLE_CREDENTIALS_BASE64:
    try:
        # Fix base64 padding if necessary
        missing_padding = len(GOOGLE_CREDENTIALS_BASE64) % 4
        if missing_padding:
            GOOGLE_CREDENTIALS_BASE64 += '=' * (4 - missing_padding)

        with open("credentials.json", "wb") as f:
            f.write(base64.b64decode(GOOGLE_CREDENTIALS_BASE64))
        logging.info("credentials.json successfully restored")
    except Exception as e:
        logging.error(f"Error restoring credentials.json: {e}")


# Initialize external clients
mistral_client = Mistral(api_key=MISTRAL_API_KEY)
calendar_mgr = GoogleCalendarManager()


async def send_long_message(update: Update, text: str) -> None:
    """
    Reply with a potentially long message by splitting it into chunks that are
    within Telegram's 4096 character limit.

    :param update: Telegram update object.
    :param text: The message to send.
    """
    if not text:
        return
    for i in range(0, len(text), 4096):
        await update.message.reply_text(text[i : i + 4096])


def search_internet(query: str) -> str:
    """
    Perform an internet search using the Mistral Web Search tool.

    This function contacts Mistral's built-in ``web_search`` tool to obtain
    up-to-date information for the given query. If the ``MISTRAL_API_KEY``
    environment variable is not set or an exception is raised during the
    request, a human-readable error message is returned instead.

    :param query: The search query.
    :return: A formatted string with search results or an error message.
    """
    # If the Mistral API key is not configured, we cannot perform a search.
    if not MISTRAL_API_KEY:
        return "Поиск недоступен: не задан API‑ключ Mistral"

    try:
        # Prepare the messages and tools payload. The ``web_search`` tool is
        # enabled via the tools parameter so the model can fetch fresh
        # information.
        messages = [
            {"role": "user", "content": f"Найди в интернете: {query}"}
        ]
        
        # Perform the chat completion with the web_search tool enabled.
        response = mistral_client.chat.complete(
            model="mistral-small-latest",
            messages=messages,
            tools=[{"type": "web_search"}]
        )
        return response.choices[0].message.content
    except Exception as e:
        # Return an error message if the search fails for any reason.
        return f"Ошибка при поиске: {e}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle the /start command. Presents the user with an interactive menu and
    initializes the database tables if they haven't been created yet.
    """
    user_id = update.effective_user.id
    db.init_db()

    keyboard = [
        [InlineKeyboardButton("🔗 Как подключить Календарь", callback_data='how_to_connect')],
        [InlineKeyboardButton("📅 Моё расписание", callback_data='my_events')],
        [InlineKeyboardButton("❓ Помощь", callback_data='help')],
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


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a help message describing available commands and features."""
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


async def connect_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Send instructions on how to connect the user's Google Calendar.
    Sets a flag in context.user_data so that the next message containing an
    email address is treated as the Gmail account to link.
    """
    service_email = "hr-bot-640@hr-bot-483711.iam.gserviceaccount.com"
    instructions = (
        "🔐 Как подключить ваш Google Календарь:\n\n"
        "1. Откройте ваш Google Календарь в браузере.\n"
        "2. Нажмите на шестерёнку ⚙️ -> Настройки.\n"
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


async def events_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Show the user's upcoming events from their Google Calendar. Uses the Gmail
    address stored in the database as the calendar ID. If the user has not
    connected a calendar yet, a helpful error message is returned.
    """
    user_id = update.effective_user.id
    gmail = db.get_token(user_id)  # We use the token field to store the Gmail address in this version
    if not gmail:
        await update.message.reply_text("❌ Календарь не подключен. Используйте /connect")
        return
    # In our DB gmail is stored as a string (previously it was JSON token)
    if isinstance(gmail, dict):
        gmail = gmail.get('email', '')  # Fallback in case old data is present
    res, _ = calendar_mgr.list_events(gmail)
    await update.message.reply_text(res)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cancel any pending action (such as awaiting Gmail) and reset state."""
    context.user_data['awaiting_gmail'] = False
    await update.message.reply_text("❌ Действие отменено. Теперь вы можете просто общаться со мной.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Primary message handler for free-form text input.

    This function covers two scenarios:
    1. If the bot is waiting for the user's Gmail address (after /connect), it
       stores the address and acknowledges the calendar linkage.
    2. Otherwise, it sends the user's query to the Mistral API, optionally
       augmenting the prompt with recent conversation history and search
       results from the internet. Both user and assistant messages are
       persisted to the database to maintain context.
    """
    user_id = update.effective_user.id
    text = update.message.text

    # If we are waiting for the user's Gmail to link the calendar
    if context.user_data.get('awaiting_gmail'):
        if "@" in text.lower():
            db.save_token(user_id, text)  # Save Gmail address
            context.user_data['awaiting_gmail'] = False
            await update.message.reply_text(
                f"✅ Календарь {text} успешно привязан! Теперь я могу видеть ваши встречи."
            )
            # Record the user's email message in conversation history
            db.save_message(user_id, "user", text)
            return
        elif text.startswith('/'):
            # If a command is entered instead of an email, exit the awaiting
            # state so the command can be processed normally.
            context.user_data['awaiting_gmail'] = False
        else:
            # If the message is not an email address, reset the flag and
            # continue to process it as a regular chat message. This avoids
            # blocking the conversation.
            context.user_data['awaiting_gmail'] = False

    # Normal chat with Mistral
    try:
        search_keywords = [
            'найди', 'поиск', 'новости', 'интернет', 'узнай', 'кто такой', 'что такое'
        ]
        context_text = ""
        if any(word in text.lower() for word in search_keywords):
            await update.message.reply_text("🔍 Ищу информацию в интернете...")
            context_text = search_internet(text)

        # Retrieve recent conversation history for context (limited to 5 for faster processing)
        history = db.get_history(user_id, limit=5)

        # System prompt provides high-level instructions. This is always the first
        # message in the conversation.
        system_prompt = (
            "Ты профессиональный HR-ассистент. Отвечай чётко и по делу. "
            "НЕ используй Markdown разметку (звёздочки, жирный шрифт). "
            "Используй только обычный текст и эмодзи."
        )
        messages_list = [{"role": "system", "content": system_prompt}]
        for entry in history:
            messages_list.append({"role": entry["role"], "content": entry["content"]})

        # Prepare the user message, optionally enriched with search results
        if context_text:
            user_content = (
                f"Используй эти данные из интернета для ответа:\n{context_text}\n\n"
                f"Вопрос пользователя: {text}"
            )
        else:
            user_content = text
        messages_list.append({"role": "user", "content": user_content})

        # Generate a response using the Mistral chat API
        response = mistral_client.chat.complete(
            model="mistral-small-latest",
            messages=messages_list,
        )
        ai_content = response.choices[0].message.content

        # Persist both messages for future context
        db.save_message(user_id, "user", text)
        db.save_message(user_id, "assistant", ai_content)

        await send_long_message(update, ai_content)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка ИИ: {str(e)}")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle incoming documents (e.g. PDF resumes) sent to the bot.

    The file is downloaded to disk, its text extracted using PyMuPDF, and
    passed to Mistral for analysis. The result is sent back to the user. The
    temporary file is removed afterwards.
    """
    file = await update.message.document.get_file()
    file_path = f"temp_{update.message.document.file_name}"
    await file.download_to_drive(file_path)
    caption = update.message.caption if update.message.caption else ""

    if file_path.endswith('.pdf'):
        doc = fitz.open(file_path)
        pdf_text = "".join([page.get_text() for page in doc])
        system_prompt = (
            "Ты профессиональный HR-ассистент. НЕ используй Markdown разметку "
            "(звёздочки, жирный шрифт). Используй только обычный текст и эмодзи."
        )
        user_prompt = "Проанализируй это резюме. "
        if caption:
            user_prompt += f"Учти следующий комментарий/вопрос пользователя: {caption}\n\n"
        else:
            user_prompt += "Дай краткую оценку:\n\n"
        user_prompt += f"Текст резюме:\n{pdf_text}"
        response = mistral_client.chat.complete(
            model="mistral-small-latest",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        ai_content = response.choices[0].message.content
        await send_long_message(update, ai_content)

        # Record the interaction in the conversation history
        user_id = update.effective_user.id
        db.save_message(user_id, "user", f"[Загружен PDF: {update.message.document.file_name}] {caption}")
        db.save_message(user_id, "assistant", ai_content)

    # Remove the temporary file
    os.remove(file_path)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button presses from the inline keyboard on the /start menu."""
    query = update.callback_query
    await query.answer()
    if query.data == 'how_to_connect':
        await connect_command(query, context)
    elif query.data == 'my_events':
        await events_command(query, context)
    elif query.data == 'help':
        await help_command(query, context)


if __name__ == '__main__':
    # Ensure the database is initialized before starting the bot
    db.init_db()
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("connect", connect_command))
    app.add_handler(CommandHandler("events", events_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(CallbackQueryHandler(button_handler))
    print("Бот запущен...")
    app.run_polling()
