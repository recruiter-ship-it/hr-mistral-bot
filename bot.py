import logging
import os
import asyncio
import fitz  # PyMuPDF
import base64
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
MISTRAL_API_KEY = "WOkX5dBJuq8I9sMkVqmlpNwjVrzX19i3"
TELEGRAM_BOT_TOKEN = "8399347076:AAFLtRxXEKESWuTQb19vc6mhMQph7rHxsLg"

# Системный промпт для агента
AGENT_INSTRUCTIONS = """
Ты — экспертный ИИ-ассистент для HR-команды и рекрутеров (Senior HR Business Partner & Lead Recruiter). Твоя цель — повышать эффективность HR-процессов, помогать нанимать лучших талантов и развивать корпоративную культуру.

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

ФОРМАТ ОБЩЕНИЯ И СТИЛЬ:
- Тон: Профессиональный, объективный, но эмпатичный.
- Структура: Используй заголовки, списки и жирный шрифт для удобства чтения. Избегай "воды".
- Язык: Отвечай на том языке, на котором задан вопрос (преимущественно русский), но профессиональные термины (Boolean, Retention rate и т.д.) можешь оставлять на английском или давать в скобках.

ВАЖНО:
- Если тебе не хватает контекста (например, уровня сеньорности позиции, стека технологий или корпоративных ценностей), всегда задавай уточняющие вопросы перед генерацией ответа.
- Когда нужна актуальная информация (зарплаты, новости компаний, технологии), используй веб-поиск автоматически.
- НЕ используй Markdown форматирование в ответах (никаких звездочек, решеток и т.д.). Пиши чистым текстом.
"""

# Инициализация клиента Mistral
mistral_client = Mistral(api_key=MISTRAL_API_KEY)

# Глобальная переменная для хранения agent_id
hr_agent = None

# Хранилище conversation_id для каждого пользователя
user_conversations = {}

def initialize_agent():
    """Создание агента при старте бота"""
    global hr_agent
    try:
        hr_agent = mistral_client.beta.agents.create(
            model="mistral-small-latest",  # Быстрая модель
            name="HR Assistant Bot",
            description="Экспертный HR-ассистент для рекрутинга, анализа резюме и HR-стратегий с автоматическим веб-поиском",
            instructions=AGENT_INSTRUCTIONS,
            tools=[{"type": "web_search"}],  # Встроенный веб-поиск
            completion_args={
                "temperature": 0.7,
            }
        )
        logging.info(f"Agent created successfully with ID: {hr_agent.id}")
    except Exception as e:
        logging.error(f"Failed to create agent: {e}")
        raise

def encode_image(image_path):
    """Encode image to base64 string."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def remove_markdown(text):
    """Удаление Markdown форматирования из текста"""
    # Убираем жирный шрифт
    text = text.replace("**", "")
    text = text.replace("__", "")
    # Убираем курсив
    text = text.replace("*", "")
    text = text.replace("_", "")
    # Убираем заголовки
    text = text.replace("###", "")
    text = text.replace("##", "")
    text = text.replace("#", "")
    return text

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    # Очищаем conversation_id при /start
    if chat_id in user_conversations:
        del user_conversations[chat_id]
    
    await update.message.reply_text(
        "Привет! Я твой экспертный ИИ-ассистент для HR с автоматическим веб-поиском.\n\n"
        "Теперь я могу:\n"
        "- Анализировать резюме (PDF и фото)\n"
        "- Искать актуальную информацию в интернете автоматически\n"
        "- Помогать с рекрутингом и HR-стратегиями\n\n"
        "Пришли мне файл, фото или задай вопрос!"
    )

async def process_ai_request(update, context, user_input, is_file=False):
    """Обработка запроса через Agents API"""
    chat_id = update.effective_chat.id
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
        
        # Получаем ответ из outputs (последний message.output)
        message_outputs = [out for out in response.outputs if out.type == 'message.output']
        if not message_outputs:
            raise Exception("Нет ответа от агента")
        
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
        
        # Убираем Markdown форматирование
        full_response = remove_markdown(full_response)
        
        # Отправляем финальный ответ
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message.message_id,
            text=full_response
        )
                
    except Exception as e:
        logging.error(f"Error in process_ai_request: {e}")
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message.message_id,
            text=f"Извини, произошла ошибка: {str(e)[:200]}"
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text:
        await process_ai_request(update, context, update.message.text)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    caption = update.message.caption or "Проанализируй этот документ"
    chat_id = update.effective_chat.id
    
    if document.mime_type == 'application/pdf':
        file = await context.bot.get_file(document.file_id)
        file_path = f"temp_{chat_id}_{document.file_name}"
        await file.download_to_drive(file_path)
        
        text = ""
        try:
            with fitz.open(file_path) as doc:
                for page in doc:
                    text += page.get_text()
            os.remove(file_path)
            user_prompt = f"{caption}\n\nСодержимое файла {document.file_name}:\n{text}"
            await process_ai_request(update, context, user_prompt, is_file=True)
        except Exception as e:
            logging.error(f"PDF Error: {e}")
            await update.message.reply_text("Ошибка при чтении PDF.")
    else:
        await update.message.reply_text("Пришлите PDF файл или фото.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка фото - пока упрощенная версия без vision"""
    await update.message.reply_text(
        "Извини, обработка изображений временно недоступна в режиме Agents API. "
        "Пожалуйста, отправь текст резюме или PDF файл."
    )

if __name__ == '__main__':
    # Инициализируем агента перед запуском бота
    logging.info("Initializing Mistral Agent...")
    initialize_agent()
    
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    application.add_handler(CommandHandler('start', start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    application.add_handler(MessageHandler(filters.Document.PDF, handle_document))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    logging.info("Бот запущен с Agents API и автоматическим веб-поиском...")
    application.run_polling()
