"""Тесты моделей раздела «Траты»."""
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.utils import timezone

from budget.models import Category

from .models import Transaction
from .queries import transactions_for_month, transactions_for_period

class TransactionTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Продукты")

    def test_default_date_is_today(self):
        item = Transaction.objects.create(category=self.category, amount=Decimal("100"))
        self.assertEqual(item.date, timezone.localdate())

    def test_non_positive_amount_is_rejected(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Transaction.objects.create(category=self.category, amount=Decimal("0"))

    def test_amount_validator_rejects_non_positive(self):
        # Валидатор ловит неверную сумму в формах (админка, правка), а не только в БД.
        for amount in [Decimal("0"), Decimal("-5")]:
            with self.subTest(amount=amount):
                item = Transaction(
                    category=self.category, amount=amount, date=date(2026, 9, 1)
                )
                with self.assertRaises(ValidationError) as ctx:
                    item.full_clean()
                self.assertIn("amount", ctx.exception.message_dict)

    def test_date_validator_rejects_out_of_range(self):
        for value in [date(1800, 1, 1), date(2200, 1, 1)]:
            with self.subTest(value=value):
                item = Transaction(
                    category=self.category, amount=Decimal("100"), date=value
                )
                with self.assertRaises(ValidationError) as ctx:
                    item.full_clean()
                self.assertIn("date", ctx.exception.message_dict)

    def test_for_month_filters_by_calendar_month(self):
        Transaction.objects.create(
            category=self.category, amount=Decimal("100"), date=date(2026, 9, 30)
        )
        Transaction.objects.create(
            category=self.category, amount=Decimal("200"), date=date(2026, 10, 1)
        )
        Transaction.objects.create(
            category=self.category, amount=Decimal("300"), date=date(2026, 10, 31)
        )
        self.assertEqual(transactions_for_month(2026, 10).count(), 2)

    def test_for_period(self):
        Transaction.objects.create(
            category=self.category, amount=Decimal("100"), date=date(2026, 10, 1)
        )
        Transaction.objects.create(
            category=self.category, amount=Decimal("200"), date=date(2026, 10, 15)
        )
        period = transactions_for_period(date(2026, 10, 2), date(2026, 10, 20))
        self.assertEqual(period.count(), 1)

    def test_category_with_history_is_protected(self):
        Transaction.objects.create(category=self.category, amount=Decimal("100"))
        with self.assertRaises(ProtectedError):
            self.category.delete()
