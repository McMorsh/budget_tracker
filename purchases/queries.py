"""Выборки целей с посчитанными накоплениями.

Аннотация `contributed_total` — то же имя, что читает свойство
`PlannedPurchase.contributed`: с ней список целей считается одним запросом
без N+1.
"""
from decimal import Decimal

from django.db.models import DecimalField, QuerySet, Sum, Value
from django.db.models.functions import Coalesce

from .models import PlannedPurchase


def goals_with_contributed() -> QuerySet[PlannedPurchase]:
    """Цели с аннотацией `contributed_total` — суммой взносов.

    Порядок задаётся явно: у запроса с группировкой (SUM по взносам)
    Django не применяет `Meta.ordering`.
    """
    return (
        PlannedPurchase.objects.annotate(
            contributed_total=Coalesce(
                Sum("contributions__amount"),
                Value(Decimal("0")),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        ).order_by("-priority", "-created_at")
    )
