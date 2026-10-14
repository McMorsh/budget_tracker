/* Траты: инлайн-правка строки и подтверждение удаления.

   После успешной правки таблица перезапрашивается с сервера (fetch +
   DOMParser): порядок строк, итоги и подписи приходят из базы, а не
   собираются заново в JS. Слушатели повешены на document, поэтому замена
   таблицы их не теряет. */
(function () {
  "use strict";

  const quickAdd = document.getElementById("quick-add");

  function getCookie(name) {
    const match = document.cookie.match(new RegExp("(^|;\\s*)" + name + "=([^;]*)"));
    return match ? decodeURIComponent(match[2]) : "";
  }

  function currentTable() {
    return document.getElementById("tx-table");
  }

  function request(url, payload) {
    return fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken"),
      },
      body: JSON.stringify(payload),
    }).then(function (response) {
      return response
        .json()
        .catch(function () {
          return {};
        })
        .then(function (data) {
          if (!response.ok) {
            const error = new Error(data.error || "Ошибка " + response.status);
            error.field = data.field || "";
            throw error;
          }
          return data;
        });
    });
  }

  /* --- удаление: подтверждение --- */

  document.addEventListener("submit", function (event) {
    const form = event.target.closest("form[data-confirm]");
    if (form && !window.confirm(form.dataset.confirm)) {
      event.preventDefault();
    }
  });

  /* --- после правки: таблица и итоги заново с сервера --- */

  function refreshTable() {
    fetch(window.location.href)
      .then(function (response) {
        if (!response.ok) {
          throw new Error("HTTP " + response.status);
        }
        return response.text();
      })
      .then(function (html) {
        const fresh = new DOMParser()
          .parseFromString(html, "text/html")
          .getElementById("tx-table");
        const table = currentTable();
        if (fresh && table) {
          table.replaceWith(fresh);
        } else {
          // Сессия истекла или разметка изменилась - показываем страницу целиком.
          window.location.reload();
        }
      })
      .catch(function () {
        // Не смогли обновить тихо - показываем страницу целиком.
        window.location.reload();
      });
  }

  /* --- предупреждение о перерасходе плана (приходит после правки) --- */

  function clearWarning() {
    document
      .querySelectorAll(".messages li[data-js-warning]")
      .forEach(function (item) {
        item.remove();
      });
  }

  function showWarning(message) {
    let list = document.querySelector(".messages");
    if (!list) {
      const main = document.querySelector("main.main");
      if (!main) {
        return;
      }
      list = document.createElement("ul");
      list.className = "messages";
      main.insertBefore(list, main.firstChild);
    }
    // Прошлое предупреждение от JS заменяем, чтобы не копились.
    clearWarning();
    const item = document.createElement("li");
    item.className = "alert alert-warning";
    item.dataset.jsWarning = "1";
    item.textContent = message;
    list.appendChild(item);
  }

  /* --- инлайн-правка --- */

  let editing = null;

  function clearError(cell) {
    const error = cell.querySelector(".field-error");
    if (error) {
      error.remove();
    }
  }

  function showError(cell, message) {
    clearError(cell);
    const error = document.createElement("span");
    error.className = "field-error";
    error.textContent = message;
    cell.appendChild(error);
  }

  function startEdit(row) {
    if (editing && !document.contains(editing.row)) {
      // Таблицу успели заменить (refreshTable) - прежняя правка осиротела.
      editing = null;
    }
    if (!row || editing || !row.classList.contains("tx-row")) {
      return;
    }
    const table = currentTable();
    const view = table ? table.dataset.view : "";
    const savedHtml = row.innerHTML;

    const dateCell = row.querySelector(".tx-date");
    const categoryCell = row.querySelector(".tx-category");
    const commentCell = row.querySelector(".tx-comment");
    const amountCell = row.querySelector(".tx-amount");
    const actionsCell = row.querySelector(".row-actions");
    if (!dateCell || !categoryCell || !commentCell || !amountCell || !actionsCell) {
      return;
    }

    const dateInput = document.createElement("input");
    dateInput.type = "date";
    dateInput.className = "cell-edit date-edit";
    dateInput.value = row.dataset.date;
    dateInput.required = true;
    dateInput.setAttribute("aria-label", "Дата");

    /* Категории берём из формы быстрого ввода (активные), а архивную
       категорию самой строки добавляем, если её там нет. */
    const categorySelect = document.createElement("select");
    categorySelect.className = "cell-edit select-edit";
    categorySelect.setAttribute("aria-label", "Категория");
    const source = quickAdd && quickAdd.querySelector('select[name="category"]');
    if (source) {
      Array.prototype.forEach.call(source.options, function (option) {
        if (option.value) {
          categorySelect.appendChild(option.cloneNode(true));
        }
      });
    }
    if (!categorySelect.querySelector('option[value="' + row.dataset.categoryId + '"]')) {
      const option = document.createElement("option");
      option.value = row.dataset.categoryId;
      option.textContent = row.dataset.categoryName + " (в архиве)";
      categorySelect.appendChild(option);
    }
    categorySelect.value = row.dataset.categoryId;

    const commentInput = document.createElement("input");
    commentInput.type = "text";
    commentInput.className = "cell-edit comment-edit";
    commentInput.maxLength = 200;
    commentInput.value = row.dataset.comment;
    commentInput.setAttribute("aria-label", "Комментарий");

    const amountInput = document.createElement("input");
    amountInput.type = "number";
    amountInput.className = "cell-edit money-edit";
    amountInput.step = "0.01";
    amountInput.min = "0.01";
    amountInput.inputMode = "decimal";
    amountInput.value = row.dataset.amount;
    amountInput.required = true;
    amountInput.setAttribute("aria-label", "Сумма, ₽");

    dateCell.textContent = "";
    dateCell.appendChild(dateInput);
    categoryCell.textContent = "";
    categoryCell.appendChild(categorySelect);
    commentCell.classList.remove("muted");
    commentCell.textContent = "";
    commentCell.appendChild(commentInput);
    amountCell.textContent = "";
    amountCell.appendChild(amountInput);
    actionsCell.textContent = "";

    const saveButton = document.createElement("button");
    saveButton.type = "button";
    saveButton.className = "link-button";
    saveButton.textContent = "Сохранить";
    const cancelButton = document.createElement("button");
    cancelButton.type = "button";
    cancelButton.className = "link-button";
    cancelButton.textContent = "Отмена";
    actionsCell.append(saveButton, cancelButton);

    let busy = false;

    function cancel() {
      if (busy) {
        return;
      }
      editing = null;
      row.innerHTML = savedHtml;
      const button = row.querySelector(".tx-edit");
      if (button) {
        button.focus();
      }
    }

    function save() {
      if (busy) {
        return;
      }
      busy = true;
      [dateCell, categoryCell, commentCell, amountCell].forEach(clearError);
      request(row.dataset.updateUrl, {
        date: dateInput.value,
        category: categorySelect.value,
        amount: amountInput.value,
        comment: commentInput.value,
      })
        .then(function (data) {
          editing = null;
          if (!data.transaction) {
            // Сервер ответил не тем (например, сессия истекла) -
            // показываем страницу целиком.
            window.location.reload();
            return;
          }
          if (data.transaction.date.slice(0, 7) !== view) {
            // Дата ушла в другой месяц - показываем его.
            window.location.href = data.month_url;
            return;
          }
          if (data.warning) {
            showWarning(data.warning);
          } else {
            // Перерасхода больше нет - убираем прошлое предупреждение.
            clearWarning();
          }
          refreshTable();
        })
        .catch(function (error) {
          busy = false;
          const message =
            error instanceof TypeError
              ? "Нет связи с сервером - проверьте соединение"
              : error.message;
          const cells = {
            date: dateCell,
            category: categoryCell,
            comment: commentCell,
            amount: amountCell,
          };
          const cell = cells[error.field] || amountCell;
          showError(cell, message);
          const input = cell.querySelector("input, select");
          if (input) {
            input.focus();
          }
        });
    }

    editing = { row: row, save: save, cancel: cancel };
    saveButton.addEventListener("click", save);
    cancelButton.addEventListener("click", cancel);
    amountInput.focus();
    amountInput.select();
  }

  document.addEventListener("click", function (event) {
    const button = event.target.closest(".tx-edit");
    if (button) {
      event.preventDefault();
      startEdit(button.closest("tr"));
    }
  });

  document.addEventListener("dblclick", function (event) {
    const cell = event.target.closest(".tx-row td");
    if (
      !cell ||
      cell.classList.contains("actions-cell") ||
      cell.querySelector("input, select")
    ) {
      return;
    }
    startEdit(cell.closest("tr"));
  });

  document.addEventListener("keydown", function (event) {
    if (!editing || !editing.row.contains(event.target)) {
      return;
    }
    if (event.target.tagName === "SELECT") {
      // Не мешаем нативному списку категорий: Enter/Escape - его клавиши,
      // а не сохранить/отменить всю строку.
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      editing.save();
    } else if (event.key === "Escape") {
      editing.cancel();
    }
  });
})();
