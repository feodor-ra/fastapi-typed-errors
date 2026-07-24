# fastapi-typed-errors

[English](README.md) · **Русский**

[![PyPI - Version](https://img.shields.io/pypi/v/fastapi-typed-errors)](https://pypi.org/project/fastapi-typed-errors/)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/fastapi-typed-errors)
![PyPI - Status](https://img.shields.io/pypi/status/fastapi-typed-errors)
![PyPI - Downloads](https://img.shields.io/pypi/dm/fastapi-typed-errors)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Pydantic v2](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/pydantic/pydantic/main/docs/badge/v2.json)](https://pydantic.dev)

![GitHub Release](https://img.shields.io/github/v/release/feodor-ra/fastapi-typed-errors)
![GitHub Repo stars](https://img.shields.io/github/stars/feodor-ra/fastapi-typed-errors?style=flat)
![GitHub last commit](https://img.shields.io/github/last-commit/feodor-ra/fastapi-typed-errors)
[![CI](https://github.com/feodor-ra/fastapi-typed-errors/actions/workflows/ci.yml/badge.svg)](https://github.com/feodor-ra/fastapi-typed-errors/actions/workflows/ci.yml)
[![Coverage Status](https://coveralls.io/repos/github/feodor-ra/fastapi-typed-errors/badge.svg?branch=main)](https://coveralls.io/github/feodor-ra/fastapi-typed-errors?branch=main)
[![Docs](https://img.shields.io/badge/docs-mkdocs-blue)](https://feodor-ra.github.io/fastapi-typed-errors/ru/)

**Типизированные HTTP-ошибки для FastAPI** — точные `Literal`-коды в OpenAPI, discriminated `oneOf`-union по полю `code` и единый источник правды: сам класс ошибки.

В обычном FastAPI `raise HTTPException(404, "...")` прячет код ошибки в строку — клиент не может по нему переключиться, в OpenAPI нет ни типа кода, ни схемы тела, а `responses={}` приходится вести руками на каждом роуте. Этот пакет делает ошибку **классом**: её HTTP-статус, машинный код и модель ответа объявляются один раз и выводятся автоматически, так что контракт ошибок становится типизированным, самодокументируемым и проверяемым в CI.

```python
class NotFoundError(BaseError[Literal[ErrorCode.NOT_FOUND]]):
    http_status = HTTPStatus.NOT_FOUND


@router.get("/items/{item_id}")
def get_item(item_id: int) -> Annotated[Item, Raises[NotFoundError]]:
    if item_id == 0:
        raise NotFoundError("No item")
    return Item(item_id=item_id)
```

Тело ответа всегда `{"code": "NOT_FOUND", "detail": "No item"}`, а в OpenAPI роут получает `404` с **точным** кодом `Literal["NOT_FOUND"]` и моделью тела — без ручного `responses`.

## Установка

```bash
pip install fastapi-typed-errors          # ядро + декоратор
pip install "fastapi-typed-errors[cli]"   # + CLI для CI-проверки
```

Требуется Python **3.12+**, FastAPI **≥ 0.115**, Pydantic **≥ 2.9**.

## Как это использовать

**1. Объявите ошибки и зарегистрируйте единственный обработчик.**

```python
from fastapi import FastAPI
from fastapi_typed_errors import BaseError, handle_base_error

app = FastAPI()
app.add_exception_handler(BaseError, handle_base_error)
```

**2. Декларируйте ошибки — выберите уровень магии:**

```python
# а) руками (только ядро) — responses пишете сами
@app.get("/x", responses={404: {"model": error_models(NotFoundError)}})
def a() -> Item: ...


# б) декларативно — маркер заполняет responses за вас
router = with_errors(APIRouter())


@router.get("/y")
def b() -> Annotated[Item, Raises[NotFoundError, ForbiddenError]]: ...


# в) автоматически — вообще без маркеров; ошибки находятся статически
router = with_errors(APIRouter(), auto=True)


@router.get("/z")
def c(user: Annotated[User, Depends(current_user)]) -> Item:
    raise NotFoundError("...")  # auto -> 404, плюс всё, что поднимает current_user
```

**3. Проверьте контракт в CI.** `check_raises` сверяет, что каждый роут *декларирует*, с тем, что он реально может *поднять* — в эндпоинте и во всём дереве зависимостей:

```python
def test_error_contracts() -> None:
    assert check_raises(app).ok
```

Или как команда: `fastapi-typed-errors check app.main:app` (exit `0`/`1`/`2`).

## Почему это круто

- **Точные типы в OpenAPI** — точный `Literal`-код на каждый статус; несколько ошибок на одном статусе становятся discriminated `oneOf`-union, и Swagger UI показывает выбор варианта по коду.
- **Единый источник правды** — статус, код и модель объявляются один раз; остальное выводит метакласс.
- **Ноль бойлерплейта в `responses`** — через маркер `Raises` или полностью автоматический `auto=True`.
- **Статическая проверка контракта** — `check_raises` ловит забытую декларацию (или мёртвую) ещё до релиза.
- **Не инвазивно** — `with_errors` патчит роутер на месте и сохраняет идентичность объекта, поэтому `include_router`, websockets и декораторы приложения продолжают работать нативно.
- **Строго** — полностью типизирован (`py.typed`), 100% покрытие по веткам, проверка `ruff` + `ty` на максимальной строгости.

## Документация

📖 **[Полная документация](https://feodor-ra.github.io/fastapi-typed-errors/ru/)** — руководство, кастомизация (свои конверты, `ABC`, голые строковые коды), ограничения и авто-генерируемый справочник API. Доступна на английском и русском.

## Лицензия

[MIT](LICENSE).

---

[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![ty](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ty/main/assets/badge/v0.json)](https://github.com/astral-sh/ty)
[![pytest](https://img.shields.io/badge/tested_with-pytest-0A9EDC?logo=pytest&logoColor=white)](https://docs.pytest.org/)
[![Material for MkDocs](https://img.shields.io/badge/Material_for_MkDocs-526CFE?logo=materialformkdocs&logoColor=white)](https://squidfunk.github.io/mkdocs-material/)
[![Conventional Commits](https://img.shields.io/badge/Conventional_Commits-1.0.0-FE5196?logo=conventionalcommits&logoColor=white)](https://www.conventionalcommits.org)
[![Semantic Versions](https://img.shields.io/badge/%20%20%F0%9F%93%A6%F0%9F%9A%80-semantic--versions-e10079.svg)](https://github.com/feodor-ra/fastapi-typed-errors/releases)

![GitHub License](https://img.shields.io/github/license/feodor-ra/fastapi-typed-errors)
