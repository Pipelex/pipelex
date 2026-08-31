# Commands

## Linting

   After making code changes, you must always lint using `make agent-check`.

   ```bash
   make agent-check
   # If the current system doesn't have the `make` command,
   # lookup the "agent-check" target in the Makefile and run the commands one by one (targets fix-unused-imports fix-keyword-only format lint pyright mypy check-ledger check-keyword-only check-hub-layering drift-check)
   ```

   This runs multiple code quality tools:
   - Pyright: Static type checking
   - Ruff: Fix unused imports, lint, format  
   - Mypy: Static type checker
   - plxt: Format and lint TOML, MTHDS, and PLX files
   - Migration ledgers: every checked-in ledger must be legal and replay harmlessly over its reference documents (`make check-ledger`, alias `cl`)
   - Drift contracts: open code↔docs review obligations fail the gate (note the digest reads the git index, so stage your changes for the check to see them; resolve with the drift workflow below)

   Always fix any issues reported by these tools before proceeding.

## Keyword-only arguments check

   Non-subject function parameters across `pipelex/` source must be keyword-only, and a positional subject is legal only under a grant recorded in `subject_grants.toml`. The convention is mechanically enforced and already runs as part of `make agent-check`, but you can invoke it on its own:

   ```bash
   make check-keyword-only   # alias: make cko — read-only gate; hard-blocks on any violation
   make fix-keyword-only     # alias: make fko — auto-insert a bare * for mechanically-fixable violations
   make subject-grant FUNC="<path>::<qualname>" RATIONALE="…"   # alias: make sgr — grant a positional subject
   ```

   `check-keyword-only` owns the pass/fail gate; `fix-keyword-only` rewrites what it can (including ungranted subjects — grant BEFORE running checks if the subject should stay positional) and reports the shapes it can't fix mechanically (resolve those by hand). See [`docs/contribute/keyword-only-arguments.md`](docs/contribute/keyword-only-arguments.md) for the full convention.

## Cleaning Derived Files

   If you need to clean derived files and caches, typically after you erased files or moved tests, the linters can get confused, the pytest collection can be off...

   ```bash
   make cleanderived
   ```

## Running Tests

   `make agent-test` runs the test suite and is **critical at the end of a coding session** to verify everything is good before wrapping up.

   At intermediate steps during LOCAL development, it's OK to run only the tests relevant to your changes — either by calling pytest directly from the `.venv` (e.g. `.venv/bin/pytest -x -q tests/unit/path/to/test_module.py`) or using `make t TEST=TestClassName`. This applies only to local setups, not cloud agents.

   ```bash
   make agent-test
   # If the current system doesn't have the `make` command, lookup the "agent-test" target in the Makefile and run the command manually.
   # Heartbeat progress lines while running; full output only on failure.
   ```

## When `make agent-test` hangs or fails opaquely

   Use **`make agent-test-debug`** (alias: `make atd`). Same suite, but with stale-process cleanup upfront, an outer wall-clock `timeout` so fixture-teardown hangs and xdist worker-replace loops can't run forever, direct file redirect for live progress (`tail -f /tmp/pytest-agent-test-debug.log`), and `-v` so each test name lands in the log as it runs. On failure it prints the failed tests, the log path, and a grep hint; on timeout, the tail of the log and the log path.

   For the full debugging methodology — clean-state protocol, when to bail to the user, how to grep failures by error class name, when xdist failures are flakes vs real bugs — see [`docs/agents/debugging-hanging-pytest-runs.md`](docs/agents/debugging-hanging-pytest-runs.md).

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
   Note: Matches names containing the provided string (pytest `-k` substring matching).

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

   - **`refresh-graph-ui-sri`**: Refetch the pinned graph viewer assets from jsDelivr (`@pipelex/mthds-ui` standalone JS+CSS, `elkjs`) and rewrite `pipelex/graph/reactflow/standalone_assets.py` with new `sha384` Subresource Integrity hashes. Use when bumping the pinned mthds-ui or elkjs version.

     ```bash
     .venv/bin/pipelex-dev refresh-graph-ui-sri --mthds-ui-version 0.6.3
     # or rotate elkjs alongside:
     .venv/bin/pipelex-dev refresh-graph-ui-sri --mthds-ui-version 0.6.3 --elkjs-version 0.11.1
     ```

   - **`trace-input-semantics`**: Capture harness for the input-schema emission chain — given one or more `.mthds` bundles, dumps one artifact per hop (parse blueprint, generated class source, raw pydantic schema, SCHEMA render, wire contract) plus a manifest of each pipe input's wire framing, so a lost or mangled authored fact is localized to exactly one hop. Use when changing the structure blueprint, the structure generator, the schema render, or the contract builder. See `docs/contribute/trace-input-semantics.md`.

     ```bash
     .venv/bin/pipelex-dev trace-input-semantics tests/data/input_semantics/probe_bundle.mthds -o /tmp/probe-trace
     ```

   - **`generate-projection-corpus`**: Write the shared inputs-template projection fixture corpus — the descriptors, the expected fill-in templates in both shapes and both formats, and the record of where the expectation deliberately differs from the engine's own renderer. Sole producer of the capture committed byte-identically in `mthds-js/tests/fixtures/protocol/` and `mthds-python/tests/fixtures/protocol/`, which is what pins the TypeScript and Python projections against each other. See `docs/contribute/generate-projection-corpus.md`.

     ```bash
     .venv/bin/pipelex-dev generate-projection-corpus tests/data/input_semantics/*.mthds -o /tmp/projection-corpus
     ```

   - **`drift`**: Drift contracts — deterministic review obligations between code and docs, declared in the root `drift.toml` (see `docs/contribute/drift-contracts.md`). When `make drift-check` (part of `make agent-check`, `make check`, and CI) reports an open contract: run `make drift-plan` to see what changed and what to review, actually review the targets and fix what is stale, `git add` the trigger files (the digest reads the git index, not the working tree), then record the review with `make drift-ack CONTRACT=<id> RATIONALE="…"`. The rationale is the on-the-record review decision — write an honest sentence. There is no bypass flag; "reviewed, no doc change needed" is a legitimate rationale.

     ```bash
     make drift-plan
     make drift-ack CONTRACT=config-docs RATIONALE="Documented the new setting; other config pages unaffected."
     ```
