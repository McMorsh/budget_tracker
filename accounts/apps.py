"""Конфигурация приложения "Аккаунты"."""
from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """Регистрация; собственных моделей нет - используется `auth.User`."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
    verbose_name = "аккаунты"
