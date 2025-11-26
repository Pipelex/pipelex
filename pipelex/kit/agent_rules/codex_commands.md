# Codex Cloud Commands

## Linting

   After making code changes, you must always lint using `make check`.

   ```bash
   make check
   # If the current system doesn't have the `make` command, lookup the "check" target in the Makefile and run the command manually.
   ```

   This runs multiple code quality tools:
   - Pyright: Static type checking
   - Ruff: Fast Python linter  
   - Mypy: Static type checker

   Always fix any issues reported by these tools before proceeding.

## Running Tests in Codex Cloud

    To test everything that can be tested from within the Codex Cloud sandbox, run this:

    ```bash
    make codex-tests
    # It's equivalent to running pytest with `-m "(dry_runnable or not inference) and not (pipelex_api or codex_disabled)"`
    # If some test fails, re-run it with `-s -vv` to see more details
    ```

---

## Prerequisites for running command lines: activate virtual environment

   **CRITICAL**: Before running any `pipelex` commands or `pytest`, you MUST activate the appropriate Python virtual environment. The only exceptions are our `make` commands which already include the env activation.

   Do this:

   ```bash
   source .venv/bin/activate
   pytest -s -v -k test_render_jinja2_from_text
   pipelex validate all
   ```

   or do that:

   ```bash
   .venv/bin/python -m pytest -s -v -k test_render_jinja2_from_text
   .venv/bin/pipelex validate all
   ```

   (adapt the above command to the OS and available virtual environment name)

   For standard installations, the virtual environment is named `.venv`. Always check this first:

   ```bash
   # Activate the virtual environment (standard installation)
   source .venv/bin/activate  # On macOS/Linux
   # or
   .venv\Scripts\activate  # On Windows
   ```

   If the installation uses a different venv name or location, activate that one instead. All subsequent `pipelex` and `pytest` commands assume the venv is active.

