# static/ — статика

- `css/style.css` — базовые стили сайта;
- `js/categories.js` — перетаскивание категорий;
- `js/vendor/` — сторонние библиотеки (SortableJS; версия и sha256 —
  в `js/vendor/README.md`); графики (Chart.js) позже добавим сюда же локально;
- `img/` — иконки и фавикон.

В продакшене статика собирается `collectstatic` и раздаётся WhiteNoise;
собранный каталог (`staticfiles/`) в git не попадает.
