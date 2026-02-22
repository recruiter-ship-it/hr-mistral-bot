"""
HR Workflow Executor - Исполнитель автономных воркфлоу
Интегрирует агента, память, документы и инструменты
"""

import os
import json
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

import database as db
import google_sheets
from google_calendar_manager import GoogleCalendarManager
from agent_core import hr_agent, TaskStatus
from document_generator import (
    create_offer_document, create_welcome_document,
    create_scorecard_document, create_rejection_letter,
    create_interview_invite
)

logger = logging.getLogger(__name__)

# Инициализация
calendar_manager = GoogleCalendarManager()


def register_all_tools():
    """Регистрация всех инструментов в агенте"""
    
    # === Google Sheets ===
    
    def add_employee_tool(employee_name: str, role: str, recruiter: str = "-//-",
                         start_date: str = None, salary: str = "", card_link: str = ""):
        success, message = google_sheets.add_employee(
            employee_name, role, recruiter, start_date, salary, card_link
        )
        return {"success": success, "message": message}
    
    hr_agent.register_tool("add_employee", add_employee_tool, {
        "description": "Добавить сотрудника в таблицу учёта",
        "parameters": {
            "type": "object",
            "properties": {
                "employee_name": {"type": "string", "description": "Имя сотрудника"},
                "role": {"type": "string", "description": "Должность"},
                "recruiter": {"type": "string", "description": "Рекрутер"},
                "start_date": {"type": "string", "description": "Дата выхода (DD/MM/YYYY)"},
                "salary": {"type": "string", "description": "Зарплата"}
            },
            "required": ["employee_name", "role"]
        }
    })
    
    def list_employees_tool(month: str = None, limit: int = 10):
        success, message = google_sheets.list_employees(month=month, limit=limit)
        return {"success": success, "employees": message}
    
    hr_agent.register_tool("list_employees", list_employees_tool, {
        "description": "Показать список сотрудников из таблицы",
        "parameters": {
            "type": "object",
            "properties": {
                "month": {"type": "string", "description": "Фильтр по месяцу"},
                "limit": {"type": "integer", "description": "Макс. количество"}
            }
        }
    })
    
    # === Google Calendar ===
    
    def get_calendar_events_tool(days: int = 7, user_id: int = None):
        # user_id будет передан из контекста
        if not user_id:
            return {"success": False, "message": "Пользователь не подключил календарь"}
        message, events = calendar_manager.list_events(user_id, days=days)
        return {"success": True, "message": message, "events": events}
    
    hr_agent.register_tool("get_calendar_events", get_calendar_events_tool, {
        "description": "Получить события из Google Calendar пользователя",
        "parameters": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Количество дней"}
            }
        }
    })
    
    # === Документы ===
    
    hr_agent.register_tool("create_offer", create_offer_document, {
        "description": "Создать оффер о приёме на работу",
        "parameters": {
            "type": "object",
            "properties": {
                "candidate_name": {"type": "string", "description": "Имя кандидата"},
                "position": {"type": "string", "description": "Должность"},
                "salary": {"type": "string", "description": "Зарплата"},
                "start_date": {"type": "string", "description": "Дата выхода"},
                "department": {"type": "string", "description": "Отдел"}
            },
            "required": ["candidate_name", "position", "salary", "start_date"]
        }
    })
    
    hr_agent.register_tool("create_welcome", create_welcome_document, {
        "description": "Создать welcome-документ для нового сотрудника",
        "parameters": {
            "type": "object",
            "properties": {
                "candidate_name": {"type": "string", "description": "Имя сотрудника"},
                "position": {"type": "string", "description": "Должность"},
                "start_date": {"type": "string", "description": "Дата выхода"},
                "buddy_name": {"type": "string", "description": "Имя buddy"},
                "manager_name": {"type": "string", "description": "Имя руководителя"}
            },
            "required": ["candidate_name", "position", "start_date"]
        }
    })
    
    hr_agent.register_tool("create_scorecard", create_scorecard_document, {
        "description": "Создать карту оценки кандидата после интервью",
        "parameters": {
            "type": "object",
            "properties": {
                "candidate_name": {"type": "string", "description": "Имя кандидата"},
                "position": {"type": "string", "description": "Должность"},
                "interviewer": {"type": "string", "description": "Интервьюер"},
                "competencies": {"type": "object", "description": "Оценки по компетенциям"}
            },
            "required": ["candidate_name", "position", "interviewer"]
        }
    })
    
    hr_agent.register_tool("create_rejection", create_rejection_letter, {
        "description": "Создать письмо с отказом кандидату",
        "parameters": {
            "type": "object",
            "properties": {
                "candidate_name": {"type": "string", "description": "Имя кандидата"},
                "position": {"type": "string", "description": "Должность"},
                "hr_name": {"type": "string", "description": "Имя HR"}
            },
            "required": ["candidate_name", "position"]
        }
    })
    
    hr_agent.register_tool("create_interview_invite", create_interview_invite, {
        "description": "Создать приглашение на интервью",
        "parameters": {
            "type": "object",
            "properties": {
                "candidate_name": {"type": "string", "description": "Имя кандидата"},
                "position": {"type": "string", "description": "Должность"},
                "interview_date": {"type": "string", "description": "Дата интервью"},
                "interview_time": {"type": "string", "description": "Время интервью"},
                "interview_type": {"type": "string", "description": "Тип (онлайн/офис)"}
            },
            "required": ["candidate_name", "position", "interview_date", "interview_time"]
        }
    })
    
    # === Воркфлоу ===
    
    def start_onboarding(employee_name: str, position: str, start_date: str,
                        recruiter: str = "-//-", salary: str = "", **kwargs):
        """Автоматический онбординг"""
        results = []
        
        # 1. Добавляем в таблицу
        result = add_employee_tool(employee_name, position, recruiter, start_date, salary)
        results.append(("add_to_tracker", result))
        
        # 2. Создаём welcome-документ
        result = create_welcome_document(employee_name, position, start_date, **kwargs)
        results.append(("create_welcome", result))
        
        # 3. Создаём оффер (если указана зарплата)
        if salary:
            result = create_offer_document(employee_name, position, salary, start_date, **kwargs)
            results.append(("create_offer", result))
        
        return {
            "success": True,
            "message": f"✅ Онбординг завершён для {employee_name}",
            "steps": results
        }
    
    hr_agent.register_tool("onboard_employee", start_onboarding, {
        "description": "Запустить полный процесс онбординга нового сотрудника",
        "parameters": {
            "type": "object",
            "properties": {
                "employee_name": {"type": "string", "description": "Имя сотрудника"},
                "position": {"type": "string", "description": "Должность"},
                "start_date": {"type": "string", "description": "Дата выхода"},
                "recruiter": {"type": "string", "description": "Рекрутер"},
                "salary": {"type": "string", "description": "Зарплата"}
            },
            "required": ["employee_name", "position", "start_date"]
        }
    })
    
    def process_new_candidate(name: str, position: str, email: str = None,
                             phone: str = None, skills: list = None, 
                             experience: str = None, source: str = None,
                             resume_text: str = None, **kwargs):
        """Обработка нового кандидата"""
        
        # Сохраняем в память
        candidate_id = hr_agent.memory.add_candidate({
            "name": name,
            "email": email,
            "phone": phone,
            "position": position,
            "skills": skills or [],
            "experience": experience,
            "source": source,
            "resume_text": resume_text,
            "status": "new"
        })
        
        # Ищем подходящие вакансии
        vacancies = hr_agent.memory.get_open_vacancies()
        matching_vacancies = []
        
        for v in vacancies:
            if position and position.lower() in v.get("title", "").lower():
                matching_vacancies.append(v)
        
        return {
            "success": True,
            "message": f"✅ Кандидат {name} сохранён (ID: {candidate_id})",
            "candidate_id": candidate_id,
            "matching_vacancies": len(matching_vacancies)
        }
    
    hr_agent.register_tool("process_candidate", process_new_candidate, {
        "description": "Обработать нового кандидата и сохранить в базу",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Имя кандидата"},
                "position": {"type": "string", "description": "Желаемая позиция"},
                "email": {"type": "string", "description": "Email"},
                "phone": {"type": "string", "description": "Телефон"},
                "skills": {"type": "array", "items": {"type": "string"}, "description": "Навыки"},
                "experience": {"type": "string", "description": "Опыт работы"},
                "source": {"type": "string", "description": "Источник"}
            },
            "required": ["name", "position"]
        }
    })
    
    logger.info(f"Registered {len(hr_agent.tools.list_tools())} tools")


def get_tools_for_mistral():
    """Получить схемы инструментов для Mistral"""
    return hr_agent.get_tools_for_mistral()


def execute_tool(name: str, params: Dict, context: Dict = None) -> Any:
    """Выполнить инструмент с контекстом"""
    # Добавляем контекст в параметры если нужно
    if context and "user_id" in context:
        params["user_id"] = context["user_id"]
    
    return hr_agent.execute_tool(name, **params)


# Инициализация при импорте
register_all_tools()
