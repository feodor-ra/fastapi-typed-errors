---
title: analysis
---

# Reference: analysis

The public symbols of the `analysis` layer. `check_raises`, `RaisesReport`, `RouteDiscrepancy` come from the root; `collect_raised` from the `analysis` subpackage.

```python
from fastapi_typed_errors import check_raises, RaisesReport, RouteDiscrepancy
from fastapi_typed_errors.analysis import collect_raised
```

## check_raises

::: fastapi_typed_errors.check_raises

## RaisesReport

::: fastapi_typed_errors.RaisesReport

## RouteDiscrepancy

::: fastapi_typed_errors.RouteDiscrepancy

## collect_raised

The AST-walking engine shared by `check_raises` and `with_errors(auto=True)`.

::: fastapi_typed_errors.analysis.collect_raised
