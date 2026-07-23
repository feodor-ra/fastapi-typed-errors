---
title: core
---

# Справочник: core

Публичные символы слоя `core`. Импортируются из корня пакета:

```python
from fastapi_typed_errors import BaseError, ErrorResponse, error_models, handle_base_error
```

## BaseError

::: fastapi_typed_errors.BaseError

## ErrorResponse

::: fastapi_typed_errors.ErrorResponse

## error_models

::: fastapi_typed_errors.error_models

## handle_base_error

::: fastapi_typed_errors.handle_base_error

## BaseErrorMeta

Публичен для разрешения конфликтов метаклассов (см. [Кастомизация](../guide/customization.md#abc)); намеренно не реэкспортируется из корня — импортируйте из `fastapi_typed_errors.core.base`.

::: fastapi_typed_errors.core.base.BaseErrorMeta
