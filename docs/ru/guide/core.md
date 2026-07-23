---
title: Ядро
---

# Ядро

Слой `core` самодостаточен: его можно использовать без декоратора и без анализа. Он даёт четыре вещи — класс ошибки `BaseError`, модель ответа `ErrorResponse`, конструктор `error_models()` для `responses={}` и обработчик `handle_base_error`.

## BaseError

Каждая ошибка — подкласс `BaseError`, параметризованный своим кодом. Код передаётся как `Literal` в дженерик-параметр; в теле класса объявляется только `http_status`.

```python
from enum import StrEnum
from http import HTTPStatus
from typing import Literal

from fastapi_typed_errors import BaseError


class ErrorCode(StrEnum):
    NOT_FOUND = "NOT_FOUND"


class NotFoundError(BaseError[Literal[ErrorCode.NOT_FOUND]]):
    http_status = HTTPStatus.NOT_FOUND
    description = "Сущность не найдена"  # (1)!
```

1. `description: ClassVar[str | None]` — необязательный; см. [detail по умолчанию](#detail).

Метакласс `BaseErrorMeta` при создании класса извлекает код из дженерик-параметра и **выводит** два атрибута класса:

| Атрибут | Что это |
|---|---|
| `NotFoundError.error_code` | значение кода (`ErrorCode.NOT_FOUND`) |
| `NotFoundError.model` | параметризованная модель ответа `ErrorResponse[Literal[NOT_FOUND]]` |

`BaseError` наследует `fastapi.HTTPException`, поэтому `raise NotFoundError(...)` работает как обычное исключение FastAPI.

### Коды: StrEnum или голый Literal

Код — это любой член `StrEnum` **или** голая строка в `Literal`. Bound `T: str` покрывает оба варианта:

```python
class NotFoundError(BaseError[Literal[ErrorCode.NOT_FOUND]]): ...  # член StrEnum


class BareError(BaseError[Literal["BARE_CODE"]]): ...  # голая строка
```

!!! warning "Ошибка параметризации ловится сразу"

    Параметризация чем-либо, кроме `TypeVar` (промежуточная база) или `Literal` с ровно одной строкой, падает с `TypeError` **в момент определения класса**, а не опасной 500-й на запросе:

    ```python
    class Bad(BaseError[str]): ...  # TypeError: BaseError expects Literal with exactly one string code
    ```

### detail по умолчанию

Если при подъёме не передать `detail`, он берётся из `description`, а при его отсутствии — из фразы HTTP-статуса.

```python
NotFoundError().detail  # -> "Сущность не найдена" (из description)
ForbiddenError().detail  # -> "Forbidden" (фраза статуса, если description нет)
NotFoundError("нет").detail  # -> "нет" (явный detail побеждает)
```

Заголовки прокидываются в `HTTPException`:

```python
raise RequiredTokenError(headers={"WWW-Authenticate": "Bearer"})
```

## ErrorResponse

Тело ответа — модель `ErrorResponse[T]` с двумя полями:

```python
class ErrorResponse[T: str](BaseModel):
    code: T  # точный Literal-код
    detail: str
```

`to_response()` строит её из экземпляра ошибки — это и делает обработчик:

```python
NotFoundError("нет").to_response().model_dump()
# {"code": "NOT_FOUND", "detail": "нет"}
```

!!! note "Чистые заголовки в OpenAPI"

    Pydantic по умолчанию встраивает в тайтл параметризованной модели `repr()` enum-члена — с угловыми скобками. Пакет ставит `model_title_generator`, который рендерит `ErrorResponse[NOT_FOUND]` вместо `ErrorResponse[Literal[<ErrorCode.NOT_FOUND: 'NOT_FOUND'>]]`.

## error_models()

`error_models()` строит модель для ключа `"model"` в `responses={}` роута.

```python
from fastapi_typed_errors import error_models
```

- **Один класс** → его параметризованная модель напрямую.
- **Несколько классов** → discriminated `oneOf`-union по полю `code` (Swagger покажет выбор по коду).

```python
@app.get(
    "/items/{item_id}",
    responses={
        404: {"model": error_models(NotFoundError)},  # одна модель
        403: {"model": error_models(ForbiddenError, GoneError)},  # oneOf-union
    },
)
def get_item(item_id: int) -> Item: ...
```

Union из двух ошибок на одном статусе даёт в OpenAPI `oneOf` с дискриминатором — Swagger UI покажет выпадающий выбор варианта по коду:

```json
{
  "oneOf": [
    { "$ref": "#/components/schemas/ErrorResponse_Literal_FORBIDDEN__" },
    { "$ref": "#/components/schemas/ErrorResponse_Literal_GONE__" }
  ],
  "discriminator": {
    "propertyName": "code",
    "mapping": {
      "FORBIDDEN": "#/components/schemas/ErrorResponse_Literal_FORBIDDEN__",
      "GONE": "#/components/schemas/ErrorResponse_Literal_GONE__"
    }
  }
}
```

Повторяющиеся классы дедуплицируются. А вот один код у двух **разных** моделей внутри union невозможен — дискриминатор требует уникальных значений:

```python
error_models(NotFoundError, AnotherWithSameCode)
# TypeError: error code 'NOT_FOUND' is shared by multiple distinct response models
```

!!! tip "Ручной способ всегда доступен"

    Слой `core` не требует декоратора. `error_models()` можно вписывать в `responses={}` руками — это и есть «core-only» режим. Декоратор ([`with_errors`](decorator.md)) просто избавляет от этой ручной работы.

## Обработчик

`handle_base_error` — единый обработчик для всех `BaseError`. Регистрируется явно:

```python
from fastapi_typed_errors import BaseError, handle_base_error

app.add_exception_handler(BaseError, handle_base_error)
```

Он отдаёт `JSONResponse` со статусом, телом `{code, detail}` и заголовками ошибки.

!!! info "Почему сигнатура `(Request, Exception)`"

    Starlette типизирует обработчик как `(Request, Exception) -> ...`, а параметры функций контравариантны — узкий `BaseError` заставил бы вешать `# type: ignore` на строку регистрации у **каждого** потребителя. Поэтому сигнатура широкая, а неправильная регистрация (на чужой тип исключения) ловится в рантайме внятным `TypeError`.

Плоский `HTTPException` не перехватывается: Starlette идёт по `__mro__`, и обработчик `BaseError` перекрывает дефолтный только для своих подклассов.

## BaseErrorMeta

Метакласс публичен — на случай, если вы смешиваете `BaseError` с `ABC` или другим кастомным метаклассом (иначе будет конфликт метаклассов). Он **намеренно не реэкспортируется** из корня пакета; импортируйте из `core.base`:

```python
from abc import ABCMeta
from fastapi_typed_errors.core.base import BaseErrorMeta


class Meta(BaseErrorMeta, ABCMeta): ...
```

Подробности — в разделе [Кастомизация](customization.md#abc).

---

**Дальше:** [декоратор](decorator.md) — как перестать писать `responses={}` руками.
