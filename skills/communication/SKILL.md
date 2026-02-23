---
name: communication
description: Коммуникация - отправка сообщений в Slack, Discord, Email, Telegram
version: 1.0.0
author: HR Bot Team
tools:
  - name: comm_send_email
    description: Отправить email письмо
  - name: comm_slack_message
    description: Отправить сообщение в Slack
  - name: comm_discord_message
    description: Отправить сообщение в Discord
  - name: comm_telegram_message
    description: Отправить сообщение в Telegram
gating:
  - trigger: "отправь email|письмо|почта"
  - trigger: "напиши в slack|отправь в slack"
  - trigger: "отправь в discord|напиши в discord"
  - trigger: "отправь сообщение|уведомление"
---

# Communication Skill

Ты - эксперт по коммуникациям. Ты отправляешь сообщения через различные каналы.

## Когда использовать этот навык

Используй этот навык когда пользователь просит:
- Отправить email
- Написать в Slack или Discord
- Отправить уведомление

## Инструменты

### comm_send_email

Отправляет email письмо.

**Параметры:**
- `to` (обязательно): Email получателя
- `subject` (обязательно): Тема письма
- `body` (обязательно): Тело письма
- `html`: HTML формат (true/false)

**Пример:**
```
comm_send_email(
  to="candidate@example.com",
  subject="Приглашение на интервью",
  body="Уважаемый Иван, приглашаем вас на интервью..."
)
```

### comm_slack_message

Отправляет сообщение в Slack.

**Параметры:**
- `channel` (обязательно): Канал или ID пользователя
- `message` (обязательно): Текст сообщения

**Пример:**
```
comm_slack_message(
  channel="#hr-team",
  message="Новый кандидат: Иван Петров, позиция Developer"
)
```

### comm_discord_message

Отправляет сообщение в Discord через webhook.

**Параметры:**
- `webhook_url` (обязательно): Discord webhook URL
- `message` (обязательно): Текст сообщения
- `username`: Имя бота (опционально)

### comm_telegram_message

Отправляет сообщение в Telegram.

**Параметры:**
- `chat_id` (обязательно): Chat ID получателя
- `message` (обязательно): Текст сообщения

## Настройка

Для работы требуются переменные окружения:
- `SMTP_HOST`, `SMTP_USER`, `SMTP_PASS` - для email
- `SLACK_BOT_TOKEN` - для Slack
- `TELEGRAM_BOT_TOKEN` - для Telegram

## Примеры

**Пользователь:** "Отправь email кандидату Ивану на ivan@mail.ru с приглашением"
**Действие:** comm_send_email(to="ivan@mail.ru", subject="Приглашение на интервью", body="...")

**Пользователь:** "Напиши в #hr-team что новый сотрудник выходит завтра"
**Действие:** comm_slack_message(channel="#hr-team", message="...")
