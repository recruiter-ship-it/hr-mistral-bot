"""
Extended Skills System for HR Bot
Навыки как в OpenClaw: Browser, Terminal, Filesystem, Memory, Communication, Image, etc.

Каждый навык - это набор инструментов для определённой области.
Навыки регистрируются в MCP Orchestrator и становятся доступны агенту.
"""

import os
import json
import logging
import asyncio
import subprocess
import shutil
import glob
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ============================================================
# SKILL BASE CLASS
# ============================================================

@dataclass
class SkillTool:
    """Определение инструмента навыка"""
    name: str
    description: str
    parameters: Dict
    handler: Callable


class BaseSkill:
    """Базовый класс для навыка"""
    
    name: str = "base"
    description: str = "Базовый навык"
    tools: List[SkillTool] = []
    
    def get_tools(self) -> List[Dict]:
        """Получить инструменты в формате Mistral"""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters
                }
            }
            for tool in self.tools
        ]
    
    async def execute(self, tool_name: str, **kwargs) -> Any:
        """Выполнить инструмент"""
        for tool in self.tools:
            if tool.name == tool_name:
                if asyncio.iscoroutinefunction(tool.handler):
                    return await tool.handler(**kwargs)
                else:
                    return tool.handler(**kwargs)
        return {"error": f"Tool {tool_name} not found in skill {self.name}"}


# ============================================================
# FILESYSTEM SKILL (как в OpenClaw)
# ============================================================

class FilesystemSkill(BaseSkill):
    """
    Навык работы с файловой системой.
    Позволяет читать, писать, создавать, удалять файлы и папки.
    """
    
    name = "filesystem"
    description = "Работа с файловой системой: чтение, запись, создание файлов и папок"
    
    # Базовая директория для безопасности
    BASE_DIR = Path("/home/z/my-project/hr-mistral-bot/workspace")
    
    def __init__(self):
        self.BASE_DIR.mkdir(parents=True, exist_ok=True)
        self._init_tools()
    
    def _init_tools(self):
        self.tools = [
            SkillTool(
                name="fs_read_file",
                description="Прочитать содержимое файла",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Путь к файлу (относительно workspace)"},
                        "encoding": {"type": "string", "description": "Кодировка (по умолчанию utf-8)", "default": "utf-8"}
                    },
                    "required": ["path"]
                },
                handler=self.read_file
            ),
            SkillTool(
                name="fs_write_file",
                description="Записать содержимое в файл (создаст если не существует)",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Путь к файлу"},
                        "content": {"type": "string", "description": "Содержимое файла"},
                        "mode": {"type": "string", "description": "Режим: 'write' (перезапись) или 'append' (добавление)", "default": "write"}
                    },
                    "required": ["path", "content"]
                },
                handler=self.write_file
            ),
            SkillTool(
                name="fs_list_dir",
                description="Показать содержимое директории",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Путь к директории (пусто = корень workspace)"},
                        "pattern": {"type": "string", "description": "Паттерн фильтрации (например, '*.txt')"}
                    }
                },
                handler=self.list_dir
            ),
            SkillTool(
                name="fs_create_dir",
                description="Создать директорию",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Путь к директории"}
                    },
                    "required": ["path"]
                },
                handler=self.create_dir
            ),
            SkillTool(
                name="fs_delete",
                description="Удалить файл или директорию",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Путь к файлу/директории"},
                        "recursive": {"type": "boolean", "description": "Рекурсивное удаление для директорий", "default": False}
                    },
                    "required": ["path"]
                },
                handler=self.delete
            ),
            SkillTool(
                name="fs_copy",
                description="Копировать файл или директорию",
                parameters={
                    "type": "object",
                    "properties": {
                        "source": {"type": "string", "description": "Исходный путь"},
                        "destination": {"type": "string", "description": "Путь назначения"}
                    },
                    "required": ["source", "destination"]
                },
                handler=self.copy
            ),
            SkillTool(
                name="fs_move",
                description="Переместить/переименовать файл или директорию",
                parameters={
                    "type": "object",
                    "properties": {
                        "source": {"type": "string", "description": "Исходный путь"},
                        "destination": {"type": "string", "description": "Путь назначения"}
                    },
                    "required": ["source", "destination"]
                },
                handler=self.move
            ),
            SkillTool(
                name="fs_search",
                description="Поиск файлов по имени или содержимому",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Поисковый запрос"},
                        "search_type": {"type": "string", "description": "Тип поиска: 'name' (по имени) или 'content' (по содержимому)", "default": "name"},
                        "path": {"type": "string", "description": "Директория поиска (пусто = весь workspace)"}
                    },
                    "required": ["query"]
                },
                handler=self.search
            ),
            SkillTool(
                name="fs_get_info",
                description="Получить информацию о файле (размер, дата создания, etc.)",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Путь к файлу"}
                    },
                    "required": ["path"]
                },
                handler=self.get_info
            )
        ]
    
    def _resolve_path(self, path: str) -> Path:
        """Безопасное разрешение пути"""
        full_path = (self.BASE_DIR / path).resolve()
        # Проверяем, что путь находится внутри BASE_DIR
        if not str(full_path).startswith(str(self.BASE_DIR.resolve())):
            raise ValueError(f"Access denied: path outside workspace: {path}")
        return full_path
    
    def read_file(self, path: str, encoding: str = "utf-8") -> Dict:
        """Прочитать файл"""
        try:
            full_path = self._resolve_path(path)
            if not full_path.exists():
                return {"error": f"File not found: {path}"}
            
            with open(full_path, 'r', encoding=encoding) as f:
                content = f.read()
            
            return {
                "success": True,
                "path": path,
                "content": content,
                "size": len(content),
                "lines": content.count('\n') + 1
            }
        except Exception as e:
            return {"error": str(e)}
    
    def write_file(self, path: str, content: str, mode: str = "write") -> Dict:
        """Записать в файл"""
        try:
            full_path = self._resolve_path(path)
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            write_mode = 'a' if mode == 'append' else 'w'
            with open(full_path, write_mode, encoding='utf-8') as f:
                f.write(content)
            
            return {
                "success": True,
                "path": path,
                "message": f"✅ Файл {'обновлён' if mode == 'append' else 'сохранён'}: {path}",
                "size": len(content)
            }
        except Exception as e:
            return {"error": str(e)}
    
    def list_dir(self, path: str = "", pattern: str = None) -> Dict:
        """Список директории"""
        try:
            full_path = self._resolve_path(path) if path else self.BASE_DIR
            if not full_path.exists():
                return {"error": f"Directory not found: {path}"}
            
            items = []
            for item in full_path.iterdir():
                if pattern and not item.match(pattern):
                    continue
                items.append({
                    "name": item.name,
                    "type": "directory" if item.is_dir() else "file",
                    "size": item.stat().st_size if item.is_file() else None,
                    "modified": datetime.fromtimestamp(item.stat().st_mtime).isoformat()
                })
            
            return {
                "success": True,
                "path": path or "/",
                "items": items,
                "count": len(items)
            }
        except Exception as e:
            return {"error": str(e)}
    
    def create_dir(self, path: str) -> Dict:
        """Создать директорию"""
        try:
            full_path = self._resolve_path(path)
            full_path.mkdir(parents=True, exist_ok=True)
            return {
                "success": True,
                "path": path,
                "message": f"✅ Директория создана: {path}"
            }
        except Exception as e:
            return {"error": str(e)}
    
    def delete(self, path: str, recursive: bool = False) -> Dict:
        """Удалить файл/директорию"""
        try:
            full_path = self._resolve_path(path)
            if not full_path.exists():
                return {"error": f"Path not found: {path}"}
            
            if full_path.is_file():
                full_path.unlink()
            elif full_path.is_dir():
                if recursive:
                    shutil.rmtree(full_path)
                else:
                    full_path.rmdir()
            
            return {
                "success": True,
                "message": f"✅ Удалено: {path}"
            }
        except Exception as e:
            return {"error": str(e)}
    
    def copy(self, source: str, destination: str) -> Dict:
        """Копировать"""
        try:
            src_path = self._resolve_path(source)
            dst_path = self._resolve_path(destination)
            
            if not src_path.exists():
                return {"error": f"Source not found: {source}"}
            
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            
            if src_path.is_file():
                shutil.copy2(src_path, dst_path)
            else:
                shutil.copytree(src_path, dst_path)
            
            return {
                "success": True,
                "message": f"✅ Скопировано: {source} → {destination}"
            }
        except Exception as e:
            return {"error": str(e)}
    
    def move(self, source: str, destination: str) -> Dict:
        """Переместить"""
        try:
            src_path = self._resolve_path(source)
            dst_path = self._resolve_path(destination)
            
            if not src_path.exists():
                return {"error": f"Source not found: {source}"}
            
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(src_path, dst_path)
            
            return {
                "success": True,
                "message": f"✅ Перемещено: {source} → {destination}"
            }
        except Exception as e:
            return {"error": str(e)}
    
    def search(self, query: str, search_type: str = "name", path: str = "") -> Dict:
        """Поиск файлов"""
        try:
            full_path = self._resolve_path(path) if path else self.BASE_DIR
            
            results = []
            
            if search_type == "name":
                for item in full_path.rglob(f"*{query}*"):
                    results.append({
                        "path": str(item.relative_to(self.BASE_DIR)),
                        "type": "directory" if item.is_dir() else "file"
                    })
            else:
                # Поиск по содержимому
                for item in full_path.rglob("*"):
                    if item.is_file() and item.suffix in ['.txt', '.md', '.py', '.json', '.yaml', '.yml', '.csv']:
                        try:
                            with open(item, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read()
                                if query.lower() in content.lower():
                                    results.append({
                                        "path": str(item.relative_to(self.BASE_DIR)),
                                        "type": "file",
                                        "matches": content.lower().count(query.lower())
                                    })
                        except:
                            pass
            
            return {
                "success": True,
                "query": query,
                "search_type": search_type,
                "results": results[:50],  # Лимит
                "count": len(results)
            }
        except Exception as e:
            return {"error": str(e)}
    
    def get_info(self, path: str) -> Dict:
        """Информация о файле"""
        try:
            full_path = self._resolve_path(path)
            if not full_path.exists():
                return {"error": f"Path not found: {path}"}
            
            stat = full_path.stat()
            return {
                "success": True,
                "path": path,
                "type": "directory" if full_path.is_dir() else "file",
                "size": stat.st_size,
                "size_human": self._human_size(stat.st_size),
                "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "permissions": oct(stat.st_mode)[-3:]
            }
        except Exception as e:
            return {"error": str(e)}
    
    def _human_size(self, size: int) -> str:
        """Человекочитаемый размер"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


# ============================================================
# TERMINAL SKILL (как в OpenClaw)
# ============================================================

class TerminalSkill(BaseSkill):
    """
    Навык выполнения терминальных команд.
    Позволяет выполнять shell команды в песочнице.
    """
    
    name = "terminal"
    description = "Выполнение терминальных команд (shell commands)"
    
    # Разрешённые команды ( whitelist )
    ALLOWED_COMMANDS = [
        "ls", "cat", "head", "tail", "grep", "find", "wc", "sort", "uniq",
        "echo", "pwd", "date", "whoami", "which", "python3", "python",
        "pip", "pip3", "git", "curl", "wget", "mkdir", "touch"
    ]
    
    # Запрещённые команды
    BLOCKED_COMMANDS = [
        "rm -rf /", "sudo", "chmod 777", "dd if=", "mkfs", ":(){ :|:& };:",
        "shutdown", "reboot", "init 0", "init 6"
    ]
    
    WORK_DIR = Path("/home/z/my-project/hr-mistral-bot/workspace")
    
    def __init__(self):
        self.WORK_DIR.mkdir(parents=True, exist_ok=True)
        self._init_tools()
    
    def _init_tools(self):
        self.tools = [
            SkillTool(
                name="terminal_execute",
                description="Выполнить shell команду",
                parameters={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Команда для выполнения"},
                        "timeout": {"type": "integer", "description": "Таймаут в секундах (по умолчанию 30)", "default": 30}
                    },
                    "required": ["command"]
                },
                handler=self.execute
            ),
            SkillTool(
                name="terminal_run_script",
                description="Выполнить скрипт (Python или Shell)",
                parameters={
                    "type": "object",
                    "properties": {
                        "script": {"type": "string", "description": "Тело скрипта"},
                        "language": {"type": "string", "description": "Язык: 'python' или 'bash'", "default": "python"}
                    },
                    "required": ["script"]
                },
                handler=self.run_script
            ),
            SkillTool(
                name="terminal_install_package",
                description="Установить Python пакет",
                parameters={
                    "type": "object",
                    "properties": {
                        "package": {"type": "string", "description": "Имя пакета"},
                        "version": {"type": "string", "description": "Версия (опционально)"}
                    },
                    "required": ["package"]
                },
                handler=self.install_package
            ),
            SkillTool(
                name="terminal_git_status",
                description="Показать статус git репозитория",
                parameters={"type": "object", "properties": {}},
                handler=self.git_status
            ),
            SkillTool(
                name="terminal_git_commit",
                description="Сделать git commit",
                parameters={
                    "type": "object",
                    "properties": {
                        "message": {"type": "string", "description": "Сообщение коммита"},
                        "files": {"type": "array", "items": {"type": "string"}, "description": "Файлы для коммита (пусто = все)"}
                    },
                    "required": ["message"]
                },
                handler=self.git_commit
            )
        ]
    
    def _validate_command(self, command: str) -> tuple:
        """Проверка безопасности команды"""
        # Проверяем заблокированные команды
        for blocked in self.BLOCKED_COMMANDS:
            if blocked in command:
                return False, f"Command blocked: contains '{blocked}'"
        
        # Извлекаем базовую команду
        base_cmd = command.split()[0] if command.split() else ""
        
        # Проверяем разрешённые
        if base_cmd not in self.ALLOWED_COMMANDS:
            # Разрешаем если команда начинается с разрешённой
            first_word = command.split()[0] if command.split() else ""
            if first_word not in self.ALLOWED_COMMANDS:
                return False, f"Command not in whitelist: {base_cmd}"
        
        return True, "OK"
    
    def execute(self, command: str, timeout: int = 30) -> Dict:
        """Выполнить команду"""
        try:
            # Валидация
            valid, msg = self._validate_command(command)
            if not valid:
                return {"error": msg}
            
            # Выполнение
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.WORK_DIR
            )
            
            return {
                "success": result.returncode == 0,
                "command": command,
                "stdout": result.stdout[:5000],  # Ограничение вывода
                "stderr": result.stderr[:1000],
                "return_code": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {"error": f"Command timed out after {timeout}s"}
        except Exception as e:
            return {"error": str(e)}
    
    def run_script(self, script: str, language: str = "python") -> Dict:
        """Выполнить скрипт"""
        try:
            # Создаём временный файл
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            ext = ".py" if language == "python" else ".sh"
            script_file = self.WORK_DIR / f"script_{timestamp}{ext}"
            
            with open(script_file, 'w') as f:
                f.write(script)
            
            # Выполняем
            if language == "python":
                cmd = f"python3 {script_file}"
            else:
                cmd = f"bash {script_file}"
            
            result = self.execute(cmd, timeout=60)
            
            # Удаляем временный файл
            script_file.unlink()
            
            return result
        except Exception as e:
            return {"error": str(e)}
    
    def install_package(self, package: str, version: str = None) -> Dict:
        """Установить пакет"""
        try:
            pkg_spec = f"{package}=={version}" if version else package
            cmd = f"pip install {pkg_spec}"
            return self.execute(cmd, timeout=120)
        except Exception as e:
            return {"error": str(e)}
    
    def git_status(self) -> Dict:
        """Git статус"""
        return self.execute("git status")
    
    def git_commit(self, message: str, files: List[str] = None) -> Dict:
        """Git commit"""
        try:
            # Добавляем файлы
            if files:
                for f in files:
                    self.execute(f"git add {f}")
            else:
                self.execute("git add .")
            
            # Коммит
            return self.execute(f'git commit -m "{message}"')
        except Exception as e:
            return {"error": str(e)}


# ============================================================
# BROWSER SKILL (как в OpenClaw)
# ============================================================

class BrowserSkill(BaseSkill):
    """
    Навык веб-автоматизации.
    Поиск, извлечение контента, скрапинг.
    """
    
    name = "browser"
    description = "Веб-автоматизация: поиск, извлечение контента, скрапинг"
    
    def __init__(self):
        self._init_tools()
    
    def _init_tools(self):
        self.tools = [
            SkillTool(
                name="browser_search",
                description="Поиск в интернете",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Поисковый запрос"},
                        "num_results": {"type": "integer", "description": "Количество результатов", "default": 10}
                    },
                    "required": ["query"]
                },
                handler=self.search
            ),
            SkillTool(
                name="browser_fetch",
                description="Получить содержимое веб-страницы",
                parameters={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL страницы"},
                        "extract_text": {"type": "boolean", "description": "Извлечь только текст", "default": True}
                    },
                    "required": ["url"]
                },
                handler=self.fetch
            ),
            SkillTool(
                name="browser_extract_links",
                description="Извлечь все ссылки со страницы",
                parameters={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL страницы"},
                        "pattern": {"type": "string", "description": "Фильтр по паттерну URL"}
                    },
                    "required": ["url"]
                },
                handler=self.extract_links
            ),
            SkillTool(
                name="browser_check_url",
                description="Проверить доступность URL",
                parameters={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL для проверки"}
                    },
                    "required": ["url"]
                },
                handler=self.check_url
            )
        ]
    
    async def search(self, query: str, num_results: int = 10) -> Dict:
        """Веб-поиск через z-ai-web-dev-sdk"""
        try:
            # Используем z-ai для поиска
            import subprocess
            import json
            
            result = subprocess.run(
                ['z-ai', 'function', '-n', 'web_search', '-a', 
                 json.dumps({"query": query, "num": num_results})],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                return {"error": f"Search failed: {result.stderr}"}
            
            # Парсим результат
            output = result.stdout
            # Извлекаем JSON из вывода
            import re
            json_match = re.search(r'\[.*\]', output, re.DOTALL)
            if json_match:
                results = json.loads(json_match.group())
                return {
                    "success": True,
                    "query": query,
                    "results": results,
                    "count": len(results)
                }
            
            return {"error": "Failed to parse search results"}
        except Exception as e:
            return {"error": str(e)}
    
    async def fetch(self, url: str, extract_text: bool = True) -> Dict:
        """Получить страницу"""
        try:
            import requests
            from bs4 import BeautifulSoup
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            if extract_text:
                soup = BeautifulSoup(response.text, 'html.parser')
                # Удаляем скрипты и стили
                for script in soup(["script", "style", "nav", "footer", "header"]):
                    script.decompose()
                
                text = soup.get_text(separator='\n', strip=True)
                # Убираем лишние пробелы
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                content = '\n'.join(lines[:100])  # Лимит строк
                
                return {
                    "success": True,
                    "url": url,
                    "title": soup.title.string if soup.title else "",
                    "content": content[:5000],
                    "status_code": response.status_code
                }
            else:
                return {
                    "success": True,
                    "url": url,
                    "content": response.text[:10000],
                    "status_code": response.status_code
                }
        except Exception as e:
            return {"error": str(e)}
    
    async def extract_links(self, url: str, pattern: str = None) -> Dict:
        """Извлечь ссылки"""
        try:
            import requests
            from bs4 import BeautifulSoup
            from urllib.parse import urljoin, urlparse
            
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url, headers=headers, timeout=30)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            links = []
            for a in soup.find_all('a', href=True):
                href = urljoin(url, a['href'])
                if pattern and pattern not in href:
                    continue
                links.append({
                    "url": href,
                    "text": a.get_text(strip=True)[:100],
                    "domain": urlparse(href).netloc
                })
            
            return {
                "success": True,
                "url": url,
                "links": links[:50],
                "count": len(links)
            }
        except Exception as e:
            return {"error": str(e)}
    
    async def check_url(self, url: str) -> Dict:
        """Проверить URL"""
        try:
            import requests
            
            response = requests.head(url, timeout=10, allow_redirects=True)
            return {
                "success": True,
                "url": url,
                "status_code": response.status_code,
                "accessible": response.status_code < 400,
                "final_url": response.url,
                "headers": dict(response.headers)
            }
        except Exception as e:
            return {"error": str(e)}


# ============================================================
# MEMORY SKILL (как в OpenClaw)
# ============================================================

class MemorySkill(BaseSkill):
    """
    Навык персистентной памяти.
    Хранение и извлечение информации между сессиями.
    """
    
    name = "memory"
    description = "Персистентная память: хранение и поиск информации"
    
    MEMORY_FILE = Path("/home/z/my-project/hr-mistral-bot/memory/agent_memory.json")
    
    def __init__(self):
        self.MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        self._load_memory()
        self._init_tools()
    
    def _init_tools(self):
        self.tools = [
            SkillTool(
                name="memory_remember",
                description="Сохранить информацию в память",
                parameters={
                    "type": "object",
                    "properties": {
                        "key": {"type": "string", "description": "Ключ для поиска"},
                        "value": {"type": "string", "description": "Значение для сохранения"},
                        "category": {"type": "string", "description": "Категория (опционально)"},
                        "tags": {"type": "array", "items": {"type": "string"}, "description": "Теги"}
                    },
                    "required": ["key", "value"]
                },
                handler=self.remember
            ),
            SkillTool(
                name="memory_recall",
                description="Вспомнить информацию из памяти",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Поисковый запрос"},
                        "category": {"type": "string", "description": "Фильтр по категории"},
                        "limit": {"type": "integer", "description": "Макс. количество результатов", "default": 10}
                    },
                    "required": ["query"]
                },
                handler=self.recall
            ),
            SkillTool(
                name="memory_forget",
                description="Удалить запись из памяти",
                parameters={
                    "type": "object",
                    "properties": {
                        "key": {"type": "string", "description": "Ключ для удаления"}
                    },
                    "required": ["key"]
                },
                handler=self.forget
            ),
            SkillTool(
                name="memory_list",
                description="Показать все записи в памяти",
                parameters={
                    "type": "object",
                    "properties": {
                        "category": {"type": "string", "description": "Фильтр по категории"},
                        "limit": {"type": "integer", "description": "Макс. количество", "default": 20}
                    }
                },
                handler=self.list_memories
            ),
            SkillTool(
                name="memory_clear",
                description="Очистить всю память",
                parameters={
                    "type": "object",
                    "properties": {
                        "confirm": {"type": "boolean", "description": "Подтверждение очистки"}
                    },
                    "required": ["confirm"]
                },
                handler=self.clear
            )
        ]
    
    def _load_memory(self):
        """Загрузить память из файла"""
        if self.MEMORY_FILE.exists():
            with open(self.MEMORY_FILE, 'r', encoding='utf-8') as f:
                self._memory = json.load(f)
        else:
            self._memory = {
                "entries": {},
                "categories": {},
                "metadata": {
                    "created": datetime.now().isoformat(),
                    "total_entries": 0
                }
            }
    
    def _save_memory(self):
        """Сохранить память в файл"""
        self._memory["metadata"]["updated"] = datetime.now().isoformat()
        self._memory["metadata"]["total_entries"] = len(self._memory["entries"])
        
        with open(self.MEMORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(self._memory, f, ensure_ascii=False, indent=2)
    
    def remember(self, key: str, value: str, category: str = "general", tags: List[str] = None) -> Dict:
        """Сохранить в память"""
        entry = {
            "key": key,
            "value": value,
            "category": category,
            "tags": tags or [],
            "created": datetime.now().isoformat(),
            "access_count": 0
        }
        
        self._memory["entries"][key] = entry
        
        # Обновляем категории
        if category not in self._memory["categories"]:
            self._memory["categories"][category] = []
        self._memory["categories"][category].append(key)
        
        self._save_memory()
        
        return {
            "success": True,
            "message": f"✅ Запомнено: {key}",
            "key": key,
            "category": category
        }
    
    def recall(self, query: str, category: str = None, limit: int = 10) -> Dict:
        """Найти в памяти"""
        results = []
        query_lower = query.lower()
        
        for key, entry in self._memory["entries"].items():
            # Фильтр по категории
            if category and entry.get("category") != category:
                continue
            
            # Поиск по ключу и значению
            if (query_lower in key.lower() or 
                query_lower in entry.get("value", "").lower() or
                any(query_lower in tag.lower() for tag in entry.get("tags", []))):
                
                entry["access_count"] = entry.get("access_count", 0) + 1
                results.append(entry)
        
        self._save_memory()
        
        return {
            "success": True,
            "query": query,
            "results": results[:limit],
            "count": len(results)
        }
    
    def forget(self, key: str) -> Dict:
        """Забыть запись"""
        if key not in self._memory["entries"]:
            return {"error": f"Key not found: {key}"}
        
        entry = self._memory["entries"].pop(key)
        
        # Удаляем из категории
        cat = entry.get("category")
        if cat in self._memory["categories"]:
            self._memory["categories"][cat] = [
                k for k in self._memory["categories"][cat] if k != key
            ]
        
        self._save_memory()
        
        return {
            "success": True,
            "message": f"✅ Забыто: {key}"
        }
    
    def list_memories(self, category: str = None, limit: int = 20) -> Dict:
        """Список всех записей"""
        entries = list(self._memory["entries"].values())
        
        if category:
            entries = [e for e in entries if e.get("category") == category]
        
        # Сортируем по дате создания (новые первые)
        entries.sort(key=lambda x: x.get("created", ""), reverse=True)
        
        return {
            "success": True,
            "entries": entries[:limit],
            "total": len(self._memory["entries"]),
            "categories": list(self._memory["categories"].keys())
        }
    
    def clear(self, confirm: bool = False) -> Dict:
        """Очистить память"""
        if not confirm:
            return {"error": "Confirmation required. Set confirm=true"}
        
        self._memory = {
            "entries": {},
            "categories": {},
            "metadata": {
                "created": datetime.now().isoformat(),
                "total_entries": 0
            }
        }
        self._save_memory()
        
        return {
            "success": True,
            "message": "✅ Память очищена"
        }


# ============================================================
# COMMUNICATION SKILL (Slack, Discord, Email)
# ============================================================

class CommunicationSkill(BaseSkill):
    """
    Навык коммуникации.
    Отправка сообщений в Slack, Discord, Email.
    """
    
    name = "communication"
    description = "Коммуникация: Slack, Discord, Email уведомления"
    
    def __init__(self):
        self._init_tools()
    
    def _init_tools(self):
        self.tools = [
            SkillTool(
                name="comm_send_email",
                description="Отправить email письмо",
                parameters={
                    "type": "object",
                    "properties": {
                        "to": {"type": "string", "description": "Email получателя"},
                        "subject": {"type": "string", "description": "Тема письма"},
                        "body": {"type": "string", "description": "Тело письма"},
                        "html": {"type": "boolean", "description": "HTML формат", "default": False}
                    },
                    "required": ["to", "subject", "body"]
                },
                handler=self.send_email
            ),
            SkillTool(
                name="comm_slack_message",
                description="Отправить сообщение в Slack",
                parameters={
                    "type": "object",
                    "properties": {
                        "channel": {"type": "string", "description": "Канал или ID пользователя"},
                        "message": {"type": "string", "description": "Текст сообщения"}
                    },
                    "required": ["channel", "message"]
                },
                handler=self.slack_message
            ),
            SkillTool(
                name="comm_discord_message",
                description="Отправить сообщение в Discord",
                parameters={
                    "type": "object",
                    "properties": {
                        "webhook_url": {"type": "string", "description": "Discord webhook URL"},
                        "message": {"type": "string", "description": "Текст сообщения"},
                        "username": {"type": "string", "description": "Имя бота (опционально)"}
                    },
                    "required": ["webhook_url", "message"]
                },
                handler=self.discord_message
            ),
            SkillTool(
                name="comm_telegram_message",
                description="Отправить сообщение в Telegram (другому пользователю)",
                parameters={
                    "type": "object",
                    "properties": {
                        "chat_id": {"type": "string", "description": "Chat ID получателя"},
                        "message": {"type": "string", "description": "Текст сообщения"}
                    },
                    "required": ["chat_id", "message"]
                },
                handler=self.telegram_message
            )
        ]
    
    def send_email(self, to: str, subject: str, body: str, html: bool = False) -> Dict:
        """Отправить email"""
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
            smtp_port = int(os.getenv("SMTP_PORT", "587"))
            smtp_user = os.getenv("SMTP_USER")
            smtp_pass = os.getenv("SMTP_PASS")
            
            if not smtp_user or not smtp_pass:
                return {"error": "SMTP credentials not configured. Set SMTP_USER and SMTP_PASS"}
            
            msg = MIMEMultipart()
            msg['From'] = smtp_user
            msg['To'] = to
            msg['Subject'] = subject
            
            msg.attach(MIMEText(body, 'html' if html else 'plain'))
            
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
            
            return {
                "success": True,
                "message": f"✅ Email отправлен на {to}",
                "to": to,
                "subject": subject
            }
        except Exception as e:
            return {"error": str(e)}
    
    def slack_message(self, channel: str, message: str) -> Dict:
        """Отправить в Slack"""
        try:
            import requests
            
            slack_token = os.getenv("SLACK_BOT_TOKEN")
            if not slack_token:
                return {"error": "SLACK_BOT_TOKEN not configured"}
            
            response = requests.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {slack_token}"},
                json={
                    "channel": channel,
                    "text": message
                }
            )
            
            data = response.json()
            if data.get("ok"):
                return {
                    "success": True,
                    "message": f"✅ Отправлено в Slack: {channel}",
                    "ts": data.get("ts")
                }
            else:
                return {"error": f"Slack error: {data.get('error')}"}
        except Exception as e:
            return {"error": str(e)}
    
    def discord_message(self, webhook_url: str, message: str, username: str = None) -> Dict:
        """Отправить в Discord"""
        try:
            import requests
            
            data = {"content": message}
            if username:
                data["username"] = username
            
            response = requests.post(webhook_url, json=data)
            
            if response.status_code == 204:
                return {
                    "success": True,
                    "message": "✅ Отправлено в Discord"
                }
            else:
                return {"error": f"Discord error: {response.status_code}"}
        except Exception as e:
            return {"error": str(e)}
    
    def telegram_message(self, chat_id: str, message: str) -> Dict:
        """Отправить в Telegram"""
        try:
            import requests
            
            bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
            if not bot_token:
                return {"error": "TELEGRAM_BOT_TOKEN not configured"}
            
            response = requests.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "Markdown"
                }
            )
            
            data = response.json()
            if data.get("ok"):
                return {
                    "success": True,
                    "message": f"✅ Отправлено в Telegram: {chat_id}"
                }
            else:
                return {"error": f"Telegram error: {data.get('description')}"}
        except Exception as e:
            return {"error": str(e)}


# ============================================================
# IMAGE SKILL (Генерация изображений)
# ============================================================

class ImageSkill(BaseSkill):
    """
    Навык работы с изображениями.
    Генерация, анализ, обработка.
    """
    
    name = "image"
    description = "Работа с изображениями: генерация через AI, анализ"
    
    OUTPUT_DIR = Path("/home/z/my-project/hr-mistral-bot/workspace/images")
    
    def __init__(self):
        self.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        self._init_tools()
    
    def _init_tools(self):
        self.tools = [
            SkillTool(
                name="image_generate",
                description="Сгенерировать изображение через AI",
                parameters={
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "Описание изображения"},
                        "size": {"type": "string", "description": "Размер: 1024x1024, 768x1344, 1344x768", "default": "1024x1024"},
                        "filename": {"type": "string", "description": "Имя файла (опционально)"}
                    },
                    "required": ["prompt"]
                },
                handler=self.generate
            ),
            SkillTool(
                name="image_describe",
                description="Описать содержимое изображения (URL или путь)",
                parameters={
                    "type": "object",
                    "properties": {
                        "source": {"type": "string", "description": "URL или путь к изображению"}
                    },
                    "required": ["source"]
                },
                handler=self.describe
            ),
            SkillTool(
                name="image_list",
                description="Показать сгенерированные изображения",
                parameters={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Макс. количество", "default": 10}
                    }
                },
                handler=self.list_images
            )
        ]
    
    async def generate(self, prompt: str, size: str = "1024x1024", filename: str = None) -> Dict:
        """Сгенерировать изображение"""
        try:
            # Используем z-ai CLI
            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"generated_{timestamp}.png"
            
            output_path = self.OUTPUT_DIR / filename
            
            result = subprocess.run(
                ['z-ai-generate', '-p', prompt, '-o', str(output_path), '-s', size],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0 and output_path.exists():
                return {
                    "success": True,
                    "message": f"✅ Изображение создано: {filename}",
                    "path": str(output_path),
                    "prompt": prompt,
                    "size": size
                }
            else:
                return {"error": f"Generation failed: {result.stderr}"}
        except Exception as e:
            return {"error": str(e)}
    
    async def describe(self, source: str) -> Dict:
        """Описать изображение через VLM"""
        try:
            # Используем z-ai для описания
            import base64
            
            # Если это URL
            if source.startswith("http"):
                import requests
                response = requests.get(source)
                image_data = base64.b64encode(response.content).decode()
            else:
                # Локальный файл
                with open(source, 'rb') as f:
                    image_data = base64.b64encode(f.read()).decode()
            
            # Вызываем VLM через z-ai
            # TODO: реализовать через z-ai-web-dev-sdk VLM
            
            return {
                "success": True,
                "message": "Image analysis requires VLM integration",
                "source": source
            }
        except Exception as e:
            return {"error": str(e)}
    
    def list_images(self, limit: int = 10) -> Dict:
        """Список изображений"""
        try:
            images = []
            for f in self.OUTPUT_DIR.glob("*.png"):
                stat = f.stat()
                images.append({
                    "filename": f.name,
                    "path": str(f),
                    "size": stat.st_size,
                    "created": datetime.fromtimestamp(stat.st_ctime).isoformat()
                })
            
            images.sort(key=lambda x: x["created"], reverse=True)
            
            return {
                "success": True,
                "images": images[:limit],
                "total": len(images)
            }
        except Exception as e:
            return {"error": str(e)}


# ============================================================
# DATABASE SKILL (SQL операции)
# ============================================================

class DatabaseSkill(BaseSkill):
    """
    Навык работы с базами данных.
    SQL запросы, миграции.
    """
    
    name = "database"
    description = "Работа с базами данных: SQL запросы, SQLite, PostgreSQL"
    
    def __init__(self):
        self._init_tools()
    
    def _init_tools(self):
        self.tools = [
            SkillTool(
                name="db_sqlite_query",
                description="Выполнить SQL запрос к SQLite",
                parameters={
                    "type": "object",
                    "properties": {
                        "db_path": {"type": "string", "description": "Путь к БД"},
                        "query": {"type": "string", "description": "SQL запрос"},
                        "params": {"type": "array", "description": "Параметры запроса"}
                    },
                    "required": ["db_path", "query"]
                },
                handler=self.sqlite_query
            ),
            SkillTool(
                name="db_sqlite_create_table",
                description="Создать таблицу в SQLite",
                parameters={
                    "type": "object",
                    "properties": {
                        "db_path": {"type": "string", "description": "Путь к БД"},
                        "table_name": {"type": "string", "description": "Имя таблицы"},
                        "columns": {"type": "object", "description": "Колонки: {name: type}"}
                    },
                    "required": ["db_path", "table_name", "columns"]
                },
                handler=self.sqlite_create_table
            ),
            SkillTool(
                name="db_list_tables",
                description="Показать таблицы в БД",
                parameters={
                    "type": "object",
                    "properties": {
                        "db_path": {"type": "string", "description": "Путь к БД"}
                    },
                    "required": ["db_path"]
                },
                handler=self.list_tables
            ),
            SkillTool(
                name="db_export_csv",
                description="Экспортировать таблицу в CSV",
                parameters={
                    "type": "object",
                    "properties": {
                        "db_path": {"type": "string", "description": "Путь к БД"},
                        "table_name": {"type": "string", "description": "Имя таблицы"},
                        "output_path": {"type": "string", "description": "Путь к CSV файлу"}
                    },
                    "required": ["db_path", "table_name", "output_path"]
                },
                handler=self.export_csv
            )
        ]
    
    def sqlite_query(self, db_path: str, query: str, params: List = None) -> Dict:
        """Выполнить SQL запрос"""
        try:
            import sqlite3
            
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            if query.strip().upper().startswith("SELECT"):
                rows = cursor.fetchall()
                results = [dict(row) for row in rows]
                conn.close()
                return {
                    "success": True,
                    "results": results,
                    "count": len(results)
                }
            else:
                conn.commit()
                affected = cursor.rowcount
                conn.close()
                return {
                    "success": True,
                    "message": f"✅ Запрос выполнен. Затронуто строк: {affected}",
                    "rows_affected": affected
                }
        except Exception as e:
            return {"error": str(e)}
    
    def sqlite_create_table(self, db_path: str, table_name: str, columns: Dict) -> Dict:
        """Создать таблицу"""
        try:
            import sqlite3
            
            cols_def = ", ".join([f"{name} {dtype}" for name, dtype in columns.items()])
            query = f"CREATE TABLE IF NOT EXISTS {table_name} ({cols_def}, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
            
            return self.sqlite_query(db_path, query)
        except Exception as e:
            return {"error": str(e)}
    
    def list_tables(self, db_path: str) -> Dict:
        """Список таблиц"""
        return self.sqlite_query(
            db_path,
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    
    def export_csv(self, db_path: str, table_name: str, output_path: str) -> Dict:
        """Экспорт в CSV"""
        try:
            import sqlite3
            import csv
            
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(f"SELECT * FROM {table_name}")
            
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            
            with open(output_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(columns)
                writer.writerows(rows)
            
            conn.close()
            
            return {
                "success": True,
                "message": f"✅ Экспортировано в {output_path}",
                "rows": len(rows)
            }
        except Exception as e:
            return {"error": str(e)}


# ============================================================
# ANALYTICS SKILL (Аналитика и отчёты)
# ============================================================

class AnalyticsSkill(BaseSkill):
    """
    Навык аналитики.
    Создание отчётов, графиков, анализ данных.
    """
    
    name = "analytics"
    description = "Аналитика: отчёты, графики, анализ данных"
    
    OUTPUT_DIR = Path("/home/z/my-project/hr-mistral-bot/workspace/reports")
    
    def __init__(self):
        self.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        self._init_tools()
    
    def _init_tools(self):
        self.tools = [
            SkillTool(
                name="analytics_create_report",
                description="Создать аналитический отчёт",
                parameters={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Название отчёта"},
                        "data": {"type": "object", "description": "Данные для отчёта"},
                        "format": {"type": "string", "description": "Формат: 'markdown' или 'json'", "default": "markdown"}
                    },
                    "required": ["title", "data"]
                },
                handler=self.create_report
            ),
            SkillTool(
                name="analytics_create_chart",
                description="Создать график из данных",
                parameters={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Название графика"},
                        "chart_type": {"type": "string", "description": "Тип: 'bar', 'line', 'pie'"},
                        "labels": {"type": "array", "items": {"type": "string"}, "description": "Метки оси X"},
                        "values": {"type": "array", "items": {"type": "number"}, "description": "Значения"},
                        "filename": {"type": "string", "description": "Имя файла"}
                    },
                    "required": ["title", "chart_type", "labels", "values"]
                },
                handler=self.create_chart
            ),
            SkillTool(
                name="analytics_summarize",
                description="Создать сводку данных",
                parameters={
                    "type": "object",
                    "properties": {
                        "data": {"type": "array", "items": {"type": "number"}, "description": "Числовые данные"},
                        "name": {"type": "string", "description": "Название набора данных"}
                    },
                    "required": ["data", "name"]
                },
                handler=self.summarize
            )
        ]
    
    def create_report(self, title: str, data: Dict, format: str = "markdown") -> Dict:
        """Создать отчёт"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"report_{title.replace(' ', '_')}_{timestamp}"
            
            if format == "json":
                filepath = self.OUTPUT_DIR / f"{filename}.json"
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump({
                        "title": title,
                        "created": datetime.now().isoformat(),
                        "data": data
                    }, f, ensure_ascii=False, indent=2)
            else:
                filepath = self.OUTPUT_DIR / f"{filename}.md"
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(f"# {title}\n\n")
                    f.write(f"*Создано: {datetime.now().strftime('%d.%m.%Y %H:%M')}*\n\n")
                    f.write("## Данные\n\n")
                    f.write(f"```json\n{json.dumps(data, ensure_ascii=False, indent=2)}\n```\n")
            
            return {
                "success": True,
                "message": f"✅ Отчёт создан: {filepath.name}",
                "path": str(filepath)
            }
        except Exception as e:
            return {"error": str(e)}
    
    def create_chart(self, title: str, chart_type: str, labels: List[str], values: List[float], filename: str = None) -> Dict:
        """Создать график"""
        try:
            import matplotlib
            matplotlib.use('Agg')  # Non-interactive backend
            import matplotlib.pyplot as plt
            
            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"chart_{timestamp}.png"
            
            filepath = self.OUTPUT_DIR / filename
            
            fig, ax = plt.subplots(figsize=(10, 6))
            
            if chart_type == "bar":
                ax.bar(labels, values)
            elif chart_type == "line":
                ax.plot(labels, values, marker='o')
            elif chart_type == "pie":
                ax.pie(values, labels=labels, autopct='%1.1f%%')
            else:
                ax.bar(labels, values)
            
            ax.set_title(title)
            plt.xticks(rotation=45, ha='right')
            plt.tight_layout()
            plt.savefig(filepath, dpi=100)
            plt.close()
            
            return {
                "success": True,
                "message": f"✅ График создан: {filename}",
                "path": str(filepath)
            }
        except Exception as e:
            return {"error": str(e)}
    
    def summarize(self, data: List[float], name: str) -> Dict:
        """Сводка данных"""
        try:
            import statistics
            
            if not data:
                return {"error": "No data provided"}
            
            summary = {
                "name": name,
                "count": len(data),
                "sum": sum(data),
                "mean": statistics.mean(data),
                "median": statistics.median(data),
                "min": min(data),
                "max": max(data),
                "range": max(data) - min(data)
            }
            
            if len(data) > 1:
                summary["stdev"] = statistics.stdev(data)
                summary["variance"] = statistics.variance(data)
            
            return {
                "success": True,
                "summary": summary
            }
        except Exception as e:
            return {"error": str(e)}


# ============================================================
# VOICE SKILL (Голосовой ввод/вывод)
# ============================================================

class VoiceSkill(BaseSkill):
    """
    Навык работы с голосом.
    Транскрибация аудио в текст (ASR) и синтез речи (TTS).
    """
    
    name = "voice"
    description = "Голосовой ввод/вывод: транскрибация аудио, синтез речи"
    
    OUTPUT_DIR = Path("/home/z/my-project/hr-mistral-bot/workspace/audio")
    
    def __init__(self):
        self.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        self._init_tools()
    
    def _init_tools(self):
        self.tools = [
            SkillTool(
                name="voice_transcribe",
                description="Транскрибировать аудиофайл в текст (поддерживает MP3, WAV, OGG, WebM)",
                parameters={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Путь к аудиофайлу"},
                        "language": {"type": "string", "description": "Язык (ru, en)", "default": "ru"}
                    },
                    "required": ["file_path"]
                },
                handler=self.transcribe
            ),
            SkillTool(
                name="voice_speak",
                description="Преобразовать текст в речь (TTS) и вернуть аудиофайл",
                parameters={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Текст для озвучивания"},
                        "voice": {"type": "string", "description": "Голос (default, male, female)", "default": "default"},
                        "speed": {"type": "number", "description": "Скорость речи (0.5-2.0)", "default": 1.0}
                    },
                    "required": ["text"]
                },
                handler=self.speak
            ),
            SkillTool(
                name="voice_list",
                description="Показать список транскрибаций",
                parameters={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Макс. количество", "default": 10}
                    }
                },
                handler=self.list_transcriptions
            )
        ]
    
    async def transcribe(self, file_path: str, language: str = "ru") -> Dict:
        """Транскрибировать аудиофайл в текст через z-ai SDK ASR"""
        try:
            import base64
            
            # Проверяем существование файла
            audio_path = Path(file_path)
            if not audio_path.exists():
                return {"error": f"Файл не найден: {file_path}"}
            
            # Читаем аудиофайл и кодируем в base64
            with open(audio_path, 'rb') as f:
                audio_data = f.read()
            
            audio_base64 = base64.b64encode(audio_data).decode('utf-8')
            
            # Используем z-ai-web-dev-sdk для ASR
            import sys
            sys.path.insert(0, '/home/z/my-project')
            
            from z_ai_sdk import ZAI
            
            zai = await ZAI.create()
            
            # Вызываем ASR
            result = await zai.asr.transcribe(
                audio=audio_base64,
                language=language
            )
            
            # Сохраняем результат
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            result_file = self.OUTPUT_DIR / f"transcription_{timestamp}.txt"
            
            transcription_text = result.text if hasattr(result, 'text') else str(result)
            
            with open(result_file, 'w', encoding='utf-8') as f:
                f.write(f"# Транскрибация {timestamp}\n")
                f.write(f"# Файл: {file_path}\n")
                f.write(f"# Язык: {language}\n\n")
                f.write(transcription_text)
            
            return {
                "success": True,
                "text": transcription_text,
                "language": language,
                "audio_file": str(audio_path),
                "result_file": str(result_file),
                "message": f"✅ Транскрибация完成: {len(transcription_text)} символов"
            }
            
        except ImportError as e:
            # Fallback: используем CLI команду
            try:
                # z-ai asr не имеет параметра языка, используем только -f
                result = subprocess.run(
                    ['z-ai', 'asr', '-f', file_path],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                
                if result.returncode == 0:
                    transcription = result.stdout.strip()
                    
                    # Сохраняем результат
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    result_file = self.OUTPUT_DIR / f"transcription_{timestamp}.txt"
                    
                    with open(result_file, 'w', encoding='utf-8') as f:
                        f.write(transcription)
                    
                    return {
                        "success": True,
                        "text": transcription,
                        "result_file": str(result_file),
                        "message": f"✅ Транскрибация完成: {len(transcription)} символов"
                    }
                else:
                    return {"error": f"ASR failed: {result.stderr}"}
                    
            except Exception as e2:
                return {"error": f"ASR error: {str(e2)}"}
                
        except Exception as e:
            return {"error": str(e)}
    
    async def speak(self, text: str, voice: str = "default", speed: float = 1.0) -> Dict:
        """Синтез речи через z-ai SDK TTS"""
        try:
            import sys
            sys.path.insert(0, '/home/z/my-project')
            
            from z_ai_sdk import ZAI
            
            zai = await ZAI.create()
            
            # Генерируем уникальное имя файла
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = self.OUTPUT_DIR / f"speech_{timestamp}.wav"
            
            # Вызываем TTS
            result = await zai.tts.synthesize(
                text=text,
                voice=voice,
                speed=speed
            )
            
            # Сохраняем аудио
            if hasattr(result, 'audio'):
                audio_data = result.audio
                if isinstance(audio_data, str):
                    # base64 encoded
                    audio_data = base64.b64decode(audio_data)
                
                with open(output_file, 'wb') as f:
                    f.write(audio_data)
                
                return {
                    "success": True,
                    "audio_file": str(output_file),
                    "text": text,
                    "voice": voice,
                    "message": f"✅ Аудио создано: {output_file.name}"
                }
            else:
                return {"error": "No audio data in response"}
                
        except ImportError:
            # Fallback: CLI
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_file = self.OUTPUT_DIR / f"speech_{timestamp}.wav"
                
                result = subprocess.run(
                    ['z-ai', 'tts', '-t', text, '-o', str(output_file), '-v', voice],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                
                if result.returncode == 0 and output_file.exists():
                    return {
                        "success": True,
                        "audio_file": str(output_file),
                        "text": text,
                        "message": f"✅ Аудио создано: {output_file.name}"
                    }
                else:
                    return {"error": f"TTS failed: {result.stderr}"}
                    
            except Exception as e2:
                return {"error": f"TTS error: {str(e2)}"}
                
        except Exception as e:
            return {"error": str(e)}
    
    def list_transcriptions(self, limit: int = 10) -> Dict:
        """Список транскрибаций"""
        try:
            files = []
            for f in self.OUTPUT_DIR.glob("transcription_*.txt"):
                stat = f.stat()
                files.append({
                    "filename": f.name,
                    "path": str(f),
                    "size": stat.st_size,
                    "created": datetime.fromtimestamp(stat.st_ctime).isoformat()
                })
            
            files.sort(key=lambda x: x["created"], reverse=True)
            
            return {
                "success": True,
                "transcriptions": files[:limit],
                "total": len(files)
            }
        except Exception as e:
            return {"error": str(e)}


# ============================================================
# SKILLS REGISTRY
# ============================================================

class SkillsRegistry:
    """Реестр всех навыков"""
    
    def __init__(self):
        self.skills: Dict[str, BaseSkill] = {}
        self._register_default_skills()
    
    def _register_default_skills(self):
        """Регистрация встроенных навыков"""
        default_skills = [
            FilesystemSkill(),
            TerminalSkill(),
            BrowserSkill(),
            MemorySkill(),
            CommunicationSkill(),
            ImageSkill(),
            DatabaseSkill(),
            AnalyticsSkill(),
            VoiceSkill()
        ]
        
        for skill in default_skills:
            self.skills[skill.name] = skill
            logger.info(f"Registered skill: {skill.name}")
    
    def get_skill(self, name: str) -> Optional[BaseSkill]:
        """Получить навык по имени"""
        return self.skills.get(name)
    
    def get_all_tools(self) -> List[Dict]:
        """Получить все инструменты всех навыков"""
        tools = []
        for skill in self.skills.values():
            tools.extend(skill.get_tools())
        return tools
    
    def get_tool_names(self) -> Dict[str, str]:
        """Получить маппинг инструмент -> навык"""
        mapping = {}
        for skill_name, skill in self.skills.items():
            for tool in skill.tools:
                mapping[tool.name] = skill_name
        return mapping
    
    async def execute_tool(self, tool_name: str, **kwargs) -> Any:
        """Выполнить инструмент"""
        mapping = self.get_tool_names()
        skill_name = mapping.get(tool_name)
        
        if not skill_name:
            return {"error": f"Tool {tool_name} not found"}
        
        skill = self.skills[skill_name]
        return await skill.execute(tool_name, **kwargs)
    
    def list_skills(self) -> List[Dict]:
        """Список всех навыков"""
        return [
            {
                "name": skill.name,
                "description": skill.description,
                "tools_count": len(skill.tools),
                "tools": [t.name for t in skill.tools]
            }
            for skill in self.skills.values()
        ]


# Глобальный реестр
skills_registry = SkillsRegistry()
