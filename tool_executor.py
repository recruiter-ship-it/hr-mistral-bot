"""
Tool Executor - Централизованный исполнитель инструментов (как в OpenClaw)

Это ядро системы взаимодействия LLM с инструментами:
1. Получает tool calls от LLM
2. Маршрутизирует вызовы к нужному навыку/MCP серверу
3. Выполняет вызов и возвращает результат
4. Управляет политиками безопасности

Архитектура:
- ToolExecutor: главный класс, оркестрирует выполнение
- ToolRegistry: реестр всех инструментов
- SkillLoader: загрузчик навыков из SKILL.md файлов
- ToolPolicy: политики безопасности
"""

import os
import json
import logging
import asyncio
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================================
# DATA TYPES
# ============================================================

class ToolType(Enum):
    """Тип инструмента"""
    LOCAL = "local"           # Локальный Python обработчик
    MCP_EXTERNAL = "mcp_ext"  # Внешний MCP сервер
    MCP_BUILTIN = "mcp_local" # Встроенный MCP сервер
    EXTENDED = "extended"     # Расширенный навык из skills_extended


@dataclass
class ToolDefinition:
    """Определение инструмента"""
    name: str
    description: str
    parameters: Dict
    tool_type: ToolType
    handler: Optional[Callable] = None
    server_name: Optional[str] = None  # Для MCP инструментов
    skill_name: Optional[str] = None   # Для extended навыков
    requires_auth: bool = False
    dangerous: bool = False
    rate_limit: Optional[int] = None   # Запросов в минуту


@dataclass
class SkillDefinition:
    """Определение навыка (как SKILL.md в OpenClaw)"""
    name: str
    description: str
    tools: List[str]
    metadata: Dict = field(default_factory=dict)
    file_path: Optional[str] = None


@dataclass
class ToolCallResult:
    """Результат вызова инструмента"""
    success: bool
    result: Any
    error: Optional[str] = None
    execution_time_ms: int = 0
    tool_name: str = ""
    cached: bool = False


# ============================================================
# SKILL LOADER (загрузка SKILL.md как в OpenClaw)
# ============================================================

class SkillLoader:
    """
    Загрузчик навыков из SKILL.md файлов.
    Формат как в OpenClaw: YAML frontmatter + Markdown описание.
    """
    
    SKILLS_DIR = Path("/home/z/my-project/hr-mistral-bot/skills")
    
    def __init__(self):
        self.skills: Dict[str, SkillDefinition] = {}
        self._load_all_skills()
    
    def _load_all_skills(self):
        """Загрузить все навыки из директории skills/"""
        if not self.SKILLS_DIR.exists():
            logger.warning(f"Skills directory not found: {self.SKILLS_DIR}")
            return
        
        for skill_dir in self.SKILLS_DIR.iterdir():
            if skill_dir.is_dir():
                skill_file = skill_dir / "SKILL.md"
                if skill_file.exists():
                    skill = self._load_skill_file(skill_file)
                    if skill:
                        self.skills[skill.name] = skill
                        logger.info(f"Loaded skill: {skill.name} with tools: {skill.tools}")
    
    def _load_skill_file(self, file_path: Path) -> Optional[SkillDefinition]:
        """Загрузить один SKILL.md файл"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Парсим YAML frontmatter
            if not content.startswith('---'):
                logger.warning(f"Invalid SKILL.md format (no frontmatter): {file_path}")
                return None
            
            # Находим конец frontmatter
            parts = content.split('---', 2)
            if len(parts) < 3:
                logger.warning(f"Invalid SKILL.md format: {file_path}")
                return None
            
            frontmatter_str = parts[1].strip()
            
            # Парсим YAML
            import yaml
            frontmatter = yaml.safe_load(frontmatter_str)
            
            if not frontmatter:
                return None
            
            name = frontmatter.get('name', file_path.parent.name)
            description = frontmatter.get('description', '')
            metadata = frontmatter.get('metadata', {})
            tools = metadata.get('tools', [])
            
            return SkillDefinition(
                name=name,
                description=description,
                tools=tools,
                metadata=metadata,
                file_path=str(file_path)
            )
            
        except Exception as e:
            logger.error(f"Failed to load skill {file_path}: {e}")
            return None
    
    def get_skill_for_tool(self, tool_name: str) -> Optional[str]:
        """Получить имя навыка для инструмента"""
        for skill_name, skill in self.skills.items():
            if tool_name in skill.tools:
                return skill_name
        return None
    
    def build_skills_prompt(self) -> str:
        """
        Построить промпт со списком навыков (как buildWorkspaceSkillsPrompt в OpenClaw)
        """
        if not self.skills:
            return ""
        
        prompt_parts = ["## 🦞 Доступные навыки:\n"]
        
        for skill_name, skill in self.skills.items():
            emoji = skill.metadata.get('openclaw', {}).get('emoji', '📦')
            prompt_parts.append(f"### {emoji} **{skill_name}**")
            prompt_parts.append(f"{skill.description}\n")
            
            if skill.tools:
                prompt_parts.append("**Инструменты:**")
                for tool in skill.tools:
                    prompt_parts.append(f"- `{tool}`")
                prompt_parts.append("")
        
        return "\n".join(prompt_parts)


# ============================================================
# TOOL REGISTRY
# ============================================================

class ToolRegistry:
    """
    Реестр всех инструментов агента.
    Централизованное хранение и поиск инструментов.
    """
    
    def __init__(self):
        self.tools: Dict[str, ToolDefinition] = {}
        self._tool_to_skill: Dict[str, str] = {}  # tool_name -> skill_name
    
    def register(self, tool: ToolDefinition):
        """Зарегистрировать инструмент"""
        self.tools[tool.name] = tool
        if tool.skill_name:
            self._tool_to_skill[tool.name] = tool.skill_name
        logger.debug(f"Registered tool: {tool.name} ({tool.tool_type.value})")
    
    def get(self, name: str) -> Optional[ToolDefinition]:
        """Получить инструмент по имени"""
        return self.tools.get(name)
    
    def get_all_tools_schemas(self) -> List[Dict]:
        """Получить все схемы инструментов для Mistral API"""
        schemas = []
        for tool in self.tools.values():
            schemas.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters
                }
            })
        return schemas
    
    def get_tool_names(self) -> List[str]:
        """Получить список всех имён инструментов"""
        return list(self.tools.keys())
    
    def get_tools_by_skill(self, skill_name: str) -> List[ToolDefinition]:
        """Получить инструменты по имени навыка"""
        return [t for t in self.tools.values() if t.skill_name == skill_name]


# ============================================================
# TOOL POLICY
# ============================================================

class ToolPolicy:
    """
    Политики безопасности для инструментов (как в OpenClaw tool-policy.ts)
    """
    
    def __init__(self):
        # Инструменты, требующие подтверждения
        self.require_confirmation = {
            "terminal_execute", "fs_delete", "memory_clear"
        }
        
        # Инструменты с ограничением частоты
        self.rate_limits = {
            "image_generate": 10,  # 10 в минуту
            "browser_search": 30,  # 30 в минуту
        }
        
        # Заблокированные инструменты (можно отключить)
        self.blocked = set()
        
        # Разрешённые для всех (allowlist)
        self.allowed_for_all = {
            "fs_read_file", "fs_list_dir", "fs_search",
            "memory_remember", "memory_recall", "memory_list",
            "browser_search", "browser_fetch",
            "image_generate", "image_describe", "image_list"
        }
    
    def is_allowed(self, tool_name: str, user_id: int = None) -> Tuple[bool, str]:
        """Проверить, разрешён ли инструмент"""
        if tool_name in self.blocked:
            return False, f"Tool {tool_name} is blocked"
        
        # В будущем можно добавить проверку по user_id
        return True, "OK"
    
    def needs_confirmation(self, tool_name: str) -> bool:
        """Требует ли инструмент подтверждения"""
        return tool_name in self.require_confirmation


# ============================================================
# TOOL EXECUTOR (Главный класс)
# ============================================================

class ToolExecutor:
    """
    Централизованный исполнитель инструментов (как в OpenClaw pi-embedded-runner.ts)
    
    Отвечает за:
    1. Маршрутизацию вызовов к нужному обработчику
    2. Выполнение с обработкой ошибок
    3. Применение политик безопасности
    4. Логирование и метрики
    """
    
    def __init__(self):
        self.registry = ToolRegistry()
        self.policy = ToolPolicy()
        self.skill_loader = SkillLoader()
        
        # Кэш результатов (для повторных вызовов)
        self._result_cache: Dict[str, ToolCallResult] = {}
        
        # Счётчики для rate limiting
        self._rate_counters: Dict[str, List[float]] = {}
        
        # Инициализируем обработчики
        self._init_handlers()
    
    def _init_handlers(self):
        """Инициализация обработчиков для разных типов инструментов"""
        # Будет заполнено при регистрации навыков
        self._local_handlers: Dict[str, Callable] = {}
        self._mcp_orchestrator = None
        self._extended_skills = None
    
    def register_local_handler(self, tool_name: str, handler: Callable):
        """Зарегистрировать локальный обработчик"""
        self._local_handlers[tool_name] = handler
        logger.info(f"Registered local handler for: {tool_name}")
    
    def set_mcp_orchestrator(self, orchestrator):
        """Установить MCP оркестратор"""
        self._mcp_orchestrator = orchestrator
    
    def set_extended_skills(self, skills_registry):
        """Установить реестр расширенных навыков"""
        self._extended_skills = skills_registry
    
    async def execute(self, tool_name: str, params: Dict, user_id: int = None) -> ToolCallResult:
        """
        Выполнить инструмент (главный метод)
        
        Как в OpenClaw:
        1. Проверить политику
        2. Найти обработчик
        3. Выполнить
        4. Вернуть результат
        """
        start_time = datetime.now()
        
        # 1. Проверка политики
        allowed, reason = self.policy.is_allowed(tool_name, user_id)
        if not allowed:
            return ToolCallResult(
                success=False,
                result=None,
                error=reason,
                tool_name=tool_name
            )
        
        # 2. Проверка rate limit
        if not self._check_rate_limit(tool_name):
            return ToolCallResult(
                success=False,
                result=None,
                error=f"Rate limit exceeded for {tool_name}",
                tool_name=tool_name
            )
        
        # 3. Найти инструмент в реестре
        tool_def = self.registry.get(tool_name)
        
        try:
            result = None
            
            # 4. Маршрутизация по типу инструмента
            if tool_def:
                if tool_def.tool_type == ToolType.LOCAL:
                    result = await self._execute_local(tool_name, params)
                elif tool_def.tool_type == ToolType.MCP_EXTERNAL:
                    result = await self._execute_mcp(tool_name, params)
                elif tool_def.tool_type == ToolType.MCP_BUILTIN:
                    result = await self._execute_mcp_local(tool_name, params)
                elif tool_def.tool_type == ToolType.EXTENDED:
                    result = await self._execute_extended(tool_name, params)
            else:
                # Пробуем найти обработчик напрямую
                if tool_name in self._local_handlers:
                    result = await self._execute_local(tool_name, params)
                elif self._mcp_orchestrator:
                    result = await self._execute_mcp(tool_name, params)
                elif self._extended_skills:
                    result = await self._execute_extended(tool_name, params)
                else:
                    return ToolCallResult(
                        success=False,
                        result=None,
                        error=f"Tool not found: {tool_name}",
                        tool_name=tool_name
                    )
            
            execution_time = int((datetime.now() - start_time).total_seconds() * 1000)
            
            return ToolCallResult(
                success=True,
                result=result,
                execution_time_ms=execution_time,
                tool_name=tool_name
            )
            
        except Exception as e:
            logger.error(f"Tool execution failed: {tool_name} - {e}")
            return ToolCallResult(
                success=False,
                result=None,
                error=str(e),
                tool_name=tool_name
            )
    
    async def _execute_local(self, tool_name: str, params: Dict) -> Any:
        """Выполнить локальный обработчик"""
        handler = self._local_handlers.get(tool_name)
        if not handler:
            raise ValueError(f"No local handler for: {tool_name}")
        
        if asyncio.iscoroutinefunction(handler):
            return await handler(**params)
        else:
            return handler(**params)
    
    async def _execute_mcp(self, tool_name: str, params: Dict) -> Any:
        """Выполнить через MCP оркестратор"""
        if not self._mcp_orchestrator:
            raise ValueError("MCP orchestrator not initialized")
        
        return await self._mcp_orchestrator.call_tool(tool_name, params)
    
    async def _execute_mcp_local(self, tool_name: str, params: Dict) -> Any:
        """Выполнить встроенный MCP инструмент"""
        if not self._mcp_orchestrator:
            raise ValueError("MCP orchestrator not initialized")
        
        return await self._mcp_orchestrator.call_local_tool(tool_name, params)
    
    async def _execute_extended(self, tool_name: str, params: Dict) -> Any:
        """Выполнить расширенный навык"""
        if not self._extended_skills:
            raise ValueError("Extended skills not initialized")
        
        # Найти навык, содержащий этот инструмент
        skill_name = self.skill_loader.get_skill_for_tool(tool_name)
        if not skill_name:
            # Пробуем найти по имени инструмента
            for skill_name, skill in self._extended_skills.skills.items():
                for tool in skill.tools:
                    if tool.name == tool_name:
                        return await skill.execute(tool_name, **params)
            raise ValueError(f"No skill found for tool: {tool_name}")
        
        skill = self._extended_skills.skills.get(skill_name)
        if not skill:
            raise ValueError(f"Skill not found: {skill_name}")
        
        return await skill.execute(tool_name, **params)
    
    def _check_rate_limit(self, tool_name: str) -> bool:
        """Проверить rate limit"""
        limit = self.policy.rate_limits.get(tool_name)
        if not limit:
            return True
        
        now = datetime.now().timestamp()
        minute_ago = now - 60
        
        # Получаем список вызовов за последнюю минуту
        calls = self._rate_counters.get(tool_name, [])
        calls = [t for t in calls if t > minute_ago]
        
        if len(calls) >= limit:
            return False
        
        # Записываем новый вызов
        calls.append(now)
        self._rate_counters[tool_name] = calls
        return True
    
    def register_tool_from_skill(self, skill: SkillDefinition, tool_name: str, 
                                  handler: Callable, schema: Dict):
        """Зарегистрировать инструмент из навыка"""
        tool_def = ToolDefinition(
            name=tool_name,
            description=schema.get('description', ''),
            parameters=schema.get('parameters', {}),
            tool_type=ToolType.EXTENDED,
            handler=handler,
            skill_name=skill.name
        )
        self.registry.register(tool_def)
    
    def build_tools_for_mistral(self) -> List[Dict]:
        """Построить список инструментов для Mistral API"""
        return self.registry.get_all_tools_schemas()
    
    def get_skills_prompt(self) -> str:
        """Получить промпт со списком навыков"""
        return self.skill_loader.build_skills_prompt()


# ============================================================
# ГЛОБАЛЬНЫЙ ЭКЗЕМПЛЯР
# ============================================================

tool_executor = ToolExecutor()
