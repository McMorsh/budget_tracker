"""Общие помощники для разделов, которые ходят по месяцам.

Используются «Бюджетом» и «Тратами»: оба экрана листают месяцы и подписаны
названием месяца по-русски.
"""
from datetime import date

from django.http import Http404
from django.utils.formats import date_format

# Границы применимости сайта. Защищают от 500 на крайних годах: ссылки
# «назад/вперёд» и даты трат не должны уводить за пределы дат Python.
MIN_YEAR = 1900
MAX_YEAR = 2100


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    """Соседний месяц (delta = ±1, допускается больше)."""
    month += delta
    while month < 1:
        month += 12
        year -= 1
    while month > 12:
        month -= 12
        year += 1
    return year, month


def month_title(year: int, month: int) -> str:
    """Название месяца по-русски, например «октябрь 2026»."""
    return date_format(date(year, month, 1), "F Y")


def check_month(year: int, month: int) -> None:
    """Проверяет границы экрана месяца; вне диапазона — Http404."""
    if not 1 <= month <= 12 or not MIN_YEAR <= year <= MAX_YEAR:
        raise Http404("Месяца с таким номером не бывает")
