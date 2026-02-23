---
name: memory
description: "Персистентная память агента: хранение и поиск информации между сессиями. Использовать когда: (1) нужно сохранить важную информацию, (2) вспомнить ранее сохранённую информацию, (3) посмотреть все записи."
metadata:
  tools:
    - memory_remember
    - memory_recall
    - memory_forget
    - memory_list
    - memory_clear
---

# Memory Skill

Навык для работы с долгосрочной памятью агента.

## Когда использовать

✅ **ИСПОЛЬЗОВАТЬ когда:**

- Нужно сохранить важную информацию для будущего
- Вспомнить что-то из предыдущих разговоров
- Посмотреть все сохранённые записи

## Инструменты

### memory_remember
Сохранить информацию в память.
```json
{"key": "user_preference", "value": "User prefers dark mode", "category": "preferences"}
```

### memory_recall
Найти информацию в памяти.
```json
{"query": "preference", "category": "preferences", "limit": 10}
```

### memory_list
Показать все записи.
```json
{"category": "preferences", "limit": 20}
```

### memory_forget
Удалить запись.
```json
{"key": "user_preference"}
```
