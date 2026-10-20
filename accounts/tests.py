"""Тесты открытой регистрации."""
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from budget.models import Category
from expenses.models import Transaction


class SignupTests(TestCase):
    """Регистрация: создаёт аккаунт, сразу входит, данные у каждого свои."""

    def signup_url(self) -> str:
        return reverse("accounts:signup")

    def test_signup_page_is_public(self):
        response = self.client.get(self.signup_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Регистрация")

    def test_signup_creates_user_and_logs_in(self):
        response = self.client.post(
            self.signup_url(),
            {
                "username": "newbie",
                "password1": "sup3r-pass-123",
                "password2": "sup3r-pass-123",
            },
        )
        self.assertRedirects(response, reverse("home"))
        self.assertTrue(User.objects.filter(username="newbie").exists())
        # Вошли сразу: главная открывается, а не уводит на вход.
        home = self.client.get(reverse("home"))
        self.assertContains(home, "Обзор")

    def test_signup_rejects_mismatched_passwords(self):
        response = self.client.post(
            self.signup_url(),
            {
                "username": "newbie",
                "password1": "sup3r-pass-123",
                "password2": "другой-пароль-123",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.exists())

    def test_signup_rejects_duplicate_username(self):
        User.objects.create_user(username="owner", password="test-pass-123")
        response = self.client.post(
            self.signup_url(),
            {
                "username": "owner",
                "password1": "sup3r-pass-123",
                "password2": "sup3r-pass-123",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), 1)

    def test_signup_redirects_logged_in_user(self):
        User.objects.create_user(username="owner", password="test-pass-123")
        self.client.force_login(User.objects.get(username="owner"))
        response = self.client.get(self.signup_url())
        self.assertRedirects(response, reverse("home"))

    def test_login_page_links_to_signup(self):
        response = self.client.get(reverse("login"))
        self.assertContains(response, reverse("accounts:signup"))

    def test_login_page_is_public(self):
        """Проверяет, что страница входа доступна без авторизации."""
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Войдите, чтобы вести свой бюджет.")


class NewUserIsolationTests(TestCase):
    """Новый пользователь видит пустой сайт и не видит чужих данных."""

    def test_new_user_sees_only_own_empty_data(self):
        owner = User.objects.create_user(username="owner", password="test-pass-123")
        category = Category.objects.create(owner=owner, name="Продукты")
        Transaction.objects.create(
            owner=owner, category=category, amount=Decimal("100")
        )

        # Регистрируемся анонимно: аккаунт создаётся, вход выполняется сразу.
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "username": "guest",
                "password1": "sup3r-pass-123",
                "password2": "sup3r-pass-123",
            },
        )
        self.assertRedirects(response, reverse("home"))
        self.assertTrue(User.objects.filter(username="guest").exists())

        # У гостя свой - пустой - сайт: чужие траты не видны.
        expenses = self.client.get(reverse("expenses:index"))
        self.assertEqual(expenses.status_code, 200)
        self.assertNotContains(expenses, "Продукты")
        purchases = self.client.get(reverse("purchases:index"))
        self.assertContains(purchases, "Активных целей нет")
