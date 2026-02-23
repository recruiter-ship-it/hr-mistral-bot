"""
HR Document Generator - Создание HR документов
Офферы, контракты, welcome-письма, scorecards и другие документы
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from string import Template

logger = logging.getLogger(__name__)


class DocumentTemplates:
    """Шаблоны HR документов"""
    
    OFFER_TEMPLATE = """
# ОФФЕР О ПРИНЯТИИ НА РАБОТУ

**Компания:** ${company_name}  
**Дата:** ${date}

---

## Уважаемый(ая) ${candidate_name}!

Мы рады предложить Вам должность **${position}** в команде ${company_name}.

### Условия предложения:

| Параметр | Значение |
|----------|----------|
| **Должность** | ${position} |
| **Отдел** | ${department} |
| **Тип занятости** | ${employment_type} |
| **Дата выхода** | ${start_date} |
| **Испытательный срок** | ${probation_period} |
| **Зарплата** | ${salary} ${currency} (${salary_frequency}) |

### Ваши обязанности:
${responsibilities}

### Социальный пакет:
${benefits}

---

Для принятия предложения, пожалуйста, подпишите и верните скан копию до ${offer_deadline}.

**С уважением,**  
${hr_name}  
HR Manager  
${company_name}  
${hr_email}
"""
    
    WELCOME_TEMPLATE = """
# Добро пожаловать в команду! 🎉

**Привет, ${candidate_name}!**

Поздравляем с присоединением к команде ${company_name}! Мы очень рады, что ты стал(а) частью нашей команды.

---

## 📅 Твой первый день

**Дата:** ${start_date}  
**Время:** ${start_time}  
**Адрес:** ${office_address}

В первый день тебя встретит ${buddy_name} — твой buddy, который поможет освоиться.

---

## 📋 Что взять с собой:
- Паспорт
- ИНН
- СНИЛС
- Диплом об образовании
- Трудовую книжку (если есть)

---

## 🗓️ План первой недели:

${first_week_plan}

---

## 📞 Контакты:

- **HR:** ${hr_name} (${hr_email})
- **Руководитель:** ${manager_name} (${manager_email})
- **Buddy:** ${buddy_name}

---

Если у тебя есть вопросы — не стесняйся писать! Мы всегда на связи.

Добро пожаловать! 🚀
"""
    
    REJECTION_TEMPLATE = """
# Уважаемый(ая) ${candidate_name}!

Благодарим Вас за интерес к вакансии **${position}** в компании ${company_name}.

Мы внимательно рассмотрели Вашу кандидатуру и получили большое количество откликов на эту позицию. К сожалению, на данном этапе мы не можем предложить Вам эту должность.

Это решение не означает, что Ваш профессиональный опыт и навыки не представляют ценности — просто в данный момент мы ищем кандидата с другим профилем.

---

**Мы хотели бы:**${keep_in_touch}

---

Мы желаем Вам успехов в поиске работы и надеемся, что наши пути ещё пересекутся!

С уважением,  
${hr_name}  
HR Team  
${company_name}
"""
    
    INTERVIEW_INVITE_TEMPLATE = """
# Приглашение на интервью

**Уважаемый(ая) ${candidate_name}!**

Благодарим за интерес к вакансии **${position}** в компании ${company_name}.

Мы хотели бы пригласить Вас на интервью.

---

## 📅 Детали интервью:

| Параметр | Значение |
|----------|----------|
| **Дата** | ${interview_date} |
| **Время** | ${interview_time} |
| **Формат** | ${interview_type} |
| **Длительность** | ${duration} минут |

${location_or_link}

---

## 👥 С Вами будут общаться:

${interviewers}

---

## 📋 Подготовка:

${preparation_tips}

---

Пожалуйста, подтвердите своё участие ответным письмом.

Если указанное время неудобно, сообщите нам, и мы подберём другое.

С уважением,  
${hr_name}  
${company_name}
"""
    
    SCORECARD_TEMPLATE = """
# КАРТА ОЦЕНКИ КАНДИДАТА

**Кандидат:** ${candidate_name}  
**Позиция:** ${position}  
**Интервьюер:** ${interviewer}  
**Дата:** ${date}

---

## 📊 Оценка по компетенциям

| Компетенция | Оценка (1-5) | Комментарий |
|-------------|--------------|-------------|
${competency_scores}

**Средняя оценка:** ${average_score}/5

---

## 💪 Сильные стороны:
${strengths}

## ⚠️ Зоны развития:
${weaknesses}

## 📝 Дополнительные комментарии:
${comments}

---

## 🎯 Рекомендация:

**[ ] Нанять**  
**[ ] Нанять с условиями** (указать какими: _____________)  
**[ ] Отклонить**  
**[ ] Нужно ещё одно интервью**

---

**Подпись интервьюера:** ________________  
**Дата:** ________________
"""
    
    FOLLOW_UP_TEMPLATE = """
# Follow-up: ${subject}

**Кому:** ${candidate_name}  
**Дата:** ${date}

---

${greeting}

${main_content}

---

${call_to_action}

С уважением,  
${hr_name}  
${company_name}
"""


class DocumentGenerator:
    """Генератор HR документов"""
    
    def __init__(self, company_name: str = "Компания"):
        self.company_name = company_name
        self.templates = DocumentTemplates()
    
    def generate_offer(self, params: Dict) -> str:
        """Генерация оффера"""
        defaults = {
            "company_name": self.company_name,
            "date": datetime.now().strftime("%d.%m.%Y"),
            "probation_period": "3 месяца",
            "employment_type": "Полная занятость",
            "currency": "USD",
            "salary_frequency": "в месяц",
            "benefits": "- ДМС после испытательного срока\n- Гибкий график\n- Оплата обучения",
            "offer_deadline": (datetime.now() + timedelta(days=3)).strftime("%d.%m.%Y"),
            "hr_email": "hr@company.com"
        }
        
        data = {**defaults, **params}
        
        return Template(self.templates.OFFER_TEMPLATE).safe_substitute(data)
    
    def generate_welcome(self, params: Dict) -> str:
        """Генерация welcome-письма"""
        defaults = {
            "company_name": self.company_name,
            "start_time": "10:00",
            "office_address": "Офис компании (адрес будет уточнён)",
            "first_week_plan": """
**День 1:** Знакомство с командой, оформление документов, настройка рабочего места
**День 2:** Обучение продуктам и процессам компании
**День 3:** Знакомство с отделами и ключевыми людьми
**День 4:** Обучение инструментам и системам
**День 5:** Постановка первых задач, 1-on-1 с руководителем
"""
        }
        
        data = {**defaults, **params}
        
        return Template(self.templates.WELCOME_TEMPLATE).safe_substitute(data)
    
    def generate_rejection(self, params: Dict) -> str:
        """Генерация письма с отказом"""
        defaults = {
            "company_name": self.company_name,
            "keep_in_touch": "- Сохранить Ваше резюме в нашей базе для будущих вакансий"
        }
        
        data = {**defaults, **params}
        
        return Template(self.templates.REJECTION_TEMPLATE).safe_substitute(data)
    
    def generate_interview_invite(self, params: Dict) -> str:
        """Генерация приглашения на интервью"""
        defaults = {
            "company_name": self.company_name,
            "interview_type": "Онлайн (Zoom)",
            "duration": "60",
            "interviewers": "- Иван Иванов, Hiring Manager\n- Мария Петрова, Team Lead",
            "preparation_tips": "- Изучите наш сайт и продукты\n- Подготовьте вопросы о команде и задачах",
            "location_or_link": "🔗 **Ссылка на Zoom:** будет отправлена дополнительно"
        }
        
        data = {**defaults, **params}
        
        return Template(self.templates.INTERVIEW_INVITE_TEMPLATE).safe_substitute(data)
    
    def generate_scorecard(self, params: Dict) -> str:
        """Генерация карты оценки кандидата"""
        defaults = {
            "date": datetime.now().strftime("%d.%m.%Y"),
            "competency_scores": self._generate_competency_table(params.get("competencies", {})),
            "average_score": self._calculate_average(params.get("competencies", {}))
        }
        
        data = {**defaults, **params}
        
        return Template(self.templates.SCORECARD_TEMPLATE).safe_substitute(data)
    
    def generate_follow_up(self, params: Dict) -> str:
        """Генерация follow-up письма"""
        defaults = {
            "company_name": self.company_name,
            "date": datetime.now().strftime("%d.%m.%Y")
        }
        
        data = {**defaults, **params}
        
        return Template(self.templates.FOLLOW_UP_TEMPLATE).safe_substitute(data)
    
    def _generate_competency_table(self, competencies: Dict) -> str:
        """Генерация таблицы компетенций для scorecard"""
        if not competencies:
            return "| - | - | - |"
        
        rows = []
        for comp, data in competencies.items():
            score = data.get("score", "-")
            comment = data.get("comment", "")
            rows.append(f"| {comp} | {score} | {comment} |")
        
        return "\n".join(rows)
    
    def _calculate_average(self, competencies: Dict) -> str:
        """Расчёт средней оценки"""
        if not competencies:
            return "-"
        
        scores = [d.get("score", 0) for d in competencies.values() if isinstance(d, dict)]
        if not scores:
            return "-"
        
        return f"{sum(scores) / len(scores):.1f}"


class GoogleDocsManager:
    """Менеджер для создания документов в Google Docs"""
    
    def __init__(self):
        self.docs_service = None
        self.drive_service = None
    
    def _get_services(self):
        """Получение сервисов Google Docs и Drive"""
        if self.docs_service:
            return True
        
        try:
            import base64
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
            
            creds_b64 = os.getenv("GOOGLE_SERVICE_ACCOUNT_B64")
            if not creds_b64:
                logger.warning("Google Service Account not configured")
                return False
            
            creds_json = base64.b64decode(creds_b64).decode('utf-8')
            creds_dict = json.loads(creds_json)
            
            if 'private_key' in creds_dict:
                creds_dict['private_key'] = creds_dict['private_key'].replace('\\n', '\n')
            
            credentials = service_account.Credentials.from_service_account_info(
                creds_dict,
                scopes=[
                    'https://www.googleapis.com/auth/documents',
                    'https://www.googleapis.com/auth/drive.file'
                ]
            )
            
            self.docs_service = build('docs', 'v1', credentials=credentials)
            self.drive_service = build('drive', 'v3', credentials=credentials)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Google Docs services: {e}")
            return False
    
    def create_document(self, title: str, content: str, folder_id: str = None) -> Dict:
        """
        Создание документа в Google Docs
        
        Args:
            title: Название документа
            content: Содержимое документа (Markdown)
            folder_id: ID папки для сохранения (опционально)
        
        Returns:
            Dict с результатом: success, document_id, url или error
        """
        if not self._get_services():
            return {
                "success": False,
                "error": "Google Docs не настроен",
                "content": content  # Возвращаем контент для локального сохранения
            }
        
        try:
            # Создаём документ
            doc = self.docs_service.documents().create(
                body={"title": title}
            ).execute()
            
            doc_id = doc["documentId"]
            
            # Конвертируем Markdown в Google Docs формат
            requests = self._markdown_to_requests(content)
            
            if requests:
                self.docs_service.documents().batchUpdate(
                    documentId=doc_id,
                    body={"requests": requests}
                ).execute()
            
            # Перемещаем в папку если указана
            if folder_id:
                self.drive_service.files().update(
                    fileId=doc_id,
                    addParents=folder_id,
                    fields="id, parents"
                ).execute()
            
            # Даём доступ по ссылке
            self.drive_service.permissions().create(
                fileId=doc_id,
                body={
                    "type": "anyoneWithLink",
                    "role": "writer"
                }
            ).execute()
            
            return {
                "success": True,
                "document_id": doc_id,
                "url": f"https://docs.google.com/document/d/{doc_id}/edit",
                "title": title
            }
            
        except Exception as e:
            logger.error(f"Failed to create document: {e}")
            return {
                "success": False,
                "error": str(e),
                "content": content
            }
    
    def _markdown_to_requests(self, markdown: str) -> List[Dict]:
        """Конвертация Markdown в запросы Google Docs API"""
        requests = []
        lines = markdown.split('\n')
        
        # Вставляем текст
        text_content = markdown
        requests.append({
            "insertText": {
                "location": {"index": 1},
                "text": text_content
            }
        })
        
        # Форматирование заголовков
        for i, line in enumerate(lines):
            if line.startswith('# '):
                # H1
                start_idx = sum(len(l) + 1 for l in lines[:i]) + 1
                end_idx = start_idx + len(line)
                requests.append({
                    "updateParagraphStyle": {
                        "range": {"startIndex": start_idx, "endIndex": end_idx},
                        "paragraphStyle": {"namedStyleType": "HEADING_1"},
                        "fields": "namedStyleType"
                    }
                })
            elif line.startswith('## '):
                # H2
                start_idx = sum(len(l) + 1 for l in lines[:i]) + 1
                end_idx = start_idx + len(line)
                requests.append({
                    "updateParagraphStyle": {
                        "range": {"startIndex": start_idx, "endIndex": end_idx},
                        "paragraphStyle": {"namedStyleType": "HEADING_2"},
                        "fields": "namedStyleType"
                    }
                })
        
        return requests


# Глобальный экземпляр генератора документов
doc_generator = DocumentGenerator()
google_docs = GoogleDocsManager()


# Функции для регистрации в агенте
def create_offer_document(candidate_name: str, position: str, salary: str,
                          start_date: str, **kwargs) -> Dict:
    """Создание оффера"""
    content = doc_generator.generate_offer({
        "candidate_name": candidate_name,
        "position": position,
        "salary": salary,
        "start_date": start_date,
        **kwargs
    })
    
    title = f"Оффер - {candidate_name} - {position}"
    
    result = google_docs.create_document(title, content)
    
    if result["success"]:
        return {
            "success": True,
            "message": f"✅ Оффер создан для {candidate_name}",
            "url": result["url"],
            "document_id": result["document_id"]
        }
    else:
        return {
            "success": False,
            "message": f"⚠️ Оффер не создан в Google Docs, но контент готов",
            "content": content
        }


def create_welcome_document(candidate_name: str, position: str, 
                            start_date: str, **kwargs) -> Dict:
    """Создание welcome-письма"""
    content = doc_generator.generate_welcome({
        "candidate_name": candidate_name,
        "position": position,
        "start_date": start_date,
        **kwargs
    })
    
    title = f"Welcome - {candidate_name}"
    
    result = google_docs.create_document(title, content)
    
    if result["success"]:
        return {
            "success": True,
            "message": f"✅ Welcome-документ создан для {candidate_name}",
            "url": result["url"]
        }
    else:
        return {
            "success": False,
            "content": content
        }


def create_scorecard_document(candidate_name: str, position: str,
                              interviewer: str, competencies: Dict,
                              **kwargs) -> Dict:
    """Создание карты оценки"""
    content = doc_generator.generate_scorecard({
        "candidate_name": candidate_name,
        "position": position,
        "interviewer": interviewer,
        "competencies": competencies,
        **kwargs
    })
    
    title = f"Scorecard - {candidate_name} - {position}"
    
    result = google_docs.create_document(title, content)
    
    if result["success"]:
        return {
            "success": True,
            "message": f"✅ Scorecard создан для {candidate_name}",
            "url": result["url"]
        }
    else:
        return {
            "success": False,
            "content": content
        }


def create_rejection_letter(candidate_name: str, position: str, 
                           **kwargs) -> Dict:
    """Создание письма с отказом"""
    content = doc_generator.generate_rejection({
        "candidate_name": candidate_name,
        "position": position,
        **kwargs
    })
    
    return {
        "success": True,
        "message": f"✅ Письмо с отказом готово для {candidate_name}",
        "content": content
    }


def create_interview_invite(candidate_name: str, position: str,
                           interview_date: str, interview_time: str,
                           **kwargs) -> Dict:
    """Создание приглашения на интервью"""
    content = doc_generator.generate_interview_invite({
        "candidate_name": candidate_name,
        "position": position,
        "interview_date": interview_date,
        "interview_time": interview_time,
        **kwargs
    })
    
    return {
        "success": True,
        "message": f"✅ Приглашение на интервью готово для {candidate_name}",
        "content": content
    }
