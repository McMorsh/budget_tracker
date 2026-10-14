# static/ - статика

- `css/style.css` - базовые стили сайта;
- `js/categories.js` - перетаскивание категорий;
- `js/expenses.js` - ввод и инлайн-правка трат;
- `js/month.js` - живой пересчёт плана месяца;
- `js/reports.js` - графики отчётов;
- `js/vendor/` - сторонние библиотеки (SortableJS, Chart.js; версии и sha256 -
  в `js/vendor/README.md`);
- `img/` - иконки и фавикон.

В продакшене статика собирается `collectstatic` и раздаётся WhiteNoise;
собранный каталог (`staticfiles/`) в git не попадает.
