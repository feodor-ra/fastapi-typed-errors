---
title: Обзор
---

# fastapi-typed-errors

**Типизированные HTTP-ошибки для FastAPI.** Точные `Literal`-коды в OpenAPI, discriminated `oneOf`-union по полю `code` и единый источник правды — сам класс ошибки.

---

## Зачем это нужно

В обычном FastAPI ошибка — это `HTTPException(404, "...")`. Код ошибки живёт в строке, в OpenAPI нет ни типа кода, ни модели тела ответа, а список возможных ошибок роута приходится вручную дублировать в `responses={}`. Клиент не может переключиться по коду, а документация быстро расходится с кодом.

`fastapi-typed-errors` делает ошибку **классом**: HTTP-статус, машинный код и модель ответа объявляются один раз и выводятся автоматически.

=== "Было"

    ```python
    @app.get("/items/{item_id}")
    def get_item(item_id: int):
        if item_id == 0:
            raise HTTPException(404, "No item")  # (1)!
        return {"item_id": item_id}
    ```

    1. Код ошибки — просто строка в `detail`; в OpenAPI у 404 нет ни точного кода, ни схемы тела.

=== "Стало"

    ```python
    class NotFoundError(BaseError[Literal[ErrorCode.NOT_FOUND]]):
        http_status = HTTPStatus.NOT_FOUND


    @router.get("/items/{item_id}")
    def get_item(item_id: int) -> Annotated[Item, Raises[NotFoundError]]:  # (1)!
        if item_id == 0:
            raise NotFoundError("No item")
        return Item(item_id=item_id)
    ```

    1. Задекларированная ошибка попадает в `responses` автоматически: 404 с точным `Literal["NOT_FOUND"]` и телом `{code, detail}`.

=== "…или с auto-магией"

    ```python
    router = with_errors(APIRouter(), auto=True)  # (1)!


    @router.get("/items/{item_id}")
    def get_item(item_id: int) -> Item:  # (2)!
        if item_id == 0:
            raise NotFoundError("No item")
        return Item(item_id=item_id)
    ```

    1. Включаем авто-заполнение один раз на роутере.
    2. Ни одного маркера — `responses` соберутся сами: обходчик найдёт `raise NotFoundError` (и ошибки из зависимостей) статически. См. [auto=True](guide/decorator.md#auto).

Тело ответа всегда предсказуемо:

```json
{ "code": "NOT_FOUND", "detail": "No item" }
```

А в OpenAPI роут получает по записи на каждый статус — с точным кодом и моделью тела. Вот как это отображается в Swagger UI:

![Панель Responses в Swagger UI: 200 → Item, 403 → ErrorResponse[FORBIDDEN], 404 → oneOf ErrorResponse[NOT_FOUND] / ErrorResponse[GONE] с дискриминатором по code](assets/swagger-responses.svg){ .fte-shot }

## Возможности

<div class="grid cards" markdown>

-   :material-shield-check: **Единый источник правды**

    ---

    Статус, код и модель ответа объявляются один раз в классе ошибки. Метакласс выводит остальное.

    [:octicons-arrow-right-24: Ядро](guide/core.md)

-   :material-code-braces: **Точные типы в OpenAPI**

    ---

    Каждый статус получает точный `Literal`-код; несколько ошибок на статус — discriminated `oneOf`-union по `code`.

    [:octicons-arrow-right-24: error_models](guide/core.md#error_models)

-   :material-tag-arrow-up: **Декларация прямо в аннотации**

    ---

    `-> Annotated[Item, Raises[NotFoundError, ForbiddenError]]` — и `responses` заполняются сами.

    [:octicons-arrow-right-24: Декоратор](guide/decorator.md)

-   :material-radar: **CI-проверка контрактов**

    ---

    `check_raises` сверяет задекларированное с реально поднимаемым — в эндпоинте и его зависимостях.

    [:octicons-arrow-right-24: CI-checker](guide/checker.md)

-   :material-auto-fix: **Авто-заполнение**

    ---

    `with_errors(router, auto=True)` находит ошибки статически и заполняет `responses` без единого маркера.

    [:octicons-arrow-right-24: auto=True](guide/decorator.md#auto)

-   :material-puzzle: **Расширяемость**

    ---

    Своя модель ответа-конверта, свои коды (`StrEnum` или голый `Literal`), совместимость с `ABC`.

    [:octicons-arrow-right-24: Кастомизация](guide/customization.md)

</div>

## Установка

=== "uv"

    ```bash
    uv add fastapi-typed-errors
    # с CLI для CI-проверки:
    uv add "fastapi-typed-errors[cli]"
    ```

=== "pip"

    ```bash
    pip install fastapi-typed-errors
    pip install "fastapi-typed-errors[cli]"
    ```

!!! info "Требования"

    - Python **3.12+** (PEP 695-дженерики)
    - FastAPI **≥ 0.115** (версии `0.137`–`0.138` исключены — см. [Ограничения](guide/limitations.md#fastapi))
    - Pydantic **≥ 2.9**

## Дальше

<div class="grid cards" markdown>

-   :material-rocket-launch: **[Быстрый старт](quickstart.md)** — рабочее приложение за минуту.
-   :material-book-open-variant: **[Руководство](guide/core.md)** — концепции, декоратор, checker, расширение.
-   :material-api: **[Справочник API](reference/core.md)** — сигнатуры из docstring-ов.

</div>
