#!/usr/bin/env python
"""Утилита командной строки Django."""
import os
import sys


def main():
    # Локально по умолчанию используем dev-настройки;
    # для продакшена DJANGO_SETTINGS_MODULE задаётся в окружении.
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Не удалось импортировать Django. Убедитесь, что зависимости "
            "установлены (pip install -r requirements/base.txt) и активно "
            "виртуальное окружение."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
