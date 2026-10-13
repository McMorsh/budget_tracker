"""Помощники для JSON-эндпоинтов, общие для приложений."""
import json

from django import forms
from django.http import HttpRequest


def json_payload(request: HttpRequest) -> dict | None:
    """Разбирает JSON-тело запроса.

    Args:
        request: Запрос с телом в формате JSON.

    Returns:
        Словарь из тела или None, если это не JSON-объект.
    """
    try:
        payload = json.loads(request.body)
    except (TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def first_error(
    form: forms.BaseForm, fallback: str = "Проверьте данные"
) -> tuple[str, str]:
    """Находит первую ошибку формы для JSON-ответа.

    Args:
        form: Невалидная форма.
        fallback: Сообщение, если ошибок у формы нет.

    Returns:
        Имя первого проблемного поля и текст его первой ошибки.
    """
    for name, errors in form.errors.items():
        if errors:
            return name, str(errors[0])
    return "", fallback
