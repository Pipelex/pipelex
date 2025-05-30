# General rules

## Repo structure

Pipelex is a framework to run low-code AI workflows for repeatable processes.
This python 3.11 code is in the `pipelex` directory.

## Code Style & formatting

- Imitate existing style
- After editing code, run `make format` -> it runs `ruff format .` with proper settings
- All imports inside this repo's packages must be absolute package paths from the root

## Linting & checking

- Run `make lint` -> it runs `ruff check . --fix` to enforce all our linting rules
- Run `make pyright` -> it typechecks with pyright using proper settings
- Run `make mypy` -> it typechecks with mypy using proper settings
    - if you added a dependency and mypy complains that it's not typed, add it to the list of modules in [[tool.mypy.overrides]] in pyproject.toml, be sure to signal it in your PR recap so that maintainers can look for existing stubs

## Testing

- Always test with `make runtests` -> it runs pytest on our `tests/` directory using proper sttings
- If all unit tests pass, run `make run-setup` -> it runs a minimal version of our app with just the inits and data loading

## PR Instructions

- One-line summary of the change.
- Be sure to list changes made to configs, tests and dependencies
