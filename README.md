# Budget Tracker — сайт «Расходы»

Личный сайт для учёта бюджета: распределение месячного дохода по категориям,
ежедневный ввод трат, аналитика «план/факт», графики, PDF-отчёт за месяц и
страница планов покупок.

## Стек

| Слой | Технология |
|---|---|
| Язык | Python 3.14 |
| Фреймворк | Django 5.2 LTS (патч 5.2.17; для Python 3.14 нужен ≥ 5.2.8) |
| База данных | PostgreSQL 18 |
| HTTP-сервер | Gunicorn + WhiteNoise |
| PDF | WeasyPrint 70 |
| Графики | Chart.js 4 (веб), matplotlib — для графиков в PDF |
| Обратный прокси | Caddy (конфиг — в `sites-infra`) |
| Запуск | Docker / docker compose |

## Целевой MVP

1. **Распределение дохода месяца** — доход, категории и «отложить»;
   план в процентах и/или рублях.
2. **Дневной ввод трат** — сумма + категория, дата по умолчанию «сегодня»;
   месяц траты определяется по её дате.
3. **План/факт и графики** — за месяц, год и в динамике.
4. **PDF-отчёты за месяц и год**.
5. **Планы покупок** — цели и накопления по ним.

## Принятые решения

- Django 5.2 LTS (поддержка до 30.04.2028) вместо Django 6.1 (до 31.12.2027).
- Деньги — только `DecimalField`; валюта одна - ₽.
- В MVP нет счетов (`Account`) и мультивалютности.

## Структура

```
budget_tracker/
├── config/              # Django-проект: settings (base/dev/prod), urls, wsgi/asgi
├── budget/              # категории и распределение дохода
├── expenses/            # ежедневные траты
├── purchases/           # планы покупок
├── reports/             # план/факт, графики, PDF
├── requirements/        # base.txt, dev.txt (django-stubs), prod.txt
├── templates/           # HTML-шаблоны (base, обзор, бюджет, траты,
│                        #   покупки, отчёты, вход)
├── static/              # css / js / изображения
├── locale/              # переводы
├── media/               # генерируемые файлы (в git только README папки)
├── manage.py
├── Dockerfile           # targets: dev (runserver), prod (gunicorn)
├── docker-compose.yml   # локальная разработка: web + postgres:18
├── .dockerignore
├── .env.example
├── PLAN.md
└── .gitignore
```

## Быстрый старт (локально)

Нужен Docker или Podman с поддержкой compose. Один раз создайте `.env` и
подставьте свой `DJANGO_SECRET_KEY`:

```sh
cp .env.example .env
docker compose up --build -d
docker compose exec web python manage.py createsuperuser
```

- сайт: http://localhost:8000/
- админка: http://localhost:8000/admin/
- логи: `docker compose logs -f web`
- остановить: `docker compose down` (данные БД остаются в томе `pgdata`;
  снести вместе с данными - `docker compose down -v`)

С Podman команды те же, только вместо `docker` - `podman` (или `podman-compose`).
На Fedora `podman compose` требует отдельного провайдера: `sudo dnf install podman-compose`.
Миграции применяются автоматически при старте web-сервиса.

Вариант без контейнеров - venv и локальный PostgreSQL:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements/base.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver
```

## Публичное и приватное

- **Публично:** код, миграции, тесты, `.env.example`, демо-данные (`seed_demo`).
- **Приватно / вне git:** `.env*`, `media/` (включая готовые PDF), `backups/`,
  prod-compose, Caddyfile, скрипты бэкапов, SSH-ключи, дампы живой БД.
