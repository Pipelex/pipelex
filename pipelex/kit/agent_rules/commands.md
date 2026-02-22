# Commands

## Linting

   After making code changes, you must always lint using `make agent-check`.

   ```bash
   make agent-check
   # If the current system doesn't have the `make` command,
   # lookup the "agent-check" target in the Makefile and run the commands one by one (targets fix-unused-imports format lint pyright mypy)
   ```

   This runs multiple code quality tools:
   - Pyright: Static type checking
   - Ruff: Fix unused imports, lint, format  
   - Mypy: Static type checker
   - plxt: Format and lint TOML, MTHDS, and PLX files

   Always fix any issues reported by these tools before proceeding.

## Cleaning Derived Files

   If you need to clean derived files and caches, typically after you erased files or moved tests, the linters can get confused, the pytest collection can be off...

   ```bash
   make cleanderived
   ```

## Running Tests

   After you're finished making code changes, you must always run tests using `make agent-test`.

   ```bash
   make agent-test
   # If the current system doesn't have the `make` command, lookup the "agent-test" target in the Makefile and run the command manually.
   # Zero output on success; full output on failure.
   ```

## Running Tests with Prints

   > **LOCAL ONLY**: The commands below are meant for a human developer running on their local machine. If you are an AI agent (Claude Code, Cursor, Codex, or any other agent running in the cloud or in a sandboxed environment), **do NOT use these commands**. Use `make agent-test` instead.

   If anything went wrong, you can run the tests with prints to see the error:

   ```bash
   make test-with-prints
   # If the current system doesn't have the `make` command, lookup the "test-with-prints" target in the Makefile and run the command manually.
   ```

## Running specific Tests

   > **LOCAL ONLY**: The commands below are meant for a human developer running on their local machine. If you are an AI agent (Claude Code, Cursor, Codex, or any other agent running in the cloud or in a sandboxed environment), **do NOT use these commands**. Use `make agent-test` instead.

   ```bash
   make tp TEST=TestClassName
   # or
   make tp TEST=test_function_name
   ```
   Note: Matches names starting with the provided string.

## Running Last Failed Tests

   > **LOCAL ONLY**: The commands below are meant for a human developer running on their local machine. If you are an AI agent (Claude Code, Cursor, Codex, or any other agent running in the cloud or in a sandboxed environment), **do NOT use these commands**. Use `make agent-test` instead.

   To rerun only the tests that failed in the previous run, use:

   ```bash
   make tp TEST=LF
   # or with any test target
   make test TEST=LF
   make t TEST=LF
   ```
   Note: `TEST=LF` (or `TEST=lf`) will use pytest's `--lf` flag instead of name filtering.

---

## Prerequisites for running command lines: use virtual environment

   **CRITICAL**: Before running any `pipelex` commands or `pytest`, you MUST use the appropriate Python virtual environment. The only exceptions are our `make` commands which already include the env activation.

   Call the CLI directly from the virtual environment:

   ```bash
   .venv/bin/pytest -s -v -k test_render_jinja2_from_text
   .venv/bin/pipelex validate --all
   ```

   For standard installations, the virtual environment is named `.venv`. Always check this first. On Windows, the path is `.venv\Scripts\` instead of `.venv/bin/`.

## Pipelex Dev CLI (`pipelex-dev`)

   The `pipelex-dev` CLI provides internal development tools that are not distributed with the package. It is available in the virtual environment.

   ```bash
   .venv/bin/pipelex-dev --help
   ```

   Key commands:

   - **`generate-mthds-schema`**: Regenerate the MTHDS JSON Schema (`.pipelex/mthds_schema.json`). Run this after modifying `mthds_schema_generator.py`.

     ```bash
     .venv/bin/pipelex-dev generate-mthds-schema
     ```
