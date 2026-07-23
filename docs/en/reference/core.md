---
title: core
---

# Reference: core

The public symbols of the `core` layer. Imported from the package root:

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

Public so metaclass conflicts can be resolved (see [Customization](../guide/customization.md#abc)); deliberately not re-exported from the root — import it from `fastapi_typed_errors.core.base`.

::: fastapi_typed_errors.core.base.BaseErrorMeta
