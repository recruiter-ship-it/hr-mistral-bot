#!/usr/bin/env python3
"""
Скрипт для настройки Google API credentials
Заполняет .env файл необходимыми переменными для MCP серверов
"""

import os
import sys
import json
import base64
from pathlib import Path
from getpass import getpass

def print_header(text: str):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}\n")

def print_section(text: str):
    print(f"\n--- {text} ---\n")

def load_env_file(env_path: Path) -> dict:
    """Загружает существующий .env файл"""
    env_vars = {}
    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip().strip('"').strip("'")
    return env_vars

def save_env_file(env_path: Path, env_vars: dict):
    """Сохраняет .env файл"""
    with open(env_path, 'w') as f:
        f.write("# Google API Credentials для HR Bot MCP Servers\n")
        f.write("# Сгенерировано setup_google_env.py\n\n")
        
        # Группируем переменные
        f.write("# === OAuth Credentials ===\n")
        for key in ['GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'GOOGLE_REFRESH_TOKEN', 'GOOGLE_ACCESS_TOKEN']:
            if key in env_vars:
                f.write(f"{key}={env_vars[key]}\n")
        
        f.write("\n# === Service Account ===\n")
        for key in ['GOOGLE_SERVICE_ACCOUNT_B64', 'GOOGLE_APPLICATION_CREDENTIALS_PATH']:
            if key in env_vars:
                f.write(f"{key}={env_vars[key]}\n")
        
        f.write("\n# === Google Cloud Project ===\n")
        for key in ['GOOGLE_CLOUD_PROJECT', 'GOOGLE_API_KEY']:
            if key in env_vars:
                f.write(f"{key}={env_vars[key]}\n")
        
        f.write("\n# === Specific APIs ===\n")
        for key in ['GOOGLE_MAPS_API_KEY', 'YOUTUBE_API_KEY', 'GOOGLE_DEVELOPER_TOKEN']:
            if key in env_vars:
                f.write(f"{key}={env_vars[key]}\n")
        
        f.write("\n# === Other Services ===\n")
        for key in ['LOOKER_API_URL', 'LOOKER_CLIENT_ID', 'LOOKER_CLIENT_SECRET', 'FIREBASE_PROJECT_ID']:
            if key in env_vars:
                f.write(f"{key}={env_vars[key]}\n")
        
        # Остальные переменные
        f.write("\n# === Other ===\n")
        written_keys = {
            'GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'GOOGLE_REFRESH_TOKEN', 
            'GOOGLE_ACCESS_TOKEN', 'GOOGLE_SERVICE_ACCOUNT_B64', 
            'GOOGLE_APPLICATION_CREDENTIALS_PATH', 'GOOGLE_CLOUD_PROJECT',
            'GOOGLE_API_KEY', 'GOOGLE_MAPS_API_KEY', 'YOUTUBE_API_KEY',
            'GOOGLE_DEVELOPER_TOKEN', 'LOOKER_API_URL', 'LOOKER_CLIENT_ID',
            'LOOKER_CLIENT_SECRET', 'FIREBASE_PROJECT_ID'
        }
        for key, value in env_vars.items():
            if key not in written_keys:
                f.write(f"{key}={value}\n")

def encode_service_account(json_path: str) -> str:
    """Кодирует Service Account JSON в base64"""
    with open(json_path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')

def get_oauth_token(client_id: str, client_secret: str) -> tuple:
    """
    Помогает получить OAuth refresh token через OAuth Playground
    """
    print("""
Для получения refresh token:

1. Откройте Google OAuth 2.0 Playground: https://developers.google.com/oauthplayground

2. Настройте OAuth Playground:
   - Нажмите на шестерёнку (Settings) в правом верхнем углу
   - В поле "Your Client ID" вставьте ваш Client ID
   - В поле "Your Client Secret" вставьте ваш Client Secret
   
3. Выберите нужные scopes (Step 1):
   Для HR бота рекомендуются следующие scopes:
   
   https://www.googleapis.com/auth/gmail.modify
   https://www.googleapis.com/auth/calendar
   https://www.googleapis.com/auth/drive
   https://www.googleapis.com/auth/spreadsheets
   https://www.googleapis.com/auth/documents
   https://www.googleapis.com/auth/contacts
   https://www.googleapis.com/auth/tasks
   https://www.googleapis.com/auth/cloud-translation
   
4. Нажмите "Authorize APIs" и авторизуйтесь

5. В Step 2 нажмите "Exchange authorization code for tokens"

6. Скопируйте "Refresh token" из ответа
""")
    
    refresh_token = input("Введите полученный refresh token: ").strip()
    return refresh_token

def setup_oauth(env_vars: dict):
    """Настройка OAuth credentials"""
    print_section("Настройка OAuth 2.0")
    
    print("OAuth 2.0 используется для: Gmail, Calendar, Tasks, Contacts, Meet, Chat")
    print("Требуется создать OAuth Client в Google Cloud Console")
    print("https://console.cloud.google.com/apis/credentials\n")
    
    env_vars['GOOGLE_CLIENT_ID'] = input("Google Client ID: ").strip() or env_vars.get('GOOGLE_CLIENT_ID', '')
    env_vars['GOOGLE_CLIENT_SECRET'] = getpass("Google Client Secret (hidden): ").strip() or env_vars.get('GOOGLE_CLIENT_SECRET', '')
    
    # Спрашиваем про refresh token
    if not env_vars.get('GOOGLE_REFRESH_TOKEN'):
        get_token = input("\nПолучить refresh token? (y/n): ").strip().lower()
        if get_token == 'y':
            env_vars['GOOGLE_REFRESH_TOKEN'] = get_oauth_token(
                env_vars['GOOGLE_CLIENT_ID'],
                env_vars['GOOGLE_CLIENT_SECRET']
            )
        else:
            env_vars['GOOGLE_REFRESH_TOKEN'] = input("Refresh token (или Enter чтобы пропустить): ").strip()

def setup_service_account(env_vars: dict):
    """Настройка Service Account"""
    print_section("Настройка Service Account")
    
    print("Service Account используется для: Sheets, Drive, Docs, BigQuery, Cloud Storage")
    print("Требуется создать Service Account в Google Cloud Console")
    print("https://console.cloud.google.com/iam-admin/serviceaccounts\n")
    
    print("Выберите способ:")
    print("1. Указать путь к JSON файлу Service Account")
    print("2. Закодировать JSON в base64 (рекомендуется для деплоя)")
    
    choice = input("Ваш выбор (1/2): ").strip()
    
    if choice == '1':
        json_path = input("Путь к JSON файлу: ").strip()
        if os.path.exists(json_path):
            env_vars['GOOGLE_APPLICATION_CREDENTIALS_PATH'] = json_path
            # Также кодируем в base64 для совместимости
            env_vars['GOOGLE_SERVICE_ACCOUNT_B64'] = encode_service_account(json_path)
            print("✅ Service Account настроен")
        else:
            print("❌ Файл не найден")
    elif choice == '2':
        json_path = input("Путь к JSON файлу: ").strip()
        if os.path.exists(json_path):
            env_vars['GOOGLE_SERVICE_ACCOUNT_B64'] = encode_service_account(json_path)
            print("✅ Service Account закодирован в base64")
        else:
            print("❌ Файл не найден")
    else:
        b64_value = input("Base64 encoded JSON (или Enter чтобы пропустить): ").strip()
        if b64_value:
            env_vars['GOOGLE_SERVICE_ACCOUNT_B64'] = b64_value

def setup_api_keys(env_vars: dict):
    """Настройка API ключей"""
    print_section("Настройка API Keys")
    
    print("API Keys используются для: Maps, Translate, Vision, YouTube")
    print("Создайте API key: https://console.cloud.google.com/apis/credentials\n")
    
    env_vars['GOOGLE_API_KEY'] = input(f"Google API Key [{env_vars.get('GOOGLE_API_KEY', '')}]: ").strip() or env_vars.get('GOOGLE_API_KEY', '')
    env_vars['GOOGLE_MAPS_API_KEY'] = input(f"Google Maps API Key [{env_vars.get('GOOGLE_MAPS_API_KEY', '')}]: ").strip() or env_vars.get('GOOGLE_MAPS_API_KEY', '')
    env_vars['YOUTUBE_API_KEY'] = input(f"YouTube API Key [{env_vars.get('YOUTUBE_API_KEY', '')}]: ").strip() or env_vars.get('YOUTUBE_API_KEY', '')

def setup_cloud_project(env_vars: dict):
    """Настройка Google Cloud Project"""
    print_section("Google Cloud Project")
    
    print("Project ID требуется для: BigQuery, Cloud Storage, Pub/Sub, Firebase")
    
    env_vars['GOOGLE_CLOUD_PROJECT'] = input(f"Google Cloud Project ID [{env_vars.get('GOOGLE_CLOUD_PROJECT', '')}]: ").strip() or env_vars.get('GOOGLE_CLOUD_PROJECT', '')

def list_available_apis():
    """Выводит список доступных API для включения"""
    print_section("API которые нужно включить в Google Cloud Console")
    
    apis = [
        ("Gmail API", "gmail.googleapis.com", "Для Gmail MCP"),
        ("Google Calendar API", "calendar.googleapis.com", "Для Calendar MCP"),
        ("Google Drive API", "drive.googleapis.com", "Для Drive MCP"),
        ("Google Sheets API", "sheets.googleapis.com", "Для Sheets MCP"),
        ("Google Docs API", "docs.googleapis.com", "Для Docs MCP"),
        ("Google Tasks API", "tasks.googleapis.com", "Для Tasks MCP"),
        ("People API", "people.googleapis.com", "Для Contacts MCP"),
        ("YouTube Data API v3", "youtube.googleapis.com", "Для YouTube MCP"),
        ("Cloud Translation API", "translate.googleapis.com", "Для Translate MCP"),
        ("Maps JavaScript API", "maps-backend.googleapis.com", "Для Maps MCP"),
        ("BigQuery API", "bigquery.googleapis.com", "Для BigQuery MCP"),
        ("Cloud Vision API", "vision.googleapis.com", "Для Vision MCP"),
        ("Google Ads API", "googleads.googleapis.com", "Для Ads MCP"),
    ]
    
    print(f"{'API':<30} {'ID':<35} {'Использование'}")
    print("-" * 80)
    for name, api_id, usage in apis:
        print(f"{name:<30} {api_id:<35} {usage}")
    
    print("\nВключить API: https://console.cloud.google.com/apis/library")

def show_current_config(env_vars: dict):
    """Показывает текущую конфигурацию"""
    print_section("Текущая конфигурация")
    
    if not env_vars:
        print("(.env файл пуст или не существует)")
        return
    
    # Скрываем секретные значения
    for key, value in env_vars.items():
        if 'SECRET' in key.upper() or 'TOKEN' in key.upper() or 'KEY' in key.upper():
            display_value = value[:10] + '...' if len(value) > 10 else '***'
        else:
            display_value = value[:50] + '...' if len(value) > 50 else value
        print(f"  {key}: {display_value}")

def show_mcp_servers_status():
    """Показывает статус MCP серверов"""
    print_section("MCP Servers Status")
    
    config_path = Path(__file__).parent / "mcp_config.json"
    if config_path.exists():
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        enabled = []
        disabled = []
        
        for server in config.get('mcpServers', []):
            name = server.get('name', '')
            desc = server.get('description', '')
            if server.get('enabled', False):
                enabled.append((name, desc))
            else:
                disabled.append((name, desc))
        
        print("✅ Включённые серверы:")
        for name, desc in enabled:
            print(f"   • {name}: {desc}")
        
        print(f"\n⚪ Отключённые серверы ({len(disabled)} шт.):")
        for name, desc in disabled[:5]:  # Показываем первые 5
            print(f"   • {name}: {desc}")
        if len(disabled) > 5:
            print(f"   ... и ещё {len(disabled) - 5}")
    else:
        print("mcp_config.json не найден")

def main():
    print_header("Google API Credentials Setup для HR Bot MCP")
    
    env_path = Path(__file__).parent / ".env"
    env_vars = load_env_file(env_path)
    
    while True:
        print("""
Меню:
  1. Настроить OAuth 2.0 (Gmail, Calendar, Tasks, Contacts)
  2. Настроить Service Account (Sheets, Drive, Docs)
  3. Настроить API Keys (Maps, Translate, YouTube)
  4. Настроить Google Cloud Project
  5. Показать текущую конфигурацию
  6. Показать статус MCP серверов
  7. Показать список API для включения
  8. Сохранить и выйти
  0. Выйти без сохранения
""")
        
        choice = input("Выберите действие: ").strip()
        
        if choice == '1':
            setup_oauth(env_vars)
        elif choice == '2':
            setup_service_account(env_vars)
        elif choice == '3':
            setup_api_keys(env_vars)
        elif choice == '4':
            setup_cloud_project(env_vars)
        elif choice == '5':
            show_current_config(env_vars)
        elif choice == '6':
            show_mcp_servers_status()
        elif choice == '7':
            list_available_apis()
        elif choice == '8':
            save_env_file(env_path, env_vars)
            print(f"\n✅ Конфигурация сохранена в {env_path}")
            print("\nТеперь вы можете запустить бота:")
            print("  python bot.py")
            break
        elif choice == '0':
            print("Выход без сохранения")
            break
        else:
            print("Неверный выбор")

if __name__ == "__main__":
    main()
