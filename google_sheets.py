"""
Google Sheets integration for HR Bot.
Manages employee onboarding tracking spreadsheet.
"""

import os
import json
import base64
import logging
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ID таблицы новых сотрудников
SPREADSHEET_ID = "1gBqrvhHjbPJKUmVLPj_9P2IkqngwYOqMC84jzilCU7I"
SHEET_NAME = "Лист1"  # Можно изменить на реальное имя листа

# Скоупы для Google Sheets
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

logger = logging.getLogger(__name__)


def get_sheets_service():
    """
    Создаёт сервис Google Sheets используя Service Account.
    
    Требуется переменная окружения GOOGLE_SERVICE_ACCOUNT с JSON credentials,
    либо GOOGLE_SERVICE_ACCOUNT_B64 с base64-encoded JSON.
    """
    try:
        # Пробуем получить credentials из переменной окружения
        creds_json = os.getenv("GOOGLE_SERVICE_ACCOUNT")
        creds_b64 = os.getenv("GOOGLE_SERVICE_ACCOUNT_B64")
        
        if creds_b64:
            # Декодируем из base64
            creds_json = base64.b64decode(creds_b64).decode('utf-8')
        
        if not creds_json:
            logger.warning("Google Service Account credentials not found")
            return None
        
        # Парсим JSON
        if isinstance(creds_json, str):
            creds_dict = json.loads(creds_json)
        else:
            creds_dict = creds_json
        
        # Убеждаемся, что private_key правильно отформатирован
        # Google отправляет \n как escape-последовательность в JSON
        if 'private_key' in creds_dict and isinstance(creds_dict['private_key'], str):
            # Заменяем экранированные \n на реальные переносы строк
            creds_dict['private_key'] = creds_dict['private_key'].replace('\\n', '\n')
        
        credentials = service_account.Credentials.from_service_account_info(
            creds_dict, 
            scopes=SCOPES
        )
        
        service = build('sheets', 'v4', credentials=credentials)
        logger.info("Google Sheets service created successfully")
        return service
        
    except Exception as e:
        logger.error(f"Failed to create Sheets service: {e}")
        return None


def get_sheet_data(range_name: str = "A:K") -> tuple:
    """
    Получает данные из таблицы.
    
    Args:
        range_name: Диапазон ячеек для чтения
        
    Returns:
        Tuple (success, data/error_message)
    """
    service = get_sheets_service()
    if not service:
        return False, "❌ Google Sheets не настроен. Обратитесь к администратору."
    
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{SHEET_NAME}!{range_name}"
        ).execute()
        
        values = result.get('values', [])
        return True, values
        
    except HttpError as e:
        logger.error(f"Sheets API error: {e}")
        return False, f"❌ Ошибка доступа к таблице: {e.reason}"
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return False, f"❌ Ошибка: {str(e)}"


def add_employee(
    employee_name: str,
    role: str,
    recruiter: str = "-//-",
    start_date: str = None,
    salary: str = "",
    card_link: str = ""
) -> tuple:
    """
    Добавляет нового сотрудника в таблицу.
    
    Args:
        employee_name: Имя сотрудника
        role: Должность
        recruiter: Имя рекрутера
        start_date: Дата выхода (формат DD/MM/YYYY или "завтра", "следующий понедельник")
        salary: Сумма в оффере
        card_link: Ссылка на карточку сотрудника
        
    Returns:
        Tuple (success, message)
    """
    service = get_sheets_service()
    if not service:
        return False, "❌ Google Sheets не настроен. Обратитесь к администратору."
    
    try:
        # Получаем текущие данные для определения следующего номера
        success, data = get_sheet_data("A:A")
        if not success:
            return False, data
        
        # Находим последний заполненный номер
        last_number = 0
        for row in data[1:]:  # Пропускаем заголовок
            if row and row[0].isdigit():
                last_number = max(last_number, int(row[0]))
        
        next_number = last_number + 1
        
        # Определяем месяц
        month_names = [
            "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
            "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
        ]
        
        # Парсим дату выхода
        if start_date:
            try:
                # Пробуем разные форматы
                for fmt in ["%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d"]:
                    try:
                        parsed_date = datetime.strptime(start_date, fmt)
                        break
                    except ValueError:
                        continue
                else:
                    # Если не распарсилось, используем сегодня
                    parsed_date = datetime.now()
                
                month = month_names[parsed_date.month - 1]
                start_date_formatted = parsed_date.strftime("%d/%m/%Y")
                
                # Вычисляем даты испытательного срока
                equator_date = parsed_date + timedelta(days=45)  # Экватор = 1.5 месяца
                end_probation_date = parsed_date + timedelta(days=90)  # 3 месяца
                
                equator_formatted = equator_date.strftime("%d/%m/%Y")
                end_probation_formatted = end_probation_date.strftime("%d/%m/%Y")
                
            except Exception as e:
                logger.error(f"Date parsing error: {e}")
                month = month_names[datetime.now().month - 1]
                start_date_formatted = start_date
                equator_formatted = "-//-"
                end_probation_formatted = "-//-"
        else:
            month = month_names[datetime.now().month - 1]
            start_date_formatted = ""
            equator_formatted = ""
            end_probation_formatted = ""
        
        # Формируем строку для добавления
        new_row = [
            next_number,           # A - №
            month,                 # B - Месяц
            employee_name,         # C - Сотрудник
            role,                  # D - Роль
            recruiter,             # E - Рекрутер
            start_date_formatted,  # F - День выхода
            equator_formatted,     # G - Экватор ИС
            end_probation_formatted,  # H - День окончания ИС
            salary,                # I - Сумма в оффере
            "",                    # J - Рекомендация
            card_link              # K - Карточка
        ]
        
        # Находим первую пустую строку
        success, existing_data = get_sheet_data("A:K")
        if not success:
            return False, existing_data
        
        # Ищем последнюю строку с данными
        last_row = len(existing_data) if existing_data else 0
        
        # Добавляем новую строку
        range_name = f"{SHEET_NAME}!A{last_row + 1}:K{last_row + 1}"
        
        body = {
            'values': [new_row]
        }
        
        result = service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=range_name,
            valueInputOption='USER_ENTERED',
            body=body
        ).execute()
        
        logger.info(f"Added employee: {employee_name}, rows updated: {result.get('updatedRows')}")
        
        message = f"✅ Сотрудник добавлен в таблицу!\n\n"
        message += f"📋 **{employee_name}**\n"
        message += f"📁 Роль: {role}\n"
        message += f"👤 Рекрутер: {recruiter}\n"
        if start_date_formatted:
            message += f"📅 Дата выхода: {start_date_formatted}\n"
        if salary:
            message += f"💰 Сумма: {salary}\n"
        message += f"\n📊 [Открыть таблицу](https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID})"
        
        return True, message
        
    except HttpError as e:
        logger.error(f"Sheets API error: {e}")
        return False, f"❌ Ошибка при добавлении: {e.reason}"
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return False, f"❌ Ошибка: {str(e)}"


def list_employees(month: str = None, limit: int = 10) -> tuple:
    """
    Показывает список сотрудников.
    
    Args:
        month: Фильтр по месяцу (опционально)
        limit: Максимальное количество записей
        
    Returns:
        Tuple (success, message/data)
    """
    service = get_sheets_service()
    if not service:
        # Если нет сервисного аккаунта, пробуем публичное чтение
        return list_employees_public(month, limit)
    
    try:
        success, data = get_sheet_data("A:K")
        if not success:
            return False, data
        
        if len(data) <= 1:
            return True, "📋 Таблица пуста."
        
        # Фильтруем данные
        employees = []
        headers = data[0] if data else []
        
        for row in data[1:]:
            if not row or not any(row):
                continue
            
            # row[0] = номер, row[1] = месяц, row[2] = сотрудник
            if month and len(row) > 1:
                if month.lower() not in row[1].lower():
                    continue
            
            employee = {
                "number": row[0] if len(row) > 0 else "",
                "month": row[1] if len(row) > 1 else "",
                "name": row[2] if len(row) > 2 else "",
                "role": row[3] if len(row) > 3 else "",
                "recruiter": row[4] if len(row) > 4 else "",
                "start_date": row[5] if len(row) > 5 else "",
                "equator": row[6] if len(row) > 6 else "",
                "end_probation": row[7] if len(row) > 7 else "",
                "salary": row[8] if len(row) > 8 else "",
                "recommendation": row[9] if len(row) > 9 else "",
                "card": row[10] if len(row) > 10 else ""
            }
            employees.append(employee)
        
        if not employees:
            return True, f"📋 Сотрудники за {month} не найдены." if month else "📋 Сотрудники не найдены."
        
        # Формируем сообщение
        message = f"📋 **Список сотрудников"
        if month:
            message += f" за {month}"
        message += f"** (последние {min(limit, len(employees))})\n\n"
        
        for emp in employees[-limit:]:
            message += f"**{emp['number']}. {emp['name']}**\n"
            message += f"📁 {emp['role']}\n"
            if emp['start_date']:
                message += f"📅 Выход: {emp['start_date']}"
                if emp['end_probation']:
                    message += f" | ИС до {emp['end_probation']}"
                message += "\n"
            message += "\n"
        
        message += f"\n📊 [Открыть таблицу](https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID})"
        
        return True, message
        
    except Exception as e:
        logger.error(f"Error listing employees: {e}")
        return False, f"❌ Ошибка: {str(e)}"


def list_employees_public(month: str = None, limit: int = 10) -> tuple:
    """
    Публичное чтение таблицы без авторизации.
    Работает только если таблица открыта для публичного доступа.
    """
    import requests
    
    try:
        url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv"
        response = requests.get(url)
        
        if response.status_code != 200:
            return False, "❌ Не удалось получить доступ к таблице"
        
        lines = response.text.split('\n')
        
        employees = []
        for i, line in enumerate(lines[1:], 1):  # Пропускаем заголовок
            if not line.strip():
                continue
            
            # Простое разделение по запятым (не идеально для CSV с кавычками)
            parts = line.split(',')
            
            if len(parts) >= 3:
                employee = {
                    "number": parts[0].strip(),
                    "month": parts[1].strip(),
                    "name": parts[2].strip(),
                    "role": parts[3].strip() if len(parts) > 3 else "",
                    "start_date": parts[5].strip() if len(parts) > 5 else ""
                }
                
                if month and month.lower() not in employee['month'].lower():
                    continue
                
                employees.append(employee)
        
        if not employees:
            return True, f"📋 Сотрудники не найдены."
        
        message = f"📋 **Список сотрудников** (последние {min(limit, len(employees))})\n\n"
        
        for emp in employees[-limit:]:
            if emp['name']:
                message += f"**{emp['number']}. {emp['name']}**\n"
                message += f"📁 {emp['role']}\n"
                if emp['start_date']:
                    message += f"📅 Выход: {emp['start_date']}\n"
                message += "\n"
        
        message += f"\n📊 [Открыть таблицу](https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID})"
        
        return True, message
        
    except Exception as e:
        logger.error(f"Error in public read: {e}")
        return False, f"❌ Ошибка: {str(e)}"


def search_employee(name: str) -> tuple:
    """
    Ищет сотрудника по имени.
    
    Args:
        name: Имя или часть имени сотрудника
        
    Returns:
        Tuple (success, message)
    """
    service = get_sheets_service()
    if not service:
        return False, "❌ Google Sheets не настроен."
    
    try:
        success, data = get_sheet_data("A:K")
        if not success:
            return False, data
        
        # Ищем сотрудника
        for row in data[1:]:
            if not row or len(row) < 3:
                continue
            
            if name.lower() in row[2].lower():
                employee = {
                    "number": row[0],
                    "month": row[1],
                    "name": row[2],
                    "role": row[3] if len(row) > 3 else "",
                    "recruiter": row[4] if len(row) > 4 else "",
                    "start_date": row[5] if len(row) > 5 else "",
                    "equator": row[6] if len(row) > 6 else "",
                    "end_probation": row[7] if len(row) > 7 else "",
                    "salary": row[8] if len(row) > 8 else "",
                    "recommendation": row[9] if len(row) > 9 else "",
                    "card": row[10] if len(row) > 10 else ""
                }
                
                message = f"🔍 **Найден сотрудник:**\n\n"
                message += f"**{employee['name']}**\n"
                message += f"📁 Роль: {employee['role']}\n"
                message += f"👤 Рекрутер: {employee['recruiter']}\n"
                message += f"📅 Выход: {employee['start_date']}\n"
                message += f"📅 Экватор ИС: {employee['equator']}\n"
                message += f"📅 Конец ИС: {employee['end_probation']}\n"
                if employee['salary']:
                    message += f"💰 Сумма: {employee['salary']}\n"
                if employee['recommendation']:
                    message += f"📝 Рекомендация: {employee['recommendation']}\n"
                
                return True, message
        
        return True, f"🔍 Сотрудник '{name}' не найден."
        
    except Exception as e:
        logger.error(f"Error searching employee: {e}")
        return False, f"❌ Ошибка: {str(e)}"


def update_employee(name: str, field: str, value: str) -> tuple:
    """
    Обновляет данные сотрудника.
    
    Args:
        name: Имя сотрудника
        field: Поле для обновления (рекрутер, дата, сумма, рекомендация)
        value: Новое значение
        
    Returns:
        Tuple (success, message)
    """
    service = get_sheets_service()
    if not service:
        return False, "❌ Google Sheets не настроен."
    
    # Маппинг полей на колонки
    field_mapping = {
        "рекрутер": "E",
        "recruiter": "E",
        "дата выхода": "F",
        "start_date": "F",
        "экватор": "G",
        "equator": "G",
        "конец ис": "H",
        "конец испытательного": "H",
        "сумма": "I",
        "salary": "I",
        "зарплата": "I",
        "рекомендация": "J",
        "recommendation": "J",
        "карточка": "K",
        "card": "K"
    }
    
    column = field_mapping.get(field.lower())
    if not column:
        return False, f"❌ Неизвестное поле '{field}'. Доступные: рекрутер, дата выхода, экватор, конец ИС, сумма, рекомендация, карточка"
    
    try:
        # Находим строку с сотрудником
        success, data = get_sheet_data("A:K")
        if not success:
            return False, data
        
        row_number = None
        for i, row in enumerate(data[1:], start=2):  # Начинаем с 2 (пропускаем заголовок)
            if row and len(row) >= 3 and name.lower() in row[2].lower():
                row_number = i
                break
        
        if not row_number:
            return False, f"❌ Сотрудник '{name}' не найден."
        
        # Обновляем ячейку
        range_name = f"{SHEET_NAME}!{column}{row_number}"
        
        body = {
            'values': [[value]]
        }
        
        service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=range_name,
            valueInputOption='USER_ENTERED',
            body=body
        ).execute()
        
        return True, f"✅ Обновлено: {field} = {value} для {name}"
        
    except Exception as e:
        logger.error(f"Error updating employee: {e}")
        return False, f"❌ Ошибка: {str(e)}"
