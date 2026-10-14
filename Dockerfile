FROM python:3.14-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Кэш matplotlib в /tmp: работает и при read-only HOME, без предупреждений
    MPLCONFIGDIR=/tmp/matplotlib

WORKDIR /app

# WeasyPrint (PDF): pango/harfbuzz для вёрстки; DejaVu - шрифты с кириллицей
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libharfbuzz-subset0 \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/ ./requirements/
RUN pip install --no-cache-dir -r requirements/base.txt


FROM base AS dev

COPY . .

EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]


FROM base AS prod

RUN pip install --no-cache-dir -r requirements/prod.txt

COPY . .

EXPOSE 8000
# --max-requests: воркер после отдачи PDF держит matplotlib (~100 МБ RSS);
# периодический перезапуск возвращает память системе.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--max-requests", "20", "--max-requests-jitter", "5"]
