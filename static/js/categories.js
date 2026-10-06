/* Категории: перетаскивание порядка, добавление и переименование прямо в списке. */
(function () {
  "use strict";

  const list = document.getElementById("category-list");
  if (!list || typeof Sortable === "undefined") {
    return;
  }

  const status = document.getElementById("order-status");
  const addButton = document.getElementById("add-category");
  const createUrl = list.dataset.createUrl;
  const renameUrl = list.dataset.renameUrl;

  function getCookie(name) {
    const match = document.cookie.match(new RegExp("(^|;\\s*)" + name + "=([^;]*)"));
    return match ? decodeURIComponent(match[2]) : "";
  }

  function setStatus(text) {
    if (status) {
      status.textContent = text;
    }
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
            throw new Error(data.error || "Ошибка " + response.status);
          }
          return data;
        });
    });
  }

  function showError(cell, message) {
    clearError(cell);
    const error = document.createElement("span");
    error.className = "field-error";
    error.textContent = message;
    cell.appendChild(error);
  }

  function clearError(cell) {
    const error = cell.querySelector(".field-error");
    if (error) {
      error.remove();
    }
  }

  /* --- перетаскивание порядка --- */

  Sortable.create(list, {
    handle: ".drag-handle",
    animation: 150,
    onEnd: function () {
      const ids = Array.from(list.querySelectorAll("tr[data-id]")).map(function (row) {
        return Number(row.dataset.id);
      });
      setStatus("Сохраняю…");
      request(list.dataset.reorderUrl, { ids: ids })
        .then(function () {
          setStatus("Порядок сохранён");
        })
        .catch(function () {
          setStatus("Не удалось сохранить порядок — обновите страницу");
        });
    },
  });

  /* --- добавление --- */

  function buildRow(data) {
    const row = document.createElement("tr");
    row.dataset.id = String(data.id);

    const handle = document.createElement("td");
    handle.className = "drag-handle";
    handle.title = "Перетащите, чтобы изменить порядок";
    handle.textContent = "⠿";

    const nameCell = document.createElement("td");
    nameCell.className = "category-name";
    nameCell.title = "Двойной клик — переименовать";
    nameCell.textContent = data.name;

    const actions = document.createElement("td");
    actions.className = "actions-cell";
    const actionsBox = document.createElement("div");
    actionsBox.className = "row-actions";
    const form = document.createElement("form");
    form.method = "post";
    form.action = data.toggle_url;
    const csrf = document.createElement("input");
    csrf.type = "hidden";
    csrf.name = "csrfmiddlewaretoken";
    csrf.value = getCookie("csrftoken");
    const button = document.createElement("button");
    button.type = "submit";
    button.className = "link-button";
    button.textContent = "В архив";
    form.append(csrf, button);
    actionsBox.appendChild(form);
    actions.appendChild(actionsBox);

    row.append(handle, nameCell, actions);
    return row;
  }

  function openNewRow() {
    const existing = list.querySelector("tr.new-row");
    if (existing) {
      existing.querySelector("input").focus();
      return;
    }

    const row = document.createElement("tr");
    row.className = "new-row";

    const handle = document.createElement("td");
    handle.className = "drag-handle";

    const nameCell = document.createElement("td");
    nameCell.className = "category-name";
    const input = document.createElement("input");
    input.type = "text";
    input.className = "name-input";
    input.placeholder = "Название категории";
    input.maxLength = 100;
    nameCell.appendChild(input);

    const actions = document.createElement("td");
    actions.className = "actions-cell";

    row.append(handle, nameCell, actions);
    list.appendChild(row);

    let busy = false;

    function cancel() {
      busy = true;
      row.remove();
    }

    function save() {
      if (busy) {
        return;
      }
      const name = input.value.trim();
      if (!name) {
        cancel();
        return;
      }
      busy = true;
      clearError(nameCell);
      request(createUrl, { name: name })
        .then(function (data) {
          const note = document.querySelector(".empty-note");
          if (note) {
            note.remove();
          }
          list.replaceChild(buildRow(data), row);
        })
        .catch(function (error) {
          busy = false;
          showError(nameCell, error.message);
          input.focus();
        });
    }

    input.addEventListener("keydown", function (event) {
      if (event.key === "Enter") {
        event.preventDefault();
        save();
      } else if (event.key === "Escape") {
        cancel();
      }
    });
    input.addEventListener("blur", save);
    input.focus();
  }

  if (addButton) {
    addButton.addEventListener("click", openNewRow);
  }

  /* --- переименование по двойному клику (делегирование на весь список) --- */

  function startRename(cell) {
    const row = cell.closest("tr");
    const oldName = cell.textContent;
    cell.textContent = "";

    const input = document.createElement("input");
    input.type = "text";
    input.className = "name-input";
    input.value = oldName;
    input.maxLength = 100;
    cell.appendChild(input);
    input.focus();
    input.select();

    let busy = false;

    function restore() {
      busy = true;
      cell.textContent = oldName;
    }

    function save() {
      if (busy) {
        return;
      }
      const name = input.value.trim();
      if (!name || name === oldName) {
        restore();
        return;
      }
      busy = true;
      clearError(cell);
      request(renameUrl, { id: Number(row.dataset.id), name: name })
        .then(function (data) {
          cell.textContent = data.name;
        })
        .catch(function (error) {
          busy = false;
          showError(cell, error.message);
          input.focus();
        });
    }

    input.addEventListener("keydown", function (event) {
      if (event.key === "Enter") {
        event.preventDefault();
        save();
      } else if (event.key === "Escape") {
        restore();
      }
    });
    input.addEventListener("blur", save);
  }

  list.addEventListener("dblclick", function (event) {
    const cell = event.target.closest(".category-name");
    if (!cell || cell.querySelector("input")) {
      return;
    }
    startRename(cell);
  });
})();
