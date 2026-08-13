# Codex Cloud Commands

## Linting

   After making code changes, you must always lint using `make agent-check`.

   ```bash
   make agent-check
   # If the current system doesn't have the `make` command,
   # lookup the "agent-check" target in the Makefile and run the commands one by one (targets fix-unused-imports fix-keyword-only format lint pyright mypy check-keyword-only check-hub-layering drift-check)
   ```

   This runs multiple code quality tools:
   - Pyright: Static type checking
   - Ruff: Fix unused imports, lint, format  
   - Mypy: Static type checker
   - plxt: Format and lint TOML, MTHDS, and PLX files
   - Drift contracts: open code↔docs review obligations fail the gate (note the digest reads the git index, so stage your changes for the check to see them)

   Always fix any issues reported by these tools before proceeding.

## Keyword-only arguments check

   Non-subject function parameters across `pipelex/` source must be keyword-only (a bare `*` after the subject). The convention is mechanically enforced and already runs as part of `make agent-check`, but you can invoke it on its own:

   ```bash
   make check-keyword-only   # alias: make cko — read-only gate; hard-blocks on any violation
   make fix-keyword-only     # alias: make fko — auto-insert a bare * for mechanically-fixable violations
   ```

   `check-keyword-only` owns the pass/fail gate; `fix-keyword-only` rewrites what it can and reports the shapes it can't fix mechanically (resolve those by hand). See [`docs/contribute/keyword-only-arguments.md`](docs/contribute/keyword-only-arguments.md) for the full convention.

## Cleaning Derived Files

   If you need to clean derived files and caches, typically after you erased files or moved tests, the linters can get confused, the pytest collection can be off...

   ```bash
   make cleanderived
   ```

## Running Tests in Codex Cloud

    To test everything that can be tested from within the Codex Cloud sandbox, run this:

    ```bash
    make codex-tests
    # It's equivalent to running pytest with `-m "(dry_runnable or not inference) and not (pipelex_api or codex_disabled)"`
    # If some test fails, re-run it with `-s -vv` to see more details
    ```

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

   - **`generate-mthds-schema`**: Regenerate the MTHDS JSON Schema (`derived/mthds_schema.json`). Run this after modifying `mthds_schema_generator.py`.

     ```bash
     .venv/bin/pipelex-dev generate-mthds-schema
     ```

   - **`generate-error-pages`**: Regenerate the per-class error reference pages under `docs/errors/` — one Markdown page per `PipelexError` subclass, which is what each error's `type_uri` dereferences to. Run after adding or renaming an error class. Pages a maintainer claims with a `<!-- pipelex:authored -->` marker are preserved across runs. Also available as `make generate-error-pages` (alias `make gep`).

     ```bash
     .venv/bin/pipelex-dev generate-error-pages
     ```

   - **`generate-error-identity`**: Regenerate the committed `(error_type, title, type_uri)` snapshot of every `PipelexError` subclass at `tests/data/errors/error_identity.txt`. `error_type` is the bare class name and consumers outside this repo branch on it, so a rename is a silent wire break — the snapshot turns it into a reviewable diff, gated by `tests/unit/pipelex/errors/test_error_identity_snapshot.py`. Run after adding, renaming or removing an error class. Also available as `make generate-error-identity` (alias `make gei`).

     ```bash
     .venv/bin/pipelex-dev generate-error-identity
     ```

## Pipelex CLI Commands

   To run the Pipelex CLI commands without the logo, you can use the `--no-logo` flag, this will avoid useless tokens in the console output.

   ```bash
   .venv/bin/pipelex --help
   .venv/bin/pipelex build --help --no-logo
   .venv/bin/pipelex run --help --no-logo
   .venv/bin/pipelex validate --help --no-logo
   .venv/bin/pipelex doctor --help --no-logo
   .venv/bin/pipelex init --help --no-logo
   ```
