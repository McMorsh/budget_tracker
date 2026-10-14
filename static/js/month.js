/* Экран месяца: живой пересчёт сумм при вводе доходов и долей.

   Только предпросмотр - при сохранении всё пересчитывает сервер
   (округление до копеек, ROUND_HALF_UP). */
(function () {
  "use strict";

  const form = document.getElementById("month-form");
  if (!form) {
    return;
  }

  const incomeInput = form.querySelector('input[name="income"]');
  const moneyFmt = new Intl.NumberFormat("ru-RU", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  const percentFmt = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });

  function toNumber(input) {
    if (!input) {
      return 0;
    }
    const value = parseFloat(String(input.value).replace(",", "."));
    return isNaN(value) ? 0 : value;
  }

  function toMoney(value) {
    return Math.round(value * 100) / 100;
  }

  function update() {
    const income = toMoney(toNumber(incomeInput));
    let sumPercent = 0;
    let sumAmount = 0;

    form.querySelectorAll("input[data-percent]").forEach(function (input) {
      sumPercent += toNumber(input);
      const amount = toMoney((income * toNumber(input)) / 100);
      sumAmount = toMoney(sumAmount + amount);
      const cell = input.closest("tr").querySelector("[data-amount]");
      if (cell) {
        cell.textContent = moneyFmt.format(amount) + " ₽";
      }
    });

    const totalCell = document.getElementById("total-amount");
    if (totalCell) {
      totalCell.textContent = moneyFmt.format(sumAmount) + " ₽";
    }

    const sumPercentEl = document.getElementById("sum-percent");
    if (sumPercentEl) {
      const sumPercentRounded = Math.round(sumPercent);
      sumPercentEl.textContent = percentFmt.format(sumPercentRounded);
      const badge = sumPercentEl.closest(".badge");
      const balanced = sumPercentRounded === 100;
      if (badge) {
        badge.classList.toggle("badge-ok", balanced);
        badge.classList.toggle("badge-warn", !balanced);
      }
    }

    const remaining = toMoney(income - sumAmount);
    const balance = document.getElementById("balance-line");
    if (balance) {
      if (remaining < 0) {
        balance.textContent = "Перерасход: " + moneyFmt.format(-remaining) + " ₽";
        balance.classList.add("negative");
      } else {
        balance.textContent =
          "Свободно от дохода: " + moneyFmt.format(remaining) + " ₽";
        balance.classList.remove("negative");
      }
    }
  }

  form.addEventListener("input", update);
  update();
})();
