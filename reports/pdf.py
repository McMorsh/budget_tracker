"""PDF-отчёты за месяц и за год: графики matplotlib + вёрстка WeasyPrint.

Matplotlib и WeasyPrint импортируются внутри функций: при старте сайта их
держать в памяти не нужно, а matplotlib занимает десятки мегабайт. Суммы
переводятся в float только для графиков (`json`-подобный обмен с matplotlib);
в PDF и на страницах - по-прежнему Decimal. Графики вставляются в HTML как
PNG в data-URI - WeasyPrint не ходит по внешним URL.
"""
import base64
import io
import os
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.contrib.auth.models import User
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.formats import number_format

from . import queries

# Цвета - как в палитре сайта (static/css/style.css и reports.js).
BAR_BUDGET_COLOR = "#93c5fd"
BAR_SPENT_COLOR = "#2563eb"
PIE_COLORS = [
    "#60a5fa",
    "#f59e0b",
    "#34d399",
    "#f472b6",
    "#a78bfa",
    "#f87171",
    "#22d3ee",
    "#facc15",
    "#4ade80",
    "#94a3b8",
]

# Подкаталог внутри MEDIA_ROOT; имена файлов детерминированные - отчёт
# пересобирается при каждом скачивании, поэтому кэш не нужен.
REPORT_DIR = "reports"

# Сколько секторов круговой диаграммы показываем отдельно; остальные
# свёртываем в "Прочее", иначе легенда из десятков строк нечитаема.
PIE_MAX_SLICES = 8

# После стольких столбцов диаграмма занимает всю ширину страницы
# (месяцы - под ней отдельной строкой), иначе столбцы и подписи тесны.
WIDE_CHART_AFTER = 8


def report_path(owner: User, year: int, month: int | None = None) -> Path:
    """Путь к PDF-отчёту владельца в media.

    Файлы лежат в подкаталоге пользователя: у разных владельцев отчёты
    не перезаписывают друг друга.

    Args:
        owner: Владелец данных.
        year: Год отчёта.
        month: Номер месяца; без него - отчёт за год.

    Returns:
        Путь к файлу (файл может ещё не существовать).
    """
    name = f"{year}.pdf" if month is None else f"{year}-{month:02d}.pdf"
    return Path(settings.MEDIA_ROOT) / REPORT_DIR / str(owner.pk) / name


def build_report_pdf(year: int, month: int, owner: User) -> Path:
    """Собирает PDF-отчёт за месяц и сохраняет его в media.

    Args:
        year: Год отчёта.
        month: Номер месяца (1-12).
        owner: Владелец данных, попадающих в отчёт.

    Returns:
        Путь к сохранённому PDF-файлу.
    """
    report = queries.month_report(year, month, owner)
    wide = len(report.rows) > WIDE_CHART_AFTER

    chart_bar = None
    chart_pie = None
    if report.rows:
        chart_bar = _png_data_uri(
            _bar_chart(
                [row.category.name for row in report.rows],
                [row.planned for row in report.rows],
                [row.fact for row in report.rows],
                wide=wide,
            )
        )
        pie = _pie_chart([(row.category.name, row.fact) for row in report.rows])
        if pie is not None:
            chart_pie = _png_data_uri(pie)

    html = render_to_string(
        "reports/pdf/month.html",
        {
            "report": report,
            "bar_chart": chart_bar,
            "pie_chart": chart_pie,
            "stacked": wide and chart_bar is not None,
            "generated_at": timezone.localdate(),
        },
    )
    return _write_pdf(html, report_path(owner, year, month))


def build_year_pdf(year: int, owner: User) -> Path:
    """Собирает PDF-отчёт за год и сохраняет его в media.

    Args:
        year: Год отчёта.
        owner: Владелец данных, попадающих в отчёт.

    Returns:
        Путь к сохранённому PDF-файлу.
    """
    report = queries.year_report(year, owner)
    wide = len(report.months) > WIDE_CHART_AFTER

    chart_bar = None
    chart_pie = None
    if report.months:
        chart_bar = _png_data_uri(
            _bar_chart(
                [month.title for month in report.months],
                [month.planned for month in report.months],
                [month.spent for month in report.months],
                wide=wide,
            )
        )
        pie = _pie_chart([(row.category.name, row.fact) for row in report.rows])
        if pie is not None:
            chart_pie = _png_data_uri(pie)

    html = render_to_string(
        "reports/pdf/year.html",
        {
            "report": report,
            "bar_chart": chart_bar,
            "pie_chart": chart_pie,
            "stacked": wide and chart_bar is not None,
            "generated_at": timezone.localdate(),
        },
    )
    return _write_pdf(html, report_path(owner, year))


def _write_pdf(html: str, path: Path) -> Path:
    """Собирает PDF из HTML и атомарно кладёт его в media."""
    pdf_bytes = _html_to_pdf(html)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Уникальное имя временного файла + os.replace: конкурентные скачивания
    # одного отчёта не мешают друг другу и не оставляют хвостов.
    tmp_path = path.with_name(f"{path.name}.{uuid4().hex}.part")
    try:
        tmp_path.write_bytes(pdf_bytes)
        os.replace(tmp_path, path)
    finally:
        tmp_path.unlink(missing_ok=True)
    return path


def _html_to_pdf(html: str) -> bytes:
    """Превращает HTML в PDF (единственное место вызова WeasyPrint)."""
    from weasyprint import HTML

    pdf_bytes = HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()
    # Без target WeasyPrint всегда отдаёт байты; None в типе - для записи в файл.
    if pdf_bytes is None:
        raise RuntimeError("WeasyPrint не вернул PDF")
    return pdf_bytes


def _png_data_uri(png: bytes) -> str:
    """PNG в data-URI для вставки в HTML."""
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def _bar_chart(
    labels: list[str], planned: list[Decimal], fact: list[Decimal], wide: bool = False
) -> bytes:
    """Столбчатая диаграмма "бюджет / траты" (PNG).

    Args:
        labels: Подписи столбцов (категории или месяцы).
        planned: Бюджет по столбцам.
        fact: Траты по столбцам.
        wide: Диаграмма на всю ширину страницы (много столбцов).
    """
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    from matplotlib.ticker import FuncFormatter

    if wide:
        figure_size = (7.2, 3.2)
        font_size = 9
        rotation = 45
    else:
        # Фигура близка к ширине колонки в PDF (≈110 мм): чем меньше масштаб,
        # тем крупнее получается текст на бумаге.
        figure_size = (4.8, 2.9)
        font_size = 8
        rotation = 35

    positions = list(range(len(labels)))
    width = 0.38
    figure, axes = plt.subplots(figsize=figure_size, dpi=150)
    axes.bar(
        [position - width / 2 for position in positions],
        # float - только для matplotlib: он принимает числа, а не Decimal.
        [float(value) for value in planned],
        width,
        label="Бюджет",
        color=BAR_BUDGET_COLOR,
    )
    axes.bar(
        [position + width / 2 for position in positions],
        [float(value) for value in fact],
        width,
        label="Траты",
        color=BAR_SPENT_COLOR,
    )
    axes.set_xticks(positions)
    axes.set_xticklabels(labels, rotation=rotation, ha="right", fontsize=font_size)
    axes.tick_params(axis="y", labelsize=font_size)
    axes.yaxis.set_major_formatter(FuncFormatter(_thousands))
    # Легенда над полем графика: внутри она перекрывает высокие столбцы.
    axes.legend(
        loc="lower left",
        bbox_to_anchor=(0.0, 1.0),
        ncols=2,
        frameon=False,
        fontsize=font_size,
    )
    axes.grid(axis="y", color="#e5e7eb", linewidth=0.8)
    axes.set_axisbelow(True)
    for spine in ("top", "right"):
        axes.spines[spine].set_visible(False)
    figure.tight_layout()

    buffer = io.BytesIO()
    try:
        # bbox_inches: вместе с легендой над осями.
        figure.savefig(buffer, format="png", bbox_inches="tight")
    finally:
        # Фигура живёт в глобальном реестре pyplot - закрываем в любом случае.
        plt.close(figure)
    return buffer.getvalue()


def _pie_chart(items: list[tuple[str, Decimal]]) -> bytes | None:
    """Круговая диаграмма структуры трат; None, если трат нет.

    Args:
        items: Пары (название, сумма) без фильтрации и сортировки.

    Крупные позиции - отдельными секторами (их не больше `PIE_MAX_SLICES`),
    мелкие - одним сектором "Прочее".
    """
    rows = sorted(
        ((name, amount) for name, amount in items if amount > 0),
        key=lambda item: item[1],
        reverse=True,
    )
    if not rows:
        return None

    main = rows[:PIE_MAX_SLICES]
    labels = [_legend_label(name, amount) for name, amount in main]
    values = [float(amount) for _name, amount in main]
    if len(rows) > PIE_MAX_SLICES:
        # Мелкие категории объединяем: легенда из десятков строк нечитаема.
        other = sum((amount for _name, amount in rows[PIE_MAX_SLICES:]), Decimal("0"))
        labels.append(_legend_label("Прочее", other))
        values.append(float(other))

    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    figure, axes = plt.subplots(figsize=(3.1, 2.7), dpi=150)
    wedges, _texts, _percents = axes.pie(
        values,
        colors=[PIE_COLORS[index % len(PIE_COLORS)] for index in range(len(values))],
        autopct=_percent_label,
        startangle=90,
        textprops={"fontsize": 7},
        wedgeprops={"linewidth": 0.6, "edgecolor": "white"},
    )
    # Легенда под диаграммой в две колонки: рядом с ней текст мельчает.
    axes.legend(
        wedges,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.0),
        ncols=2,
        fontsize=7,
        frameon=False,
    )

    buffer = io.BytesIO()
    try:
        figure.savefig(buffer, format="png", bbox_inches="tight")
    finally:
        plt.close(figure)
    return buffer.getvalue()


def _legend_label(name: str, amount: Decimal) -> str:
    """Строка легенды: "Продукты - 16 451 ₽" (копейки в легенде не нужны)."""
    return f"{name} - {number_format(amount, decimal_pos=0, force_grouping=True)} ₽"


def _thousands(value: float, _position: int | None = None) -> str:
    """Подпись оси: 34000.0 -> "34 000"."""
    return f"{value:,.0f}".replace(",", "\u00a0")


def _percent_label(percent: float) -> str:
    """Доля на круговой: подписываем только крупные секторы."""
    return f"{percent:.0f}%" if percent >= 5 else ""
