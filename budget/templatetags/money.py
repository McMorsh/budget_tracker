"""Шаблонные фильтры для денег."""
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django import template
from django.utils.formats import number_format

register = template.Library()

DASH = "-"


@register.filter
def rubles(value, decimals=0):
    """Форматирует сумму по-русски: 85000 -> "85 000 ₽", 12750.5 -> "12 750,50 ₽".

    Второй аргумент - число знаков после запятой (по умолчанию 0).
    Округление - половина вверх, как в `budget.models.money`, чтобы
    отображение не расходилось с расчётами.
    """
    try:
        decimal_pos = int(decimals)
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return DASH
    quant = Decimal(1).scaleb(-decimal_pos)
    number = number.quantize(quant, rounding=ROUND_HALF_UP)
    formatted = number_format(number, decimal_pos=decimal_pos, force_grouping=True)
    return f"{formatted} ₽"
