"""Тесты моделей и экранов раздела «Траты»."""
import json
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from budget.models import Allocation, BudgetMonth, Category
from budget.utils import month_title, shift_month

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


class TransactionViewsTests(TestCase):
    """Ввод, список, инлайн-правка и удаление трат (Фаза 5)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="owner", password="test-pass-123"
        )
        cls.category = Category.objects.create(name="Продукты")

    def setUp(self):
        self.client.force_login(self.user)

    def month_url(self, year: int = 2026, month: int = 9) -> str:
        return reverse("expenses:month", args=[year, month])

    def post_json(self, url: str, payload: dict):
        return self.client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )

    # --- доступ ---

    def test_section_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("expenses:index"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(reverse("login")))

    def test_edit_and_delete_require_login(self):
        item = Transaction.objects.create(category=self.category, amount=Decimal("100"))
        self.client.logout()
        for url in [
            reverse("expenses:transaction_update", args=[item.pk]),
            reverse("expenses:transaction_delete", args=[item.pk]),
        ]:
            with self.subTest(url=url):
                response = self.client.post(url)
                self.assertEqual(response.status_code, 302)

    # --- список ---

    def test_bad_month_number_is_404(self):
        for month in [0, 13]:
            with self.subTest(month=month):
                response = self.client.get(
                    reverse("expenses:month", args=[2026, month])
                )
                self.assertEqual(response.status_code, 404)

    def test_out_of_range_year_is_404(self):
        # Крайние годы увели бы ссылки «назад/вперёд» за пределы дат Python — 500.
        for year, month in [(0, 1), (1899, 12), (2101, 1), (10000, 1)]:
            with self.subTest(year=year):
                response = self.client.get(
                    reverse("expenses:month", args=[year, month])
                )
                self.assertEqual(response.status_code, 404)

    def test_year_boundaries_render(self):
        for year, month in [(1900, 1), (2100, 12)]:
            with self.subTest(year=year):
                response = self.client.get(
                    reverse("expenses:month", args=[year, month])
                )
                self.assertEqual(response.status_code, 200)

    def test_month_page_shows_only_its_transactions(self):
        Transaction.objects.create(
            category=self.category,
            amount=Decimal("100"),
            date=date(2026, 9, 5),
            comment="Лента",
        )
        Transaction.objects.create(
            category=self.category,
            amount=Decimal("200"),
            date=date(2026, 10, 5),
            comment="Магнит",
        )

        response = self.client.get(self.month_url())
        self.assertContains(response, month_title(2026, 9))
        self.assertContains(response, "Лента")
        self.assertNotContains(response, "Магнит")

    def test_month_page_shows_total_and_count(self):
        Transaction.objects.create(
            category=self.category, amount=Decimal("1234.50"), date=date(2026, 9, 10)
        )
        Transaction.objects.create(
            category=self.category, amount=Decimal("765.50"), date=date(2026, 9, 11)
        )

        response = self.client.get(self.month_url())
        self.assertContains(response, "2\xa0000,00 ₽")
        self.assertContains(response, 'id="month-count">2<')

    def test_index_opens_current_month(self):
        response = self.client.get(reverse("expenses:index"))
        today = timezone.localdate()
        self.assertContains(response, month_title(today.year, today.month))

    # --- дата по умолчанию ---

    def test_default_date_in_current_month_is_today(self):
        today = timezone.localdate()
        response = self.client.get(reverse("expenses:index"))
        self.assertContains(response, f'value="{today:%Y-%m-%d}"')

    def test_default_date_in_past_month_is_last_day(self):
        response = self.client.get(self.month_url(2020, 2))
        self.assertContains(response, 'value="2020-02-29"')

    def test_default_date_in_future_month_is_first_day(self):
        today = timezone.localdate()
        year, month = shift_month(today.year, today.month, 2)
        response = self.client.get(self.month_url(year, month))
        self.assertContains(response, f'value="{year}-{month:02d}-01"')

    @patch("expenses.views.timezone.localdate", return_value=date(2026, 1, 5))
    def test_default_date_across_new_year(self, _localdate):
        response = self.client.get(self.month_url(2025, 12))
        self.assertContains(response, 'value="2025-12-31"')
        response = self.client.get(self.month_url(2026, 2))
        self.assertContains(response, 'value="2026-02-01"')

    # --- добавление ---

    def test_add_transaction(self):
        response = self.client.post(
            self.month_url(),
            {
                "date": "2026-09-10",
                "category": self.category.pk,
                "amount": "500.00",
                "comment": "Пятёрочка",
            },
        )
        self.assertRedirects(response, self.month_url())
        item = Transaction.objects.get()
        self.assertEqual(item.amount, Decimal("500.00"))
        self.assertEqual(item.comment, "Пятёрочка")
        self.assertEqual(item.date, date(2026, 9, 10))

    def test_add_transaction_redirects_to_month_of_date(self):
        response = self.client.post(
            self.month_url(),
            {
                "date": "2026-08-15",
                "category": self.category.pk,
                "amount": "100",
                "comment": "",
            },
        )
        self.assertRedirects(response, self.month_url(2026, 8))

    def test_add_rejects_non_positive_amount(self):
        expected_errors = {
            "0": "0.01",
            "-5": "0.01",
            "abc": "число",
            "": "Обязательное",
        }
        for amount, expected in expected_errors.items():
            with self.subTest(amount=amount):
                response = self.client.post(
                    self.month_url(),
                    {
                        "date": "2026-09-10",
                        "category": self.category.pk,
                        "amount": amount,
                        "comment": "",
                    },
                )
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, expected)
        self.assertFalse(Transaction.objects.exists())

    def test_add_rejects_amount_above_max_digits(self):
        response = self.client.post(
            self.month_url(),
            {
                "date": "2026-09-10",
                "category": self.category.pk,
                "amount": "99999999999.99",
                "comment": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Transaction.objects.exists())

    def test_add_accepts_max_allowed_amount(self):
        response = self.client.post(
            self.month_url(),
            {
                "date": "2026-09-10",
                "category": self.category.pk,
                "amount": "9999999999.99",
                "comment": "",
            },
        )
        self.assertRedirects(response, self.month_url())

    def test_add_rejects_impossible_date(self):
        response = self.client.post(
            self.month_url(),
            {
                "date": "2026-02-30",
                "category": self.category.pk,
                "amount": "100",
                "comment": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Transaction.objects.exists())

    def test_add_rejects_date_out_of_range(self):
        for value in ["1800-01-01", "2200-01-01"]:
            with self.subTest(value=value):
                response = self.client.post(
                    self.month_url(),
                    {
                        "date": value,
                        "category": self.category.pk,
                        "amount": "100",
                        "comment": "",
                    },
                )
                self.assertEqual(response.status_code, 200)
        self.assertFalse(Transaction.objects.exists())

    def test_add_accepts_comment_of_max_length(self):
        response = self.client.post(
            self.month_url(),
            {
                "date": "2026-09-10",
                "category": self.category.pk,
                "amount": "100",
                "comment": "x" * 200,
            },
        )
        self.assertRedirects(response, self.month_url())

    def test_add_rejects_unknown_category(self):
        response = self.client.post(
            self.month_url(),
            {"date": "2026-09-10", "category": 999, "amount": "100", "comment": ""},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Transaction.objects.exists())

    def test_add_rejects_missing_fields(self):
        response = self.client.post(self.month_url(), {})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Transaction.objects.exists())

    # --- предупреждение о перерасходе плана ---

    def make_plan(self, percent: int = 10) -> None:
        """Бюджет на сентябрь 2026 и доля категории (при 10 % план 1 000 ₽)."""
        month = BudgetMonth.objects.create(
            year=2026, month=9, income=Decimal("10000")
        )
        Allocation.objects.create(
            budget_month=month, category=self.category, percent=percent
        )

    def add_transaction(self, amount: str):
        return self.client.post(
            self.month_url(),
            {
                "date": "2026-09-10",
                "category": self.category.pk,
                "amount": amount,
                "comment": "",
            },
            follow=True,
        )

    def test_add_warns_about_category_overrun(self):
        self.make_plan()  # план 1 000 ₽
        response = self.add_transaction("1200")
        self.assertContains(response, "Трата добавлена")
        self.assertContains(response, "Перерасход по категории «Продукты»")
        # Предупреждаем, но сохраняем.
        self.assertTrue(Transaction.objects.exists())

    def test_add_has_no_warning_when_fact_equals_plan(self):
        self.make_plan()  # план 1 000 ₽
        response = self.add_transaction("1000")
        self.assertNotContains(response, "Перерасход")

    def test_add_ignores_transactions_of_other_months(self):
        self.make_plan()  # план сентября 1 000 ₽
        Transaction.objects.create(
            category=self.category, amount=Decimal("600"), date=date(2026, 9, 30)
        )
        # Октябрь без бюджета: сентябрьские траты в его факт не попадают.
        response = self.client.post(
            self.month_url(2026, 10),
            {
                "date": "2026-10-01",
                "category": self.category.pk,
                "amount": "1100",
                "comment": "",
            },
            follow=True,
        )
        self.assertNotContains(response, "Перерасход")

    def test_add_has_no_warning_within_plan(self):
        self.make_plan()
        response = self.add_transaction("800")
        self.assertNotContains(response, "Перерасход")

    def test_add_has_no_warning_without_budget(self):
        response = self.add_transaction("1200")
        self.assertNotContains(response, "Перерасход")

    def test_add_has_no_warning_when_category_has_no_plan(self):
        BudgetMonth.objects.create(year=2026, month=9, income=Decimal("10000"))
        response = self.add_transaction("1200")
        self.assertNotContains(response, "Перерасход")

    def test_add_has_no_warning_when_plan_is_zero(self):
        self.make_plan(percent=0)
        response = self.add_transaction("1200")
        self.assertNotContains(response, "Перерасход")

    def test_update_reports_overrun_warning(self):
        self.make_plan()
        item = Transaction.objects.create(
            category=self.category, amount=Decimal("900"), date=date(2026, 9, 1)
        )
        response = self.post_json(
            reverse("expenses:transaction_update", args=[item.pk]),
            {
                "date": "2026-09-01",
                "category": self.category.pk,
                "amount": "1100",
                "comment": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Перерасход", response.json()["warning"])

    def test_update_warning_uses_new_category(self):
        self.make_plan()  # план «Продукты» 1 000 ₽
        other = Category.objects.create(name="Кафе")
        item = Transaction.objects.create(
            category=other, amount=Decimal("900"), date=date(2026, 9, 1)
        )
        # Переносим трату в «Продукты» — перерасход считается по новой категории.
        response = self.post_json(
            reverse("expenses:transaction_update", args=[item.pk]),
            {
                "date": "2026-09-01",
                "category": self.category.pk,
                "amount": "1100",
                "comment": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Продукты", response.json()["warning"])

    def test_update_has_no_warning_within_plan(self):
        self.make_plan()
        item = Transaction.objects.create(
            category=self.category, amount=Decimal("100"), date=date(2026, 9, 1)
        )
        response = self.post_json(
            reverse("expenses:transaction_update", args=[item.pk]),
            {
                "date": "2026-09-01",
                "category": self.category.pk,
                "amount": "500",
                "comment": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["warning"], "")

    def test_add_rejects_long_comment(self):
        response = self.client.post(
            self.month_url(),
            {
                "date": "2026-09-10",
                "category": self.category.pk,
                "amount": "100",
                "comment": "x" * 201,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Transaction.objects.exists())

    # --- архивные категории ---

    def test_archived_category_not_offered_for_new_transactions(self):
        archived = Category.objects.create(name="Старое", is_active=False)
        response = self.client.get(self.month_url())
        self.assertNotContains(response, f'<option value="{archived.pk}">')

    def test_archived_category_stays_in_history(self):
        archived = Category.objects.create(name="Старое", is_active=False)
        Transaction.objects.create(
            category=archived, amount=Decimal("100"), date=date(2026, 9, 3)
        )
        response = self.client.get(self.month_url())
        self.assertContains(response, "Старое")
        self.assertContains(response, "(в архиве)")

    def test_add_rejects_archived_category(self):
        archived = Category.objects.create(name="Старое", is_active=False)
        response = self.client.post(
            self.month_url(),
            {
                "date": "2026-09-10",
                "category": archived.pk,
                "amount": "100",
                "comment": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Transaction.objects.exists())

    # --- инлайн-правка ---

    def test_update_transaction(self):
        item = Transaction.objects.create(
            category=self.category, amount=Decimal("100"), date=date(2026, 9, 1)
        )
        response = self.post_json(
            reverse("expenses:transaction_update", args=[item.pk]),
            {
                "date": "2026-09-02",
                "category": self.category.pk,
                "amount": "250.50",
                "comment": "Кафе",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["transaction"]["date"], "2026-09-02")
        self.assertEqual(data["transaction"]["amount"], "250.50")
        self.assertEqual(data["month_url"], self.month_url())

        item.refresh_from_db()
        self.assertEqual(item.amount, Decimal("250.50"))
        self.assertEqual(item.comment, "Кафе")
        self.assertEqual(item.date, date(2026, 9, 2))

    def test_update_reports_field_error(self):
        item = Transaction.objects.create(
            category=self.category, amount=Decimal("100"), date=date(2026, 9, 1)
        )
        response = self.post_json(
            reverse("expenses:transaction_update", args=[item.pk]),
            {
                "date": "2026-09-01",
                "category": self.category.pk,
                "amount": "0",
                "comment": "",
            },
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["field"], "amount")
        self.assertTrue(data["error"])
        item.refresh_from_db()
        self.assertEqual(item.amount, Decimal("100.00"))

    def test_update_allows_archived_category_of_same_transaction(self):
        archived = Category.objects.create(name="Старое", is_active=False)
        item = Transaction.objects.create(
            category=archived, amount=Decimal("100"), date=date(2026, 9, 1)
        )
        response = self.post_json(
            reverse("expenses:transaction_update", args=[item.pk]),
            {
                "date": "2026-09-01",
                "category": archived.pk,
                "amount": "120.00",
                "comment": "",
            },
        )
        self.assertEqual(response.status_code, 200)

    def test_update_rejects_foreign_archived_category(self):
        archived = Category.objects.create(name="Старое", is_active=False)
        item = Transaction.objects.create(
            category=self.category, amount=Decimal("100"), date=date(2026, 9, 1)
        )
        response = self.post_json(
            reverse("expenses:transaction_update", args=[item.pk]),
            {
                "date": "2026-09-01",
                "category": archived.pk,
                "amount": "100",
                "comment": "",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["field"], "category")

    def test_update_normalizes_amount(self):
        # «1e3» — валидный Decimal для формы; ответ и БД должны быть «1000.00».
        item = Transaction.objects.create(
            category=self.category, amount=Decimal("100"), date=date(2026, 9, 1)
        )
        response = self.post_json(
            reverse("expenses:transaction_update", args=[item.pk]),
            {
                "date": "2026-09-01",
                "category": self.category.pk,
                "amount": "1e3",
                "comment": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["transaction"]["amount"], "1000.00")
        item.refresh_from_db()
        self.assertEqual(item.amount, Decimal("1000.00"))

    def test_update_can_move_transaction_to_other_month(self):
        item = Transaction.objects.create(
            category=self.category, amount=Decimal("100"), date=date(2026, 9, 1)
        )
        response = self.post_json(
            reverse("expenses:transaction_update", args=[item.pk]),
            {
                "date": "2026-10-05",
                "category": self.category.pk,
                "amount": "100",
                "comment": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["month_url"], self.month_url(2026, 10))

    def test_update_rejects_bad_json(self):
        item = Transaction.objects.create(
            category=self.category, amount=Decimal("100"), date=date(2026, 9, 1)
        )
        response = self.client.post(
            reverse("expenses:transaction_update", args=[item.pk]),
            data="not json",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_update_rejects_non_object_json(self):
        item = Transaction.objects.create(
            category=self.category, amount=Decimal("100"), date=date(2026, 9, 1)
        )
        url = reverse("expenses:transaction_update", args=[item.pk])
        for body in ["null", json.dumps([1, 2])]:
            with self.subTest(body=body):
                response = self.client.post(
                    url, data=body, content_type="application/json"
                )
                self.assertEqual(response.status_code, 400)

    def test_update_requires_csrf_token(self):
        item = Transaction.objects.create(
            category=self.category, amount=Decimal("100"), date=date(2026, 9, 1)
        )
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        client.get(self.month_url())  # страница ставит cookie csrftoken
        url = reverse("expenses:transaction_update", args=[item.pk])
        payload = json.dumps(
            {
                "date": "2026-09-01",
                "category": self.category.pk,
                "amount": "100",
                "comment": "",
            }
        )

        without_token = client.post(url, data=payload, content_type="application/json")
        self.assertEqual(without_token.status_code, 403)

        token = client.cookies["csrftoken"].value
        with_token = client.post(
            url,
            data=payload,
            content_type="application/json",
            headers={"X-CSRFToken": token},
        )
        self.assertEqual(with_token.status_code, 200)

    def test_update_rejects_get(self):
        item = Transaction.objects.create(
            category=self.category, amount=Decimal("100"), date=date(2026, 9, 1)
        )
        response = self.client.get(
            reverse("expenses:transaction_update", args=[item.pk])
        )
        self.assertEqual(response.status_code, 405)

    def test_update_unknown_transaction_is_404(self):
        response = self.post_json(
            reverse("expenses:transaction_update", args=[999]), {}
        )
        self.assertEqual(response.status_code, 404)

    # --- удаление ---

    def test_delete_transaction(self):
        item = Transaction.objects.create(
            category=self.category, amount=Decimal("100"), date=date(2026, 9, 1)
        )
        response = self.client.post(
            reverse("expenses:transaction_delete", args=[item.pk])
        )
        self.assertRedirects(response, self.month_url())
        self.assertFalse(Transaction.objects.filter(pk=item.pk).exists())

    def test_delete_rejects_get(self):
        item = Transaction.objects.create(
            category=self.category, amount=Decimal("100"), date=date(2026, 9, 1)
        )
        response = self.client.get(
            reverse("expenses:transaction_delete", args=[item.pk])
        )
        self.assertEqual(response.status_code, 405)

    def test_delete_unknown_transaction_is_404(self):
        response = self.client.post(
            reverse("expenses:transaction_delete", args=[999])
        )
        self.assertEqual(response.status_code, 404)
