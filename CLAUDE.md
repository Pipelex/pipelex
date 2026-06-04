# Pipelex Coding Rules

## Commands

### Linting

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

### Cleaning Derived Files

   If you need to clean derived files and caches, typically after you erased files or moved tests, the linters can get confused, the pytest collection can be off...

   ```bash
   make cleanderived
   ```

### Running Tests

   `make agent-test` runs the test suite and is **critical at the end of a coding session** to verify everything is good before wrapping up.

   At intermediate steps during LOCAL development, it's OK to run only the tests relevant to your changes — either by calling pytest directly from the `.venv` (e.g. `.venv/bin/pytest -x -q tests/unit/path/to/test_module.py`) or using `make t TEST=TestClassName`. This applies only to local setups, not cloud agents.

   ```bash
   make agent-test
   # If the current system doesn't have the `make` command, lookup the "agent-test" target in the Makefile and run the command manually.
   # Zero output on success; full output on failure.
   ```

### When `make agent-test` hangs or fails opaquely

   Use **`make agent-test-debug`** (alias: `make atd`). Same suite, but with stale-process cleanup upfront, an outer wall-clock `timeout` so fixture-teardown hangs and xdist worker-replace loops can't run forever, direct file redirect for live progress (`tail -f /tmp/pytest-agent-test-debug.log`), and `-v` so each test name lands in the log as it runs. On failure or timeout it prints the failed tests, the log path, and a grep hint.

   For the full debugging methodology — clean-state protocol, when to bail to the user, how to grep failures by error class name, when xdist failures are flakes vs real bugs — see [`docs/agents/debugging-hanging-pytest-runs.md`](docs/agents/debugging-hanging-pytest-runs.md).

### Running Tests with Prints

   > **LOCAL ONLY**: The commands below are meant for a human developer running on their local machine. If you are an AI agent (Claude Code, Cursor, Codex, or any other agent running in the cloud or in a sandboxed environment), **do NOT use these commands**. Use `make agent-test` instead.

   If anything went wrong, you can run the tests with prints to see the error:

   ```bash
   make test-with-prints
   # If the current system doesn't have the `make` command, lookup the "test-with-prints" target in the Makefile and run the command manually.
   ```

### Running specific Tests

   > **LOCAL ONLY**: The commands below are meant for a human developer running on their local machine. If you are an AI agent (Claude Code, Cursor, Codex, or any other agent running in the cloud or in a sandboxed environment), **do NOT use these commands**. Use `make agent-test` instead.

   ```bash
   make tp TEST=TestClassName
   # or
   make tp TEST=test_function_name
   ```
   Note: Matches names starting with the provided string.

### Running Last Failed Tests

   > **LOCAL ONLY**: The commands below are meant for a human developer running on their local machine. If you are an AI agent (Claude Code, Cursor, Codex, or any other agent running in the cloud or in a sandboxed environment), **do NOT use these commands**. Use `make agent-test` instead.

   To rerun only the tests that failed in the previous run, use:

   ```bash
   make tp TEST=LF
   # or with any test target
   make test TEST=LF
   make t TEST=LF
   ```
   Note: `TEST=LF` (or `TEST=lf`) will use pytest's `--lf` flag instead of name filtering.

### Temporal Integration Test Options

   The Temporal integration tests support different server modes via the `--temporal-server` pytest CLI option:

   - `--temporal-server`: Which Temporal server to use
     - `none` (default): in-process test server — no external dependencies, used in CI
     - `time-skipping`: in-process server with deterministic time control
     - A profile name from `temporal_server_configs` in `pipelex.toml` (e.g. `local`, `testing`): connects to a real Temporal server using the profile's host, namespace, and API key settings

   ```bash
   # CI default: in-process server
   .venv/bin/pytest tests/integration/pipelex/temporal/

   # Dev with local Temporal server
   .venv/bin/pytest tests/integration/pipelex/temporal/ \
     --temporal-server local

   # Dev with cloud/testing server
   .venv/bin/pytest tests/integration/pipelex/temporal/ \
     --temporal-server testing
   ```

---

### Prerequisites for running command lines: use virtual environment

   **CRITICAL**: Before running any `pipelex` commands or `pytest`, you MUST use the appropriate Python virtual environment. The only exceptions are our `make` commands which already include the env activation.

   Call the CLI directly from the virtual environment:

   ```bash
   .venv/bin/pytest -s -v -k test_render_jinja2_from_text
   .venv/bin/pipelex validate --all
   ```

   For standard installations, the virtual environment is named `.venv`. Always check this first. On Windows, the path is `.venv\Scripts\` instead of `.venv/bin/`.

### Pipelex Dev CLI (`pipelex-dev`)

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

   - **`refresh-graph-ui-sri`**: Refetch the pinned graph viewer assets from jsDelivr (`@pipelex/mthds-ui` standalone JS+CSS, `elkjs`) and rewrite `pipelex/graph/reactflow/standalone_assets.py` with new `sha384` Subresource Integrity hashes. Use when bumping the pinned mthds-ui or elkjs version.

     ```bash
     .venv/bin/pipelex-dev refresh-graph-ui-sri --mthds-ui-version 0.6.3
     # or rotate elkjs alongside:
     .venv/bin/pipelex-dev refresh-graph-ui-sri --mthds-ui-version 0.6.3 --elkjs-version 0.11.1
     ```

## Standards related to developing the Pipelex codebase

### Spec vs Blueprint Architecture

- **Blueprints** (`pipelex/pipe_operators/`, `pipelex/pipe_controllers/`, `pipelex/core/`) are the MTHDS language reference — what `.mthds` files parse into.
- **Specs** (`pipelex/builder/pipe/`) are a convenience authoring format for AI agents. Each spec has `to_blueprint()` that transforms it into the corresponding blueprint. Spec-level fields may differ from blueprint-level fields.

When adding validation or fields, decide which layer they belong to. Language rules go on blueprints; authoring convenience goes on specs. See `pipelex/builder/CLAUDE.md` for details.

### Main config

- The main config model is defined using `ConfigModel` classes, derived from `pydantic BaseModel`
- The model is defined in `pipelex/system/configuration/configs.py`, some of the submodels being defined in their respective sub-packages
- When adding new configs, place them where it makes most sense, ask the user if you need arbitrage
- As per our python standards, use StrEnum for multiple-value enums. In that case they must not be strict pydantic fields, i.e. add `= Field(strict=False)`
- **Important**: NEVER EVER set default values for config attributes in the class definition. All the default values are defined in the main config file `pipelex/pipelex.toml`. The only exception si for Optional values which must be set to `None` in the class definition.
- If (and only if) you add some config that will clearly make sense for client projects to override, for instance if it's a case of user preference, then you can also add a copy of the settings to the project override config file `.pipelex/pipelex.toml`. NEVER add them commented out: commented-out TOML is never parsed or validated, so it rots silently when keys are refactored. Instead, write the actual default values (matching `pipelex/pipelex.toml`, even empty ones like `activity_queues = {}`) so the override file stays valid and behaves like setting nothing. Plain prose comments explaining the setting are fine — it's commented-out keys/values that are forbidden.
- The different `pipelex.toml` files and the python model `configs.py` must be up to date with each other in terms of structure and attributes, otherwise the loading of teh config fails. To check quickly that you're good, just run `make tb` which tests the boot sequence, which includes the config loading.

## Writing Docs

We use Material for MkDocs. All markdown in our docs must be compatible with Material for MkDocs and done using best practices to get the best results with Material for MkDocs.

### MkDocs Markdown Requirements

- Always add a blank line before any bullet lists or numbered lists in MkDocs markdown.
