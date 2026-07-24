---
title: Changelog
---

# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.1] — 2026-07-25

### Fixed

- A `Raises` marker shared through a PEP 695 `type` alias and placed as a metadata
  element of `Annotated` (`Annotated[Item, CommonRaises, Raises[...]]`) is no longer
  dropped silently — the alias is now unwrapped in metadata position too, on par with
  tuple unpacking. Aliasing the whole annotation already worked.

## [1.0.0] — 2026-07-24

### Added

- First stable release. Three independent layers:
  - **core** — `BaseError`, the `BaseErrorMeta` metaclass, `ErrorResponse`,
    `error_models()`, `handle_base_error`.
  - **decorator** — `with_errors(router)` with the `Raises[...]` marker, plus
    `auto=True` to fill `responses` from a static walk of the endpoint and its
    dependency tree.
  - **analysis** — `check_raises()` CI checker comparing declared vs. actually
    raised errors, and a `typer` CLI (`cli` extra).
