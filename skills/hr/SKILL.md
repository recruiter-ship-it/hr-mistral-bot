---
name: hr
description: "HR инструменты: создание офферов, welcome-писем, приглашений на интервью. Использовать когда: (1) нужно создать оффер кандидату, (2) создать welcome-документ, (3) создать приглашение на интервью, (4) создать письмо с отказом."
metadata:
  tools:
    - create_offer
    - create_welcome_letter
    - create_rejection_letter
    - create_interview_invite
---

# HR Skill

Навык для работы с HR документами.

## Когда использовать

✅ **ИСПОЛЬЗОВАТЬ когда:**

- Нужно создать оффер о приёме на работу
- Создать welcome-письмо для нового сотрудника
- Создать приглашение на интервью
- Создать письмо с отказом кандидату

## Инструменты

### create_offer
Создать оффер о приёме на работу.
```json
{
  "candidate_name": "Иван Петров",
  "position": "Python Developer",
  "salary": "3000 USDT",
  "start_date": "01.03.2025",
  "department": "Development"
}
```

### create_welcome_letter
Создать welcome-письмо.
```json
{
  "employee_name": "Иван Петров",
  "position": "Python Developer",
  "start_date": "01.03.2025",
  "start_time": "10:00",
  "buddy": "Мария",
  "manager": "Алексей"
}
```

### create_interview_invite
Создать приглашение на интервью.
```json
{
  "candidate_name": "Иван Петров",
  "position": "Python Developer",
  "interview_date": "25.02.2025",
  "interview_time": "14:00",
  "duration": 60,
  "interview_type": "онлайн"
}
```
