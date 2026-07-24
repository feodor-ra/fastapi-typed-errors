---
title: Декоратор
---

# Декоратор: with_errors и Raises

Слой `decorator` избавляет от ручного `responses={}`. Ошибки объявляются прямо в return-аннотации эндпоинта маркером `Raises`, а `with_errors` заполняет `responses` на регистрации.

## with_errors

`with_errors(router)` возвращает **тот же** объект `APIRouter`, подменив его `add_api_route` на месте (instance patch), и учит понимать `Raises`.

```python
from fastapi import APIRouter
from fastapi_typed_errors import with_errors

router = with_errors(APIRouter())
```

!!! abstract "Почему тот же объект, а не обёртка"

    В FastAPI 0.139 ленивый `include_router` сравнивает включённый роутер **по идентичности** (`included_router.original_router is self`). Любая утиная обёртка проходит генерацию OpenAPI, но молча даёт 404 в рантайме. Сохранение идентичности заставляет `include_router`, websockets, декораторы приложения и императивную регистрацию работать нативно на любой версии FastAPI.

Единая точка перехвата — `add_api_route`, куда сходятся все 8 глаголов-декораторов, `api_route` и методы `app.*`. Для приложения оборачивайте его роутер:

```python
with_errors(app.router)
```

Патч **идемпотентен**: повторный `with_errors` — no-op.

!!! warning "Оборачивайте до регистрации"

    Роуты, добавленные в роутер **до** `with_errors(router)`, не дооснащаются. Сначала оборачиваем — потом регистрируем.

## Маркер Raises

`Raises[...]` — инертные метаданные `Annotated` в return-аннотации. Он перечисляет ошибки, которые роут может поднять.

```python
from typing import Annotated
from fastapi_typed_errors import Raises


@router.get("/items/{item_id}")
def get_item(item_id: int) -> Annotated[Item, Raises[NotFoundError, ForbiddenError]]:
    if item_id == 0:
        raise NotFoundError("нет")
    return Item(item_id=item_id)
```

Успешная (`200`) схема остаётся чистой — pydantic игнорирует маркер. Несколько ошибок на одном статусе становятся discriminated `oneOf`-union.

### Формы записи, переиспользование и композиция

Объявлять ошибки можно несколькими способами, и они свободно комбинируются. Выбирайте тот, что читается лучше на месте вызова.

**Инлайн-список** — разовый набор ошибок прямо на роуте:

```python
def get_item(item_id: int) -> Annotated[Item, Raises[NotFoundError, ForbiddenError]]: ...
```

**Общий кортеж** — повторяющийся набор выносим в кортеж и распаковываем, субскрипцией или через конструктор:

```python
from typing import Final

TOKEN_ERRORS: Final = (RequiredTokenError, InvalidTokenError, WrongTokenTypeError)


# обе формы эквивалентны:
def a() -> Annotated[Item, Raises[*TOKEN_ERRORS]]: ...
def b() -> Annotated[Item, Raises(*TOKEN_ERRORS)]: ...
```

Конструкторная форма `Raises(*TOKEN_ERRORS)` — статически «чистая» запасная для тайпчекеров.

**Именованный алиас-маркер** — дайте доменному набору ошибок имя через PEP 695 `type`-алиас и переиспользуйте его на многих роутах (и даже на разных роутерах):

```python
type AuthErrors = Raises[RequiredTokenError, InvalidTokenError, WrongTokenTypeError]


def me() -> Annotated[User, AuthErrors]: ...
def stats() -> Annotated[Stats, AuthErrors, Raises[RateLimitedError]]: ...  # общий набор + локальная
```

**Композиция** — поставьте несколько маркеров рядом в одном `Annotated`: общий набор плюс специфичные для роута ошибки. Они **конкатенируются и дедуплицируются**, так что пересечение маркеров безвредно:

```python
def transfer() -> Annotated[Account, AuthErrors, OwnershipErrors, Raises[ConflictError]]: ...
```

| Когда | Что использовать |
| --- | --- |
| Разовый набор на одном роуте | инлайн `Raises[A, B]` |
| Повторяющийся набор, распаковка ad-hoc | `Raises[*TUPLE]` / `Raises(*TUPLE)` (статически «чистая») |
| Именованный доменный набор для широкого переиспользования | `type AuthErrors = Raises[...]` |
| Общий набор + локальные добавки на роуте | композиция маркеров: `Annotated[T, AuthErrors, Raises[C]]` |

!!! note "Валидация — на этапе импорта"

    `Raises[...]` проверяет каждый член сразу при вычислении (то есть при импорте модуля): это должен быть подкласс `BaseError` с объявленными `error_code` и `http_status`, список непуст. Иначе — `TypeError` с именем нарушителя.

### Что видит `Raises` в аннотации

Маркер находится сквозь PEP 695 `type`-алиасы (оборачивающие как всю аннотацию, так и **сам маркер** в позиции метаданных), вложенные `Annotated`-базы и члены union — задекларированный маркер **никогда не теряется молча**:

```python
type ItemNF = Annotated[Item, Raises[NotFoundError]]
type CommonRaises = Raises[NotFoundError, ForbiddenError]


def a() -> ItemNF: ...  # алиас всей аннотации
def b() -> Annotated[Item, Raises[NotFoundError]] | None: ...  # union-обёртка
def c() -> Annotated[Item, CommonRaises, Raises[ConflictError]]: ...  # алиас-маркер в метаданных
def d() -> Annotated[ItemNF, Raises[ConflictError]]: ...  # алиас-аннотация, вложенная в другую
```

## Семантика слияния

Что попадает в итоговый `responses`:

- **Маркеры `Raises`** и (при `auto=True`) **найденные обходчиком** ошибки — объединяются.
- **Явный `responses={<status>: ...}`** на роуте побеждает выведенные записи **целиком по этому статусу** (без слияния моделей). Используйте `int`-ключи статусов.
- Router-level `responses` домердживает сам FastAPI и проигрывает per-route.

```python
@router.get("/x", responses={404: {"description": "Своё описание", "model": MyModel}})
def endpoint() -> Annotated[Item, Raises[NotFoundError]]:  # 404 возьмётся из responses, не из Raises
    ...
```

Описания статусов берутся из `description` классов; несколько на статус — склеиваются через `;`, fallback — фраза HTTP-статуса.

## Нормализация Response и None

`-> Annotated[Response-подкласс, Raises[...]]` и `-> Annotated[None, Raises[...]]` нормализуются в `response_model=None` — иначе FastAPI, не видя сквозь `Annotated`, счёл бы это моделью и упал бы с `FastAPIError` (или вырастил бы паразитную `null`-схему).

```python
from fastapi.responses import StreamingResponse


@router.get("/download")
def download() -> Annotated[StreamingResponse, Raises[NotFoundError]]: ...
```

!!! danger "Голые стрим-возвраты не поддерживаются"

    `-> Annotated[AsyncIterator[X], Raises[...]]` (SSE/JSONL) не поддерживается: FastAPI не видит stream-тип сквозь `Annotated`, а публичного способа задать `stream_item_type` нет. Для стриминга с `Raises` аннотируйте подкласс `Response`.

## auto=True { #auto }

`with_errors(router, auto=True)` заполняет `responses` **без единого маркера**: на регистрации каждый эндпоинт и **всё его дерево зависимостей** статически обходятся (тем же обходчиком, что у [CI-checker](checker.md)), и найденные ошибки вливаются в `responses` — объединяясь с любыми `Raises`, которые вы всё же написали.

```python
from fastapi import Depends

router = with_errors(APIRouter(), auto=True)


def current_user(token: Annotated[str, Depends(oauth)]) -> User:
    if not token:
        raise RequiredTokenError("нужен токен")  # (1)!
    ...


@router.get("/items/{item_id}")
def get_item(item_id: int, user: Annotated[User, Depends(current_user)]) -> Item:
    if item_id == 0:
        raise NotFoundError("нет")  # (2)!
    return Item(item_id=item_id)
```

1. Ошибка из зависимости — тоже попадёт в `responses` роута (401).
2. Ошибка из тела эндпоинта (404).

Итог: `responses` содержит и `404` (из эндпоинта), и `401` (из зависимости) — без явных деклараций.

!!! info "Как это работает"

    Обходчик собирает `raise`-выражения из исходников эндпоинта и его хелперов, а дерево `Depends` реконструируется на регистрации через публичные функции FastAPI. Security-схемы (`OAuth2PasswordBearer` и т.п.) пропускаются — они поднимают обычный `HTTPException`, а не `BaseError`. Ограничения обходчика (локальные переменные, `self.method()`, динамика) те же, что у checker — см. [Ограничения](limitations.md#walker).

!!! tip "auto vs Raises"

    - `Raises` — точная, проверяемая декларация (checker сверит её с реальностью).
    - `auto` — «задокументируй то, что я и так поднимаю», без ручной работы.

    Их можно сочетать: часть объявить явно (например, динамические `raise`, которые AST не видит), остальное подхватит `auto`.

Флаг `auto` задаётся при **первом** вызове `with_errors` (патч идемпотентен, повторный вызов его не меняет).

## Прочие тонкости

- **Разворачивание эндпоинта** (только для чтения аннотаций): `functools.partial`, `functools.wraps`-цепочки, callable-инстансы (`type(obj).__call__`). Регистрируется всегда исходный объект.
- **Нерезолвящиеся аннотации** без упоминания `Raises` (паттерн `if TYPE_CHECKING:`) проходят как в стоковом FastAPI; с упоминанием `Raises` — быстрый `TypeError`.
- **Маркер на необёрнутом роутере** инертен — ничего не инъектируется и ничего не падает. [CI-checker](checker.md) читает аннотации напрямую, поэтому такой дрейф всё равно ловит.

---

**Дальше:** [CI-checker](checker.md) — сверка задекларированного с реально поднимаемым.
