"""Настройки для локальной разработки (docker/podman compose или venv)."""
from .base import *
from .base import env

DEBUG = True

ALLOWED_HOSTS = env.list(
    "DJANGO_ALLOWED_HOSTS",
    default=["localhost", "127.0.0.1"],
)
