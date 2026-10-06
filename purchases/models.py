"""Модели планов покупок: цели, взносы в них и прогресс накопления."""
from decimal import Decimal

from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone


class PlannedPurchase(models.Model):
    """Цель: покупка, на которую копим."""

    class Status(models.TextChoices):
        WANTED = "wanted", "хочу"
        SAVING = "saving", "коплю"
        BOUGHT = "bought", "куплено"

    title = models.CharField("что покупаем", max_length=200)
    amount = models.DecimalField(
        "стоимость, ₽",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
    )
    priority = models.PositiveSmallIntegerField("приоритет", default=0)
    status = models.CharField(
        "статус",
        max_length=10,
        choices=Status.choices,
        default=Status.WANTED,
    )
    created_at = models.DateTimeField("создано", auto_now_add=True)
    bought_at = models.DateField("куплено", null=True, blank=True)

    class Meta:
        verbose_name = "план покупки"
        verbose_name_plural = "планы покупок"
        ordering = ["priority", "-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gte=0),
                name="purchase_amount_non_negative",
            ),
        ]

    def __str__(self) -> str:
        return self.title

    @property
    def contributed(self) -> Decimal:
        """Сколько уже накоплено на цель.

        Если queryset аннотирован `contributed_total` (так делает обзорная
        страница), берём готовое значение — иначе считаем запросом.
        """
        annotated = getattr(self, "contributed_total", None)
        if annotated is not None:
            return annotated
        total = PurchaseContribution.objects.filter(purchase=self).aggregate(
            total=Sum("amount")
        )["total"]
        return total if total is not None else Decimal("0")

    @property
    def remaining(self) -> Decimal:
        """Сколько осталось накопить."""
        return max(self.amount - self.contributed, Decimal("0"))

    @property
    def progress_percent(self) -> int:
        """Прогресс накопления, % (0–100)."""
        if self.amount <= 0:
            return 0
        return int(min(self.contributed * 100 / self.amount, Decimal("100")))


class PurchaseContribution(models.Model):
    """Взнос в цель (накопление)."""

    purchase = models.ForeignKey(
        PlannedPurchase,
        on_delete=models.CASCADE,
        related_name="contributions",
        verbose_name="цель",
    )
    amount = models.DecimalField("сумма, ₽", max_digits=12, decimal_places=2)
    date = models.DateField("дата", default=timezone.localdate)
    comment = models.CharField("комментарий", max_length=200, blank=True)
    created_at = models.DateTimeField("создано", auto_now_add=True)

    class Meta:
        verbose_name = "взнос"
        verbose_name_plural = "взносы"
        ordering = ["-date", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="contribution_amount_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.purchase}: {self.amount} ₽"
