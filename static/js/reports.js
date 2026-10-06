/* Отчёты: графики «план/факт» и структура трат (Chart.js).

   Данные приходят из json_script-блоков, подписи категорий рисуются на
   canvas — HTML из данных не собирается. Цвета интерфейса берём из
   CSS-переменных; палитра для долей структуры своя, категорий заранее
   неизвестно сколько. */
(function () {
  "use strict";

  if (typeof Chart === "undefined") {
    return;
  }

  const styles = getComputedStyle(document.documentElement);
  const cssVar = function (name) {
    return styles.getPropertyValue(name).trim();
  };

  const textColor = cssVar("--text");
  const mutedColor = cssVar("--muted");
  const borderColor = cssVar("--border");
  const accentColor = cssVar("--accent");
  const planColor = cssVar("--chart-plan");

  const moneyFmt = new Intl.NumberFormat("ru-RU", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  const axisFmt = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });

  // Палитра для круговой диаграммы: категорий может быть больше, поэтому
  // цвета повторяются по кругу.
  const PALETTE = [
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
  ];

  function readData(id) {
    const node = document.getElementById(id);
    if (!node) {
      return null;
    }
    try {
      return JSON.parse(node.textContent);
    } catch (error) {
      console.warn("Не удалось разобрать данные графика " + id, error);
      return null;
    }
  }

  function barChart(canvasId, data) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || !data || !data.labels.length) {
      return;
    }
    new Chart(canvas, {
      type: "bar",
      data: {
        labels: data.labels,
        datasets: [
          {
            label: "Бюджет",
            data: data.planned,
            backgroundColor: planColor,
            borderRadius: 4,
          },
          {
            label: "Траты",
            data: data.fact,
            backgroundColor: accentColor,
            borderRadius: 4,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: "bottom",
            labels: { color: textColor, boxWidth: 14 },
          },
          tooltip: {
            callbacks: {
              label: function (context) {
                return (
                  context.dataset.label +
                  ": " +
                  moneyFmt.format(context.parsed.y) +
                  " ₽"
                );
              },
            },
          },
        },
        scales: {
          x: {
            ticks: { color: mutedColor },
            grid: { display: false },
          },
          y: {
            beginAtZero: true,
            ticks: {
              color: mutedColor,
              // precision: 0 — Chart.js сам подбирает целые шаги,
              // иначе при мелких суммах подписи дублируются (1, 1, 2, 2).
              precision: 0,
              callback: function (value) {
                return axisFmt.format(value);
              },
            },
            grid: { color: borderColor },
          },
        },
      },
    });
  }

  function doughnutChart(canvasId, data) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || !data || !data.labels.length) {
      return;
    }
    new Chart(canvas, {
      type: "doughnut",
      data: {
        labels: data.labels,
        datasets: [
          {
            data: data.fact,
            backgroundColor: data.labels.map(function (_label, index) {
              return PALETTE[index % PALETTE.length];
            }),
            borderWidth: 0,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: "bottom",
            labels: { color: textColor, boxWidth: 14 },
          },
          tooltip: {
            callbacks: {
              label: function (context) {
                return context.label + ": " + moneyFmt.format(context.parsed) + " ₽";
              },
            },
          },
        },
      },
    });
  }

  barChart("plan-fact-chart", readData("plan-fact-data"));
  barChart("year-months-chart", readData("year-months-data"));
  doughnutChart("year-structure-chart", readData("year-structure-data"));
})();
