---
title: Рецепты
---

# Рецепты

Готовые паттерны для частых задач.

## Общий кортеж ошибок авторизации

Ошибки токена/авторизации обычно одни и те же на многих роутах. Вынесите их в кортеж и распаковывайте маркером:

```python
from typing import Final

TOKEN_ERRORS: Final = (RequiredTokenError, InvalidTokenError, WrongTokenTypeError)


@router.get("/me")
def me(user: Annotated[User, Depends(current_user)]) -> Annotated[User, Raises[*TOKEN_ERRORS]]: ...
```

Все три кода на `401` автоматически станут discriminated `oneOf`-union.

## Ошибки зависимостей без ручной декларации

Если ошибки авторизации живут в зависимостях (`Depends`), включите [`auto=True`](decorator.md#auto) — и не декларируйте их вовсе:

```python
router = with_errors(APIRouter(), auto=True)


def current_user(token: Annotated[str, Depends(oauth)]) -> User:
    if invalid(token):
        raise InvalidTokenError("плохой токен")  # найдётся автоматически
    ...


@router.get("/me")
def me(user: Annotated[User, Depends(current_user)]) -> User:
    return user  # 401 из зависимости попадёт в responses сам
```

## Фабрика `get_or_404`

Частый паттерн — общий хелпер, поднимающий переданный класс ошибки:

```python
def get_or_404[M](value: M | None, *, error: type[BaseError[Any]]) -> M:
    if value is None:
        raise error("не найдено")
    return value


@router.get("/items/{item_id}")
def get_item(item_id: int) -> Annotated[Item, Raises[NotFoundError]]:
    item = get_or_404(repo.find(item_id), error=NotFoundError)
    return item
```

Обходчик (`auto` и `check_raises`) понимает эту фабрику: класс ошибки, переданный **аргументом вызова**, засчитывается как потенциально поднимаемый.

## Тестирование контрактов ошибок

Одна строка в тесте гарантирует, что декларации не разошлись с кодом:

```python
from fastapi_typed_errors import check_raises


def test_error_contracts() -> None:
    assert check_raises(app).ok
```

Полное тело ответа тоже легко проверить через `TestClient`:

```python
def test_not_found() -> None:
    response = TestClient(app).get("/items/0")
    assert response.status_code == 404
    assert response.json() == {"code": "NOT_FOUND", "detail": "нет"}
```

## Приложение целиком

Оберните роутер приложения, чтобы декораторы `app.get(...)` тоже понимали `Raises`:

```python
app = FastAPI()
app.add_exception_handler(BaseError, handle_base_error)
with_errors(app.router, auto=True)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

---

**Дальше:** [Ограничения](limitations.md) — что вне области видимости и почему.
