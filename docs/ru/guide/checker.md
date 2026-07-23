---
title: CI-checker
---

# CI-checker: check_raises

Аннотации `Raises[...]` — это декларация. `check_raises` статически проверяет, что декларация **совпадает** с тем, что роут реально может поднять — в самом эндпоинте, его хелперах и во всём дереве зависимостей. Это закрывает разрыв, который аннотации оставляют открытым: забытая декларация или мёртвая, которую больше не поднимают.

## Библиотечное использование

Идеально ложится в тест:

```python
from fastapi_typed_errors import check_raises


def test_error_contracts() -> None:
    report = check_raises(app)  # FastAPI-приложение или APIRouter
    assert report.ok, report.routes
```

`check_raises` возвращает [`RaisesReport`](../reference/analysis.md) со свойством `.ok` и списком расхождений `.routes`.

## Две категории расхождений

Каждый `RouteDiscrepancy` содержит две **независимые** корзины:

| Категория | Что значит | По умолчанию |
|---|---|---|
| `undeclared` | ошибка поднимается в коде, но её нет в `Raises` | **всегда провал** |
| `overdeclared` | ошибка задекларирована, но её подъём не найден | провал (отключается флагом) |

```python
report = check_raises(app)
for route in report.routes:
    print(route.path, route.methods)
    print("  не задекларированы:", [e.__name__ for e in route.undeclared])
    print("  лишние декларации:", [e.__name__ for e in route.overdeclared])
```

Так как AST-анализ консервативен (динамические `raise` он может не увидеть), `overdeclared` иногда даёт ложное срабатывание. Тогда отключите эту корзину:

```python
report = check_raises(app, allow_overdeclared=True)  # игнорировать лишние декларации
```

!!! tip "Оставляйте overdeclared включённым, если можете"

    Он ловит мёртвые декларации, которые копятся в OpenAPI. Прибегайте к `allow_overdeclared=True` только для кода с динамическими `raise`, которые обходчик не видит.

## CLI

Та же проверка как команда — удобно в CI-пайплайне. Нужен extra `cli`:

```bash
pip install "fastapi-typed-errors[cli]"
```

Указывается путь к приложению в форме `module:attribute`:

```bash
fastapi-typed-errors check app.main:app
```

=== "Совпадение (exit 0)"

    ```console
    $ fastapi-typed-errors check app.main:app
    All 12 route(s) match their Raises declarations.
    ```

=== "Расхождения (exit 1)"

    ```console
    $ fastapi-typed-errors check app.main:app
    ┏━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┓
    ┃ Route           ┃ Undeclared     ┃ Overdeclared  ┃
    ┡━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━┩
    │ GET /items      │ ForbiddenError │ -             │
    └─────────────────┴────────────────┴───────────────┘
    1 of 12 route(s) have discrepancies.
    ```

Флаги: `--allow-overdeclared`, `--max-depth N`.

Коды выхода:

| Код | Значение |
|---|---|
| `0` | все декларации совпадают |
| `1` | найдены расхождения (таблица) |
| `2` | ошибка использования/загрузки (плохой путь, не приложение, нерезолвящийся `Raises`) |

## Что именно сверяется

- **Задекларировано** — объединение маркеров `Raises[...]` из return-аннотации эндпоинта. Читается напрямую из аннотаций, поэтому работает **независимо** от того, обёрнут ли роутер `with_errors`.
- **Поднимается** — `raise`-выражения из исходников эндпоинта **плюс** каждого узла дерева `Depends` (security-схемы пропускаются).

Обходчик понимает фабричный паттерн `get_or_404(error=NotFoundError)` (класс ошибки приходит аргументом вызова), замыкания, кросс-модульные хелперы и `functools.partial`. Он работает в одном процессе и **никогда не исполняет** ваш код. Про ложные пропуски (локальные переменные, `self.method()`-цепочки, динамика) — см. [Ограничения](limitations.md#walker).

!!! example "GitHub Actions"

    ```yaml
    - run: uv run fastapi-typed-errors check app.main:app
    ```

    Или запускайте через тест `assert check_raises(app).ok` — тогда отдельная CLI-зависимость не нужна.

---

**Дальше:** [Кастомизация](customization.md) — своя модель ответа, коды, совместимость с `ABC`.
