# Commands

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

## Running Tests

   After you're finished making code changes, you must always run tests using `make test-xdist`.

   ```bash
   make test-xdist
   # If the current system doesn't have the `make` command, lookup the "test-xdist" target in the Makefile and run the command manually.
   # If some test failes, re-run it with `-s -vv` to see more details
   ```

## Running Tests with Prints

   If anything went wrong, you can run the tests with prints to see the error:

   ```bash
   make test-with-prints
   # If the current system doesn't have the `make` command, lookup the "test-with-prints" target in the Makefile and run the command manually.
   ```

## Running specific Tests

   ```bash
   make tp TEST=TestClassName
   # or
   make tp TEST=test_function_name
   ```
   Note: Matches names starting with the provided string.

## Running Last Failed Tests

   To rerun only the tests that failed in the previous run, use:

   ```bash
   make tp TEST=LF
   # or with any test target
   make test TEST=LF
   make t TEST=LF
   ```
   Note: `TEST=LF` (or `TEST=lf`) will use pytest's `--lf` flag instead of name filtering.

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
