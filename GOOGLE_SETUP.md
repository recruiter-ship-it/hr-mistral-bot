# Настройка Google OAuth для бота

## Шаг 1: Создание проекта в Google Cloud Console

1. Перейдите на https://console.cloud.google.com/
2. Создайте новый проект или выберите существующий
3. Название проекта: `HR Mistral Bot`

## Шаг 2: Включение API

1. В меню слева выберите **APIs & Services** → **Library**
2. Найдите и включите следующие API:
   - **Google Calendar API**
   - **Gmail API**

## Шаг 3: Настройка OAuth Consent Screen

1. Перейдите в **APIs & Services** → **OAuth consent screen**
2. Выберите **External** (если бот для личного использования)
3. Заполните обязательные поля:
   - **App name**: HR Mistral Bot
   - **User support email**: ваш email
   - **Developer contact information**: ваш email
4. Нажмите **Save and Continue**
5. На странице **Scopes** нажмите **Add or Remove Scopes**
6. Добавьте следующие scopes:
   - `https://www.googleapis.com/auth/calendar.readonly`
   - `https://www.googleapis.com/auth/calendar.events`
   - `https://www.googleapis.com/auth/gmail.readonly`
7. Нажмите **Save and Continue**
8. На странице **Test users** добавьте свой Gmail адрес
9. Нажмите **Save and Continue**

## Шаг 4: Создание OAuth Client ID

1. Перейдите в **APIs & Services** → **Credentials**
2. Нажмите **Create Credentials** → **OAuth client ID**
3. Выберите **Application type**: **Desktop app**
4. **Name**: HR Bot Desktop Client
5. Нажмите **Create**
6. Скопируйте **Client ID** и **Client Secret**

## Шаг 5: Настройка переменных окружения

В GitHub Actions добавьте секреты:

1. Перейдите в Settings → Secrets and variables → Actions
2. Добавьте два новых секрета:
   - `GOOGLE_CLIENT_ID`: ваш Client ID
   - `GOOGLE_CLIENT_SECRET`: ваш Client Secret

## Шаг 6: Обновление кода (если нужно)

Если вы используете другой redirect URI (не localhost), обновите в `google_auth.py`:

```python
REDIRECT_URI = "urn:ietf:wg:oauth:2.0:oob"  # Для desktop приложений
```

## Шаг 7: Тестирование

1. Запустите бота
2. Отправьте команду `/connect`
3. Перейдите по ссылке и авторизуйтесь
4. Скопируйте код авторизации
5. Отправьте боту: `/auth <код>`
6. Проверьте команды:
   - `/calendar` - должен показать ваши события
   - `/emails` - должен показать ваши письма

## Важные замечания

### Redirect URI для production

Для production использования рекомендуется:

1. Создать простой веб-сервер для обработки OAuth callback
2. Использовать ngrok или подобный сервис для туннелирования
3. Или использовать `urn:ietf:wg:oauth:2.0:oob` для desktop приложений

### Безопасность

- **НЕ** коммитьте Client ID и Client Secret в Git
- Используйте переменные окружения
- Токены пользователей хранятся в БД в base64 (рекомендуется добавить шифрование)

### Ограничения

- Приложение в режиме "Testing" имеет лимит 100 пользователей
- Для публичного использования нужно пройти верификацию Google
- Refresh token действителен до тех пор, пока пользователь не отзовет доступ

## Альтернативный вариант: Service Account

Если вы хотите дать боту доступ к **своему** календарю и почте (не пользователей):

1. Создайте Service Account в Google Cloud Console
2. Скачайте JSON ключ
3. Дайте Service Account доступ к вашему календарю (Share calendar)
4. Используйте `google_calendar.py` (старая версия) вместо OAuth

**Внимание**: Service Account НЕ может получить доступ к Gmail без Google Workspace и domain-wide delegation.

## Troubleshooting

### Ошибка: redirect_uri_mismatch

- Убедитесь, что redirect URI в коде совпадает с настройками в Google Cloud Console
- Для desktop приложений используйте `http://localhost:8080` или `urn:ietf:wg:oauth:2.0:oob`

### Ошибка: invalid_grant

- Токен истек или был отозван
- Попросите пользователя переподключиться через `/connect`

### Ошибка: insufficient permissions

- Проверьте, что все необходимые scopes добавлены в OAuth consent screen
- Попросите пользователя переподключиться (при изменении scopes)
