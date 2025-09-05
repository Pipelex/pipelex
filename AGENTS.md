# General rules

## Repo structure

Pipelex is a framework to run low-code AI workflows for repeatable processes.
This python >=3.10 code is in the `pipelex` directory.

## Code Style & formatting

- Imitate existing style
- Use type hints
- Respect Pydantic v2 standard
- Use Typer for CLIs
- Use explicit keyword arguments for function calls with multiple parameters (e.g., `func(arg_name=value)` not just `func(value)`)
- Add trailing commas to multi-line lists, dicts, function arguments, and tuples with >2 items (helps with cleaner diffs and prevents syntax errors when adding items)
- All imports inside this repo's packages must be absolute package paths from the root

## Error Handling & Validation

- Use `format_pydantic_validation_error` for consistent error formatting when catching ValidationError
- Implement `StuffContentValidationError` for content validation failures

## Linting & checking

- Run `make lint` -> it runs `ruff check . --fix` to enforce all our linting rules
- Run `make pyright` -> it typechecks with pyright using proper settings
- Run `make mypy` -> it typechecks with mypy using proper settings
    - if you added a dependency and mypy complains that it's not typed, add it to the list of modules in [[tool.mypy.overrides]] in pyproject.toml, be sure to signal it in your PR recap so that maintainers can look for existing stubs

## Testing

- Always test with `make codex-tests` -> it runs pytest on our `tests/` directory using proper settings
- If all unit tests pass, run `make validate` -> it runs a minimal version of our app with just the inits and data loading (`pipelex validate all -c pipelex/libraries` under the hood) in the python environment.

## PR Instructions

- Run `make fix-unused-imports` -> removes unused imports, required to validate PR
- Re-run checks in one call with `make check` -> formatting and linting with Ruff, type-checking with Pyright and Mypy
- Re-run `make codex-tests`
- Write a one-line summary of the changes.
- Be sure to list changes made to configs, tests and dependencies
