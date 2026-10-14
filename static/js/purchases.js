/* Покупки: инлайн-правка целей и взносов, смена статуса.
 *
 * После успешного сохранения разметка (таблицы списка или сводка и взносы
 * в карточке цели) перезапрашивается с сервера - порядок, прогресс и итоги
 * приходят из базы, а не пересчитываются в JS. Слушатели повешены на
 * document, поэтому замена разметки их не теряет. */
(function () {
  "use strict";

  function getCookie(name) {
    const match = document.cookie.match(new RegExp("(^|;\\s*)" + name + "=([^;]*)"));
    return match ? decodeURIComponent(match[2]) : "";
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

  function errorMessage(error) {
    return error instanceof TypeError
      ? "Нет связи с сервером - проверьте соединение"
      : error.message;
  }

  /* --- удаления: подтверждение --- */

  document.addEventListener("submit", function (event) {
    const form = event.target.closest("form[data-confirm]");
    if (form && !window.confirm(form.dataset.confirm)) {
      event.preventDefault();
    }
  });

  /* --- обновление блоков разметки с сервера ---

     Блоков может быть несколько (сводка цели и таблица взносов); форму
     "Добавить взнос" не трогаем, чтобы не терять черновик. */

  function refreshBlocks(ids) {
    fetch(window.location.href)
      .then(function (response) {
        if (!response.ok) {
          throw new Error("HTTP " + response.status);
        }
        return response.text();
      })
      .then(function (html) {
        const fresh = new DOMParser().parseFromString(html, "text/html");
        let complete = true;
        ids.forEach(function (id) {
          const freshBlock = fresh.getElementById(id);
          const current = document.getElementById(id);
          if (freshBlock && current) {
            current.replaceWith(freshBlock);
          } else {
            complete = false;
          }
        });
        if (!complete) {
          // Сессия истекла или разметка изменилась - показываем страницу целиком.
          window.location.reload();
        }
      })
      .catch(function () {
        // Не смогли обновить тихо - показываем страницу целиком.
        window.location.reload();
      });
  }

  /* --- ошибки по полям строки --- */

  let editing = null;

  function dropOrphanEdit() {
    if (editing && !document.contains(editing.row)) {
      // Разметку успели заменить - прежняя правка осиротела.
      editing = null;
    }
  }

  function clearError(container) {
    const error = container.querySelector(".field-error");
    if (error) {
      error.remove();
    }
  }

  function showError(container, message) {
    clearError(container);
    const error = document.createElement("span");
    error.className = "field-error";
    error.textContent = message;
    container.appendChild(error);
  }

  function cellInput(type, className, value, label) {
    const input = document.createElement("input");
    input.type = type;
    input.className = "cell-edit " + className;
    input.value = value;
    input.required = true;
    input.setAttribute("aria-label", label);
    return input;
  }

  function actionButtons() {
    const save = document.createElement("button");
    save.type = "button";
    save.className = "link-button";
    save.textContent = "Сохранить";
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "link-button";
    cancel.textContent = "Отмена";
    return { save: save, cancel: cancel };
  }

  /* --- правка цели: строка превращается в редактор на всю ширину --- */

  function editField(label, type, className, value) {
    const wrap = document.createElement("span");
    wrap.className = "edit-field";
    const input = cellInput(type, className, value, label);
    wrap.appendChild(input);
    return { wrap: wrap, input: input };
  }

  function editSelect(label, className, value, source) {
    const wrap = document.createElement("span");
    wrap.className = "edit-field";
    const select = document.createElement("select");
    select.className = "cell-edit " + className;
    select.setAttribute("aria-label", label);
    // Варианты берём из формы добавления, чтобы подписи не дублировались в JS.
    if (source) {
      Array.prototype.forEach.call(source.options, function (option) {
        select.appendChild(option.cloneNode(true));
      });
    }
    select.value = value;
    wrap.appendChild(select);
    return { wrap: wrap, input: select };
  }

  function startPurchaseEdit(row) {
    dropOrphanEdit();
    if (editing || !row || !row.closest("#purchase-lists")) {
      return;
    }
    const table = row.closest("table");
    if (!table) {
      return;
    }
    const savedHtml = row.innerHTML;
    const columns = table.querySelectorAll("thead th").length;

    const titleField = editField("Название цели", "text", "title-edit", row.dataset.title);
    titleField.input.maxLength = 200;
    const amountField = editField("Стоимость, ₽", "number", "money-edit", row.dataset.amount);
    amountField.input.step = "0.01";
    amountField.input.min = "0";
    amountField.input.inputMode = "decimal";
    const priorityField = editField("Приоритет", "number", "priority-edit", row.dataset.priority);
    priorityField.input.step = "1";
    priorityField.input.min = "0";
    const statusSource = document.querySelector(
      "#purchase-add select[name='status']"
    );
    const statusField = editSelect(
      "Статус",
      "status-edit",
      row.dataset.status,
      statusSource
    );

    const editor = document.createElement("td");
    editor.className = "row-editor-cell";
    editor.colSpan = columns;

    const box = document.createElement("div");
    box.className = "row-editor";
    const buttons = actionButtons();
    box.append(
      titleField.wrap,
      amountField.wrap,
      priorityField.wrap,
      statusField.wrap,
      buttons.save,
      buttons.cancel
    );
    editor.appendChild(box);
    row.textContent = "";
    row.appendChild(editor);

    let busy = false;

    function cancel() {
      if (busy) {
        return;
      }
      editing = null;
      row.innerHTML = savedHtml;
    }

    function save() {
      if (busy) {
        return;
      }
      busy = true;
      [titleField, amountField, priorityField, statusField].forEach(function (field) {
        clearError(field.wrap);
      });
      request(row.dataset.updateUrl, {
        title: titleField.input.value,
        amount: amountField.input.value,
        priority: priorityField.input.value,
        status: statusField.input.value,
      })
        .then(function () {
          editing = null;
          refreshBlocks(["purchase-lists"]);
        })
        .catch(function (error) {
          busy = false;
          const fields = {
            title: titleField,
            amount: amountField,
            priority: priorityField,
            status: statusField,
          };
          const field = fields[error.field] || amountField;
          showError(field.wrap, errorMessage(error));
          field.input.focus();
        });
    }

    editing = { row: row, save: save, cancel: cancel };
    buttons.save.addEventListener("click", save);
    buttons.cancel.addEventListener("click", cancel);
    titleField.input.focus();
    titleField.input.select();
  }

  /* --- правка взноса в карточке цели --- */

  function startContributionEdit(row) {
    dropOrphanEdit();
    if (editing || !row || !row.closest("#goal-body")) {
      return;
    }
    const dateCell = row.querySelector(".contribution-date");
    const commentCell = row.querySelector(".contribution-comment");
    const amountCell = row.querySelector(".contribution-amount");
    const actionsCell = row.querySelector(".row-actions");
    if (!dateCell || !commentCell || !amountCell || !actionsCell) {
      return;
    }
    const savedHtml = row.innerHTML;

    const dateInput = cellInput("date", "date-edit", row.dataset.date, "Дата");
    const amountInput = cellInput("number", "money-edit", row.dataset.amount, "Сумма, ₽");
    amountInput.step = "0.01";
    amountInput.min = "0.01";
    amountInput.inputMode = "decimal";
    const commentInput = cellInput("text", "comment-edit", row.dataset.comment, "Комментарий");
    commentInput.required = false;
    commentInput.maxLength = 200;

    dateCell.textContent = "";
    dateCell.appendChild(dateInput);
    commentCell.classList.remove("muted");
    commentCell.textContent = "";
    commentCell.appendChild(commentInput);
    amountCell.textContent = "";
    amountCell.appendChild(amountInput);
    actionsCell.textContent = "";

    const buttons = actionButtons();
    actionsCell.append(buttons.save, buttons.cancel);

    let busy = false;

    function cancel() {
      if (busy) {
        return;
      }
      editing = null;
      row.innerHTML = savedHtml;
      const button = row.querySelector(".contribution-edit");
      if (button) {
        button.focus();
      }
    }

    function save() {
      if (busy) {
        return;
      }
      busy = true;
      [dateCell, commentCell, amountCell].forEach(clearError);
      request(row.dataset.updateUrl, {
        date: dateInput.value,
        amount: amountInput.value,
        comment: commentInput.value,
      })
        .then(function () {
          editing = null;
          // Прогресс и итог тоже меняются - обновляем сводку и таблицу взносов.
          refreshBlocks(["goal-summary", "contribution-card"]);
        })
        .catch(function (error) {
          busy = false;
          const cells = {
            date: dateCell,
            amount: amountCell,
            comment: commentCell,
          };
          const cell = cells[error.field] || amountCell;
          showError(cell, errorMessage(error));
          const input = cell.querySelector("input");
          if (input) {
            input.focus();
          }
        });
    }

    editing = { row: row, save: save, cancel: cancel };
    buttons.save.addEventListener("click", save);
    buttons.cancel.addEventListener("click", cancel);
    amountInput.focus();
    amountInput.select();
  }

  /* --- кнопки: правка взноса --- */

  document.addEventListener("click", function (event) {
    const contributionButton = event.target.closest(".contribution-edit");
    if (contributionButton) {
      event.preventDefault();
      startContributionEdit(contributionButton.closest("tr"));
    }
  });

  document.addEventListener("dblclick", function (event) {
    const purchaseCell = event.target.closest("tr.purchase-row td");
    if (
      purchaseCell &&
      !purchaseCell.classList.contains("actions-cell") &&
      !purchaseCell.querySelector("input")
    ) {
      startPurchaseEdit(purchaseCell.closest("tr"));
      return;
    }
    const contributionCell = event.target.closest("tr.contribution-row td");
    if (
      contributionCell &&
      !contributionCell.classList.contains("actions-cell") &&
      !contributionCell.querySelector("input")
    ) {
      startContributionEdit(contributionCell.closest("tr"));
    }
  });

  document.addEventListener("keydown", function (event) {
    if (!editing || !editing.row.contains(event.target)) {
      return;
    }
    if (event.target.tagName === "SELECT") {
      // Не мешаем нативному списку статусов: Enter/Escape - его клавиши.
      return;
    }
    if (event.key === "Enter") {
      // Enter на кнопке - её собственное действие (Сохранить/Отмена).
      if (event.target.closest("button")) {
        return;
      }
      event.preventDefault();
      editing.save();
    } else if (event.key === "Escape") {
      editing.cancel();
    }
  });

  /* --- кнопки: смена статуса --- */

  document.addEventListener("click", function (event) {
    const button = event.target.closest(".js-status");
    if (!button) {
      return;
    }
    event.preventDefault();
    const scope = button.closest("[data-status-url]");
    const url = scope && scope.dataset.statusUrl;
    if (!url) {
      return;
    }
    // Статус меняет состав таблиц (цель уходит в "Куплено" или
    // возвращается) - обновляем разметку с сервера.
    button.disabled = true;
    request(url, { status: button.dataset.status })
      .then(function () {
        // На списке меняется состав таблиц, в карточке - только сводка.
        refreshBlocks(
          document.getElementById("purchase-lists")
            ? ["purchase-lists"]
            : ["goal-summary"]
        );
      })
      .catch(function (error) {
        button.disabled = false;
        window.alert("Не удалось сменить статус: " + errorMessage(error));
      });
  });
})();
