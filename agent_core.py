"""
HR Agent Core - Центральное ядро агента
Оркестрация инструментов, память и автономные воркфлоу
"""

import os
import json
import logging
import asyncio
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_INPUT = "needs_input"


@dataclass
class Task:
    """Задача для выполнения агентом"""
    id: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    steps: List[Dict] = field(default_factory=list)
    current_step: int = 0
    result: Any = None
    error: str = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class WorkflowStep:
    """Шаг в рабочем процессе"""
    name: str
    tool: str
    params: Dict
    condition: str = None  # Условие выполнения
    on_success: str = None  # Следующий шаг при успехе
    on_failure: str = None  # Следующий шаг при ошибке


class ToolRegistry:
    """Реестр всех инструментов агента"""
    
    def __init__(self):
        self._tools: Dict[str, Callable] = {}
        self._tool_schemas: Dict[str, Dict] = {}
    
    def register(self, name: str, func: Callable, schema: Dict):
        """Регистрация инструмента"""
        self._tools[name] = func
        self._tool_schemas[name] = schema
        logger.info(f"Tool registered: {name}")
    
    def get(self, name: str) -> Optional[Callable]:
        return self._tools.get(name)
    
    def get_schema(self, name: str) -> Optional[Dict]:
        return self._tool_schemas.get(name)
    
    def get_all_schemas(self) -> List[Dict]:
        """Получить все схемы для Mistral function calling"""
        schemas = []
        for name, schema in self._tool_schemas.items():
            schemas.append({
                "type": "function",
                "function": {
                    "name": name,
                    **schema
                }
            })
        return schemas
    
    def list_tools(self) -> List[str]:
        return list(self._tools.keys())


class MemorySystem:
    """Система памяти агента"""
    
    def __init__(self, db_path: str = "agent_memory.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Инициализация базы данных памяти"""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        
        # Кандидаты
        conn.execute("""
            CREATE TABLE IF NOT EXISTS candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                position TEXT,
                status TEXT DEFAULT 'new',
                skills TEXT,
                experience TEXT,
                salary_expectation TEXT,
                source TEXT,
                notes TEXT,
                resume_text TEXT,
                rating INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Вакансии
        conn.execute("""
            CREATE TABLE IF NOT EXISTS vacancies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                department TEXT,
                description TEXT,
                requirements TEXT,
                salary_range TEXT,
                status TEXT DEFAULT 'open',
                hiring_manager TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Знания компании
        conn.execute("""
            CREATE TABLE IF NOT EXISTS knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT,
                tags TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Взаимодействия
        conn.execute("""
            CREATE TABLE IF NOT EXISTS interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_id INTEGER,
                type TEXT,
                channel TEXT,
                summary TEXT,
                outcome TEXT,
                next_steps TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Задачи
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                description TEXT,
                status TEXT,
                steps TEXT,
                current_step INTEGER,
                result TEXT,
                error TEXT,
                created_at TIMESTAMP,
                updated_at TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()
    
    # === Кандидаты ===
    
    def add_candidate(self, candidate: Dict) -> int:
        """Добавить кандидата"""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            INSERT INTO candidates 
            (name, email, phone, position, status, skills, experience, 
             salary_expectation, source, notes, resume_text, rating)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            candidate.get('name'),
            candidate.get('email'),
            candidate.get('phone'),
            candidate.get('position'),
            candidate.get('status', 'new'),
            json.dumps(candidate.get('skills', []), ensure_ascii=False),
            candidate.get('experience'),
            candidate.get('salary_expectation'),
            candidate.get('source'),
            candidate.get('notes'),
            candidate.get('resume_text'),
            candidate.get('rating')
        ))
        candidate_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return candidate_id
    
    def get_candidate(self, candidate_id: int) -> Optional[Dict]:
        """Получить кандидата по ID"""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT * FROM candidates WHERE id = ?", (candidate_id,)
        )
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return self._row_to_dict(row, 'candidates')
        return None
    
    def search_candidates(self, query: str = None, status: str = None, 
                         position: str = None, limit: int = 10) -> List[Dict]:
        """Поиск кандидатов"""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        
        sql = "SELECT * FROM candidates WHERE 1=1"
        params = []
        
        if query:
            sql += " AND (name LIKE ? OR email LIKE ? OR skills LIKE ? OR notes LIKE ?)"
            query_param = f"%{query}%"
            params.extend([query_param, query_param, query_param, query_param])
        
        if status:
            sql += " AND status = ?"
            params.append(status)
        
        if position:
            sql += " AND position LIKE ?"
            params.append(f"%{position}%")
        
        sql += f" ORDER BY created_at DESC LIMIT {limit}"
        
        cursor = conn.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_dict(row, 'candidates') for row in rows]
    
    def update_candidate(self, candidate_id: int, updates: Dict) -> bool:
        """Обновить кандидата"""
        import sqlite3
        if not updates:
            return False
        
        conn = sqlite3.connect(self.db_path)
        set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
        values = list(updates.values()) + [datetime.now().isoformat()]
        
        conn.execute(
            f"UPDATE candidates SET {set_clause}, updated_at = ? WHERE id = ?",
            values + [candidate_id]
        )
        conn.commit()
        conn.close()
        return True
    
    # === Вакансии ===
    
    def add_vacancy(self, vacancy: Dict) -> int:
        """Добавить вакансию"""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            INSERT INTO vacancies 
            (title, department, description, requirements, salary_range, status, hiring_manager)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            vacancy.get('title'),
            vacancy.get('department'),
            vacancy.get('description'),
            vacancy.get('requirements'),
            vacancy.get('salary_range'),
            vacancy.get('status', 'open'),
            vacancy.get('hiring_manager')
        ))
        vacancy_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return vacancy_id
    
    def get_open_vacancies(self) -> List[Dict]:
        """Получить открытые вакансии"""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT * FROM vacancies WHERE status = 'open' ORDER BY created_at DESC"
        )
        rows = cursor.fetchall()
        conn.close()
        return [self._row_to_dict(row, 'vacancies') for row in rows]
    
    # === Знания ===
    
    def add_knowledge(self, category: str, title: str, content: str, tags: List[str] = None):
        """Добавить знание в базу"""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO knowledge (category, title, content, tags)
            VALUES (?, ?, ?, ?)
        """, (category, title, content, json.dumps(tags or [], ensure_ascii=False)))
        conn.commit()
        conn.close()
    
    def search_knowledge(self, query: str) -> List[Dict]:
        """Поиск по базе знаний"""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            SELECT * FROM knowledge 
            WHERE title LIKE ? OR content LIKE ? OR tags LIKE ?
            ORDER BY created_at DESC
        """, (f"%{query}%", f"%{query}%", f"%{query}%"))
        rows = cursor.fetchall()
        conn.close()
        return [self._row_to_dict(row, 'knowledge') for row in rows]
    
    # === Взаимодействия ===
    
    def log_interaction(self, candidate_id: int, interaction_type: str, 
                       channel: str, summary: str, outcome: str = None, 
                       next_steps: str = None):
        """Записать взаимодействие с кандидатом"""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO interactions 
            (candidate_id, type, channel, summary, outcome, next_steps)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (candidate_id, interaction_type, channel, summary, outcome, next_steps))
        conn.commit()
        conn.close()
    
    # === Задачи ===
    
    def save_task(self, task: Task):
        """Сохранить задачу"""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO tasks 
            (id, description, status, steps, current_step, result, error, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            task.id,
            task.description,
            task.status.value,
            json.dumps(task.steps, ensure_ascii=False),
            task.current_step,
            json.dumps(task.result, ensure_ascii=False) if task.result else None,
            task.error,
            task.created_at.isoformat(),
            task.updated_at.isoformat()
        ))
        conn.commit()
        conn.close()
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Получить задачу"""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return Task(
                id=row[0],
                description=row[1],
                status=TaskStatus(row[2]),
                steps=json.loads(row[3]) if row[3] else [],
                current_step=row[4],
                result=json.loads(row[5]) if row[5] else None,
                error=row[6],
                created_at=datetime.fromisoformat(row[7]),
                updated_at=datetime.fromisoformat(row[8])
            )
        return None
    
    def _row_to_dict(self, row, table_name: str) -> Dict:
        """Конвертировать строку в словарь"""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(f"PRAGMA table_info({table_name})")
        columns = [col[1] for col in cursor.fetchall()]
        conn.close()
        
        result = {}
        for i, col in enumerate(columns):
            value = row[i]
            # Парсим JSON поля
            if col in ['skills', 'tags', 'steps', 'result'] and value:
                try:
                    value = json.loads(value)
                except:
                    pass
            result[col] = value
        return result


class WorkflowEngine:
    """Движок для выполнения автономных воркфлоу"""
    
    # Предопределённые воркфлоу
    WORKFLOWS = {
        "onboard_employee": {
            "name": "Онбординг нового сотрудника",
            "description": "Полный процесс онбординга: добавление в таблицы, создание документов, отправка писем",
            "steps": [
                {"name": "add_to_tracker", "tool": "add_employee", "required": True},
                {"name": "create_welcome_doc", "tool": "create_document", "params": {"type": "welcome"}},
                {"name": "schedule_onboarding", "tool": "create_calendar_event", "required": True},
                {"name": "send_welcome_email", "tool": "send_email", "params": {"template": "welcome"}}
            ]
        },
        "process_candidate": {
            "name": "Обработка нового кандидата",
            "description": "Анализ резюме, сохранение в базу, сравнение с вакансиями",
            "steps": [
                {"name": "analyze_resume", "tool": "analyze_resume", "required": True},
                {"name": "save_candidate", "tool": "save_candidate", "required": True},
                {"name": "match_vacancies", "tool": "match_vacancies"},
                {"name": "send_confirmation", "tool": "send_email", "params": {"template": "application_received"}}
            ]
        },
        "interview_pipeline": {
            "name": "Пайплайн интервью",
            "description": "Планирование и проведение интервью",
            "steps": [
                {"name": "schedule_screening", "tool": "create_calendar_event", "required": True},
                {"name": "prepare_questions", "tool": "generate_interview_questions"},
                {"name": "send_invite", "tool": "send_email", "params": {"template": "interview_invite"}},
                {"name": "create_scorecard", "tool": "create_document", "params": {"type": "scorecard"}}
            ]
        },
        "reject_candidate": {
            "name": "Отклонение кандидата",
            "description": "Обновление статуса и отправка вежливого отказа",
            "steps": [
                {"name": "update_status", "tool": "update_candidate_status", "required": True},
                {"name": "send_rejection", "tool": "send_email", "params": {"template": "rejection"}, "required": True}
            ]
        },
        "make_offer": {
            "name": "Создание оффера",
            "description": "Генерация оффера и отправка кандидату",
            "steps": [
                {"name": "create_offer_doc", "tool": "create_document", "params": {"type": "offer"}, "required": True},
                {"name": "update_status", "tool": "update_candidate_status", "params": {"status": "offer"}},
                {"name": "send_offer", "tool": "send_email", "params": {"template": "offer"}, "required": True}
            ]
        }
    }
    
    def __init__(self, tool_registry: ToolRegistry, memory: MemorySystem):
        self.tools = tool_registry
        self.memory = memory
        self.active_workflows: Dict[str, Task] = {}
    
    def start_workflow(self, workflow_name: str, params: Dict) -> Task:
        """Запустить воркфлоу"""
        import uuid
        
        if workflow_name not in self.WORKFLOWS:
            raise ValueError(f"Unknown workflow: {workflow_name}")
        
        workflow = self.WORKFLOWS[workflow_name]
        
        task = Task(
            id=str(uuid.uuid4())[:8],
            description=workflow["name"],
            status=TaskStatus.IN_PROGRESS,
            steps=[{"step": s, "status": "pending", "result": None} for s in workflow["steps"]]
        )
        
        # Сохраняем параметры для использования в шагах
        task.result = {"params": params, "results": {}}
        
        self.active_workflows[task.id] = task
        self.memory.save_task(task)
        
        logger.info(f"Started workflow '{workflow_name}' with task_id: {task.id}")
        return task
    
    async def execute_step(self, task: Task, step_index: int) -> Dict:
        """Выполнить один шаг воркфлоу"""
        step_data = task.steps[step_index]
        step = step_data["step"]
        
        tool_name = step["tool"]
        tool_func = self.tools.get(tool_name)
        
        if not tool_func:
            return {"success": False, "error": f"Tool not found: {tool_name}"}
        
        # Подготавливаем параметры
        params = step.get("params", {})
        # Мерджим с параметрами из задачи
        if task.result and "params" in task.result:
            params = {**task.result["params"], **params}
        
        try:
            logger.info(f"Executing step '{step['name']}' with tool '{tool_name}'")
            result = await tool_func(**params) if asyncio.iscoroutinefunction(tool_func) else tool_func(**params)
            
            return {"success": True, "result": result}
        except Exception as e:
            logger.error(f"Step '{step['name']}' failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def continue_workflow(self, task_id: str) -> Task:
        """Продолжить выполнение воркфлоу"""
        task = self.active_workflows.get(task_id) or self.memory.get_task(task_id)
        
        if not task:
            raise ValueError(f"Task not found: {task_id}")
        
        if task.status != TaskStatus.IN_PROGRESS:
            return task
        
        # Выполняем текущий шаг
        while task.current_step < len(task.steps):
            step_result = await self.execute_step(task, task.current_step)
            
            task.steps[task.current_step]["status"] = "completed" if step_result["success"] else "failed"
            task.steps[task.current_step]["result"] = step_result
            
            # Сохраняем результат
            if task.result:
                task.result["results"][task.steps[task.current_step]["step"]["name"]] = step_result
            
            task.updated_at = datetime.now()
            
            if not step_result["success"] and task.steps[task.current_step]["step"].get("required"):
                task.status = TaskStatus.FAILED
                task.error = f"Step '{task.steps[task.current_step]['step']['name']}' failed: {step_result.get('error')}"
                break
            
            task.current_step += 1
        
        # Если все шаги выполнены
        if task.current_step >= len(task.steps):
            task.status = TaskStatus.COMPLETED
        
        self.memory.save_task(task)
        return task
    
    def get_workflow_status(self, task_id: str) -> Dict:
        """Получить статус воркфлоу"""
        task = self.memory.get_task(task_id)
        if not task:
            return {"error": "Task not found"}
        
        completed = sum(1 for s in task.steps if s["status"] == "completed")
        failed = sum(1 for s in task.steps if s["status"] == "failed")
        
        return {
            "task_id": task.id,
            "description": task.description,
            "status": task.status.value,
            "progress": f"{completed}/{len(task.steps)}",
            "current_step": task.current_step,
            "completed": completed,
            "failed": failed,
            "total": len(task.steps),
            "error": task.error
        }


class HRAgent:
    """Главный класс HR Агента"""
    
    def __init__(self):
        self.tools = ToolRegistry()
        self.memory = MemorySystem()
        self.workflows = WorkflowEngine(self.tools, self.memory)
        
        # Регистрируем базовые инструменты
        self._register_core_tools()
    
    def _register_core_tools(self):
        """Регистрация базовых инструментов"""
        
        # Управление кандидатами
        self.tools.register(
            "save_candidate",
            lambda **p: self.memory.add_candidate(p),
            {
                "description": "Сохранить кандидата в базу данных",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Имя кандидата"},
                        "email": {"type": "string", "description": "Email"},
                        "phone": {"type": "string", "description": "Телефон"},
                        "position": {"type": "string", "description": "Желаемая позиция"},
                        "skills": {"type": "array", "items": {"type": "string"}, "description": "Навыки"},
                        "experience": {"type": "string", "description": "Опыт работы"},
                        "salary_expectation": {"type": "string", "description": "Ожидания по зарплате"},
                        "source": {"type": "string", "description": "Источник кандидата"},
                        "notes": {"type": "string", "description": "Заметки"},
                        "resume_text": {"type": "string", "description": "Текст резюме"},
                        "rating": {"type": "integer", "description": "Оценка 1-10"}
                    },
                    "required": ["name"]
                }
            }
        )
        
        self.tools.register(
            "search_candidates",
            lambda query=None, status=None, position=None, limit=10: 
                self.memory.search_candidates(query, status, position, limit),
            {
                "description": "Поиск кандидатов в базе",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Поисковый запрос"},
                        "status": {"type": "string", "description": "Статус кандидата"},
                        "position": {"type": "string", "description": "Позиция"},
                        "limit": {"type": "integer", "description": "Макс. количество"}
                    }
                }
            }
        )
        
        self.tools.register(
            "update_candidate_status",
            lambda candidate_id, status: self.memory.update_candidate(candidate_id, {"status": status}),
            {
                "description": "Обновить статус кандидата",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "candidate_id": {"type": "integer", "description": "ID кандидата"},
                        "status": {"type": "string", "description": "Новый статус", 
                                  "enum": ["new", "screening", "interview", "offer", "hired", "rejected"]}
                    },
                    "required": ["candidate_id", "status"]
                }
            }
        )
        
        # Управление вакансиями
        self.tools.register(
            "create_vacancy",
            lambda **p: self.memory.add_vacancy(p),
            {
                "description": "Создать новую вакансию",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Название вакансии"},
                        "department": {"type": "string", "description": "Отдел"},
                        "description": {"type": "string", "description": "Описание"},
                        "requirements": {"type": "string", "description": "Требования"},
                        "salary_range": {"type": "string", "description": "Зарплатная вилка"},
                        "hiring_manager": {"type": "string", "description": "Нанимающий менеджер"}
                    },
                    "required": ["title"]
                }
            }
        )
        
        self.tools.register(
            "list_vacancies",
            lambda: self.memory.get_open_vacancies(),
            {
                "description": "Показать открытые вакансии",
                "parameters": {"type": "object", "properties": {}}
            }
        )
        
        # Воркфлоу
        self.tools.register(
            "start_workflow",
            lambda workflow_name, **params: self.workflows.start_workflow(workflow_name, params),
            {
                "description": "Запустить автоматический рабочий процесс",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "workflow_name": {
                            "type": "string", 
                            "description": "Название воркфлоу",
                            "enum": ["onboard_employee", "process_candidate", "interview_pipeline", 
                                    "reject_candidate", "make_offer"]
                        }
                    },
                    "required": ["workflow_name"]
                }
            }
        )
        
        self.tools.register(
            "get_workflow_status",
            lambda task_id: self.workflows.get_workflow_status(task_id),
            {
                "description": "Получить статус выполнения воркфлоу",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "description": "ID задачи"}
                    },
                    "required": ["task_id"]
                }
            }
        )
    
    def register_tool(self, name: str, func: Callable, schema: Dict):
        """Регистрация дополнительного инструмента"""
        self.tools.register(name, func, schema)
    
    def get_tools_for_mistral(self) -> List[Dict]:
        """Получить схемы инструментов для Mistral API"""
        return self.tools.get_all_schemas()
    
    def execute_tool(self, name: str, **params) -> Any:
        """Выполнить инструмент по имени"""
        func = self.tools.get(name)
        if not func:
            raise ValueError(f"Tool not found: {name}")
        return func(**params)


# Глобальный экземпляр агента
hr_agent = HRAgent()
