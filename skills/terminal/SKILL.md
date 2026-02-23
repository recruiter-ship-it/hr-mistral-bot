---
name: terminal
description: "Выполнение терминальных команд (shell commands). Использовать когда: (1) нужно запустить программу, (2) выполнить скрипт, (3) установить пакет, (4) git операции. НЕ использовать для: работы с файлами (используй filesystem), веб-операций (используй browser)."
metadata:
  tools:
    - terminal_execute
    - terminal_run_script
    - terminal_install_package
    - terminal_git_status
    - terminal_git_commit
---

# Terminal Skill

Навык для выполнения терминальных команд в безопасной песочнице.

## Когда использовать

✅ **ИСПОЛЬЗОВАТЬ когда:**

- Нужно выполнить shell команду
- Запустить Python или Bash скрипт
- Установить Python пакет
- Проверить статус git репозитория
- Сделать git commit

## Когда НЕ использовать

❌ **НЕ ИСПОЛЬЗОВАТЬ когда:**

- Нужно просто прочитать файл → используй `fs_read_file`
- Нужно создать файл → используй `fs_write_file`
- Нужно найти информацию в интернете → используй `browser_search`

## Безопасность

Навык использует whitelist разрешённых команд и блокирует опасные операции:
- `rm -rf /` - заблокировано
- `sudo` - заблокировано
- `shutdown` - заблокировано

## Инструменты

### terminal_execute
Выполнить shell команду.
```json
{"command": "ls -la", "timeout": 30}
```

### terminal_run_script
Выполнить скрипт.
```json
{"script": "print('Hello')", "language": "python"}
```
