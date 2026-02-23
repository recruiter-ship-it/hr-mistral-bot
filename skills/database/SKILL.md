---
name: database
description: Работа с базами данных - SQL запросы, SQLite, экспорт
version: 1.0.0
author: HR Bot Team
tools:
  - name: db_sqlite_query
    description: Выполнить SQL запрос к SQLite
  - name: db_sqlite_create_table
    description: Создать таблицу в SQLite
  - name: db_list_tables
    description: Показать таблицы в БД
  - name: db_export_csv
    description: Экспортировать таблицу в CSV
gating:
  - trigger: "sql запрос|база данных|sqlite"
  - trigger: "создай таблицу|добавь в базу"
  - trigger: "экспортируй|выгрузи в csv"
  - trigger: "покажи таблицы|структура базы"
---

# Database Skill

Ты - эксперт по работе с базами данных. Ты выполняешь SQL запросы и управляешь таблицами.

## Когда использовать этот навык

Используй этот навык когда пользователь просит:
- Выполнить SQL запрос
- Создать или изменить таблицу
- Экспортировать данные
- Посмотреть структуру базы

## Инструменты

### db_sqlite_query

Выполняет SQL запрос.

**Параметры:**
- `db_path` (обязательно): Путь к БД
- `query` (обязательно): SQL запрос
- `params`: Параметры запроса

**Пример:**
```
db_sqlite_query(
  db_path="data.db",
  query="SELECT * FROM candidates WHERE status = ?",
  params=["new"]
)
```

### db_sqlite_create_table

Создаёт таблицу.

**Параметры:**
- `db_path` (обязательно): Путь к БД
- `table_name` (обязательно): Имя таблицы
- `columns` (обязательно): Словарь {имя: тип}

**Пример:**
```
db_sqlite_create_table(
  db_path="hr.db",
  table_name="interviews",
  columns={
    "id": "INTEGER PRIMARY KEY",
    "candidate": "TEXT",
    "date": "TEXT",
    "status": "TEXT"
  }
)
```

### db_list_tables

Показывает таблицы в БД.

**Параметры:**
- `db_path` (обязательно): Путь к БД

### db_export_csv

Экспортирует таблицу в CSV.

**Параметры:**
- `db_path` (обязательно): Путь к БД
- `table_name` (обязательно): Имя таблицы
- `output_path` (обязательно): Путь к CSV файлу

## Типы данных SQLite

- `INTEGER` - целое число
- `TEXT` - текст
- `REAL` - число с плавающей точкой
- `BLOB` - бинарные данные
- `PRIMARY KEY` - первичный ключ
- `NOT NULL` - обязательно

## Примеры

**Пользователь:** "Покажи всех кандидатов из базы"
**Действие:** db_sqlite_query(db_path="hr.db", query="SELECT * FROM candidates")

**Пользователь:** "Создай таблицу для интервью"
**Действие:** db_sqlite_create_table(...)
