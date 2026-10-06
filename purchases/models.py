"""Модели планов покупок: цели, взносы в них и прогресс накопления."""
from datetime import date
from decimal import Decimal
from typing import Any

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone

from budget.utils import MAX_YEAR, MIN_YEAR


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
        # Валидатор дублирует CheckConstraint ниже, но срабатывает в формах
        # (добавление и инлайн-правка), а не только на уровне базы.
        validators=[MinValueValidator(Decimal("0"))],
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
        # Большее число важнее: приоритетные цели выше в списке.
        ordering = ["-priority", "-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gte=0),
                name="purchase_amount_non_negative",
            ),
        ]

    def __str__(self) -> str:
        return self.title

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Держит дату покупки в согласии со статусом.

        Куплено — проставляем дату (если ещё нет), любой другой статус —
        снимаем: поле не редактируется вручную, лишних полей в формах нет.
        """
        if self.status == self.Status.BOUGHT:
            if self.bought_at is None:
                self.bought_at = timezone.localdate()
        else:
            self.bought_at = None
        super().save(*args, **kwargs)

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
        """Прогресс накопления, % (0–100).

        Дробные проценты отбрасываются: полоса должна доходить до 100 %
        только при полном накоплении.
        """
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
    amount = models.DecimalField(
        "сумма, ₽",
        max_digits=12,
        decimal_places=2,
        # Валидатор дублирует CheckConstraint ниже, но срабатывает в формах
        # (включая инлайн-правку и админку), а не только на уровне базы.
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    date = models.DateField(
        "дата",
        default=timezone.localdate,
        # Те же границы, что у трат: дата вне диапазона ломала бы страницы.
        validators=[
            MinValueValidator(date(MIN_YEAR, 1, 1)),
            MaxValueValidator(date(MAX_YEAR, 12, 31)),
        ],
    )
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
