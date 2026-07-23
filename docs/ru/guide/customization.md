---
title: Кастомизация
---

# Кастомизация и расширение

## Своя модель ответа

По умолчанию тело ошибки — `{code, detail}`. Чтобы добавить свои поля (например, конверт со `status`), наследуйте `ErrorResponse` дженерик-подклассом и укажите его в `response_base` своего базового класса ошибок.

```python
from typing import Any, ClassVar, Literal

from fastapi_typed_errors import BaseError, ErrorResponse


class MyErrorResponse[T: str](ErrorResponse[T]):
    status: Literal["error"] = "error"  # (1)!


class AppError[T: str](BaseError[T]):
    response_base: ClassVar[type[ErrorResponse[Any]]] = MyErrorResponse


class NotFoundError(AppError[Literal["NOT_FOUND"]]):
    http_status = HTTPStatus.NOT_FOUND
```

1. Дополнительное поле встаёт **рядом** с `code`/`detail`.

Тело ответа станет:

```json
{ "status": "error", "code": "NOT_FOUND", "detail": "..." }
```

!!! danger "Только плоское расширение"

    Форма должна оставаться **плоской**. Вложенные конверты вида `{"status": ..., "data": {"code": ...}}` не поддерживаются: pydantic-овские discriminated union требуют, чтобы дискриминатор `code` был на **верхнем уровне** модели, иначе `error_models()` для нескольких ошибок на одном статусе сломается.

## Голые строковые коды

Enum приносите свой — но он не обязателен. Код может быть голой строкой в `Literal`:

```python
class BareError(BaseError[Literal["BARE_CODE"]]):
    http_status = HTTPStatus.CONFLICT
```

`StrEnum` удобнее, когда кодов много и хочется единый реестр; голый `Literal` — для разовых случаев.

## description и заголовки

- `description: ClassVar[str | None]` — дефолтный `detail` и описание статуса в OpenAPI.
- Заголовки прокидываются в `HTTPException`:

```python
class RequiredTokenError(BaseError[Literal["REQUIRED_TOKEN"]]):
    http_status = HTTPStatus.UNAUTHORIZED
    description = "Требуется токен"


raise RequiredTokenError(headers={"WWW-Authenticate": "Bearer"})
```

## Промежуточные базы

Общую конфигурацию (свой `response_base`, общий префикс кодов) выносите в промежуточную дженерик-базу — она параметризуется `TypeVar` и **не** обязана объявлять код:

```python
class AppError[T: str](BaseError[T]):
    response_base = MyErrorResponse
    # http_status здесь не нужен — это не конкретная ошибка


class NotFoundError(AppError[Literal["NOT_FOUND"]]):
    http_status = HTTPStatus.NOT_FOUND
```

Метакласс пропускает базы, параметризованные `TypeVar`, и выводит `error_code`/`model` только у конкретных подклассов.

## Совместимость с ABC { #abc }

`BaseError` наследует `HTTPException` и использует метакласс `BaseErrorMeta`. Если смешать его с `ABC` (у которого свой `ABCMeta`), Python выдаст конфликт метаклассов. Решение — комбинированный метакласс:

```python
from abc import ABCMeta, abstractmethod
from fastapi_typed_errors.core.base import BaseErrorMeta  # (1)!


class ABCErrorMeta(BaseErrorMeta, ABCMeta): ...


class AbstractError[T: str](BaseError[T], metaclass=ABCErrorMeta):
    @abstractmethod
    def audit(self) -> None: ...
```

1. `BaseErrorMeta` намеренно **не** реэкспортируется из корня пакета — импортируйте из `fastapi_typed_errors.core.base`.

## Явная регистрация — это принцип

Пакет не прячет магию за `install(app)`-хелперами. Обработчик вешается руками:

```python
app.add_exception_handler(BaseError, handle_base_error)
```

Это тот же стиль, что `app.add_middleware(...)`: настройка приложения остаётся явной и под вашим контролем.

---

**Дальше:** [Рецепты](recipes.md) — частые практические паттерны.
