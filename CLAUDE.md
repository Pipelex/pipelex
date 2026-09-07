# Pipelex Coding Rules

## Commands

`make` targets activate the virtual environment themselves; anything else (`pytest`, `pipelex`, `pipelex-dev`) runs from `.venv/bin/` (`.venv\Scripts\` on Windows), never bare. The Makefile is the reference for every target and alias; without `make`, read the target there and run its prerequisites one by one.

- **`make agent-check` after every code change, and fix everything it reports.** Its prerequisites are `fix-unused-imports fix-keyword-only format lint pyright mypy check-ledger check-keyword-only check-hub-layering drift-check`: the import and keyword-only fixers, ruff, pyright, mypy, `plxt` over TOML/MTHDS/PLX, the migration-ledger replay (`cl`), the hub-layering check and the drift contracts. The drift digest reads the git index, so stage your changes before the check.
- **Keyword-only arguments** (the convention is in the standards and in `docs/contribute/keyword-only-arguments.md`): `make check-keyword-only` (`cko`) is the gate, `make fix-keyword-only` (`fko`) inserts the bare `*` where it can — on ungranted subjects too — and reports the shapes it cannot fix, and `make subject-grant FUNC="<path>::<qualname>" RATIONALE="…"` (`sgr`) grants a positional subject. Grant before `make agent-check`, which runs the fixer.
- **Drift contracts.** When `make drift-check` reports an open contract: `make drift-plan`, review and fix the stale targets, `git add` the trigger files, then `make drift-ack CONTRACT=<id> RATIONALE="…"`. No bypass flag; "reviewed, no doc change needed" is a legitimate rationale. See `docs/contribute/drift-contracts.md`.
- **`make agent-test` at the end of every coding session.** Heartbeat lines while running, full output only on failure. If it hangs or fails opaquely, `make agent-test-debug` (`atd`) adds stale-process cleanup, an outer timeout and a live log; the methodology is `docs/agents/debugging-hanging-pytest-runs.md`. At intermediate steps in a local setup, running only the relevant tests is fine: `.venv/bin/pytest -x -q tests/unit/path/to/test_module.py`, or `make t TEST=<name>` (pytest `-k` substring matching; `TEST=LF` reruns the last failures). `make tp` / `make test-with-prints` are for a human at a terminal; an agent in the cloud or in a sandbox uses `make agent-test` only.
- **`make test-ts-gates` (`ttg`) after touching anything under `pipelex/codegen/emitters/`, or moving the pinned prettier version.** `make agent-test` does not cover the TypeScript emission: the two gates that read the emitted TypeScript as TypeScript need a node toolchain and skip silently without one. This target provisions a pinned prettier and zod into `.ts-toolchain/` (npm, node >= 22.6) and makes those gates fail instead of skip, as CI does. See `docs/contribute/typescript-emission-gates.md`.
- **`make cleanderived`** when linters or pytest collection get confused after files were erased or moved.
- **`CLAUDE.md` and `AGENTS.md` are generated.** Edit the sources in `pipelex/kit/agent_rules/` (assembled per `pipelex/kit/index.toml`) and run `make rules`; `make check-rules` is the CI gate, and `make agent-check` does not include it.
- **`pipelex-dev`** (`.venv/bin/pipelex-dev --help`) holds the internal generators, most with a `make` alias. `generate-mthds-schema` (`gms`) after modifying `mthds_schema_generator.py`. `generate-error-pages` (`gep`) and `generate-error-identity` (`gei`) after adding, renaming or removing an error class: consumers outside this repo branch on `error_type`, so a rename is a silent wire break that the committed snapshot turns into a reviewable diff. `refresh-graph-ui-sri --mthds-ui-version <v> [--elkjs-version <v>]` when bumping the pinned mthds-ui or elkjs. `trace-input-semantics` when changing the structure blueprint, the structure generator, the schema render or the contract builder (`docs/contribute/trace-input-semantics.md`). `generate-projection-corpus` to rewrite the fixture corpus committed byte-identically in `mthds-js` and `mthds-python` (`docs/contribute/generate-projection-corpus.md`). `drift` carries the drift-contract commands above.

## Standards related to developing the Pipelex codebase

### Spec vs Blueprint Architecture

- **Blueprints** (`pipelex/pipe_operators/`, `pipelex/pipe_controllers/`, `pipelex/pipe_machinery/`, `pipelex/mthds_parsing/`, `pipelex/core/`) are the MTHDS language reference — what `.mthds` files parse into. The base `PipeBlueprint` lives in `pipe_machinery/`, the bundle blueprint the parser produces in `mthds_parsing/`, and the concept/domain blueprints in `core/`.
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

### Keyword-only arguments

Non-subject function parameters across `pipelex/` source must be **keyword-only**, so call sites are self-documenting: `do_thing(retries=3, timeout=30)` over the opaque `do_thing(3, 30)`. The compliant shapes:

- `def f(*, opt1, opt2): ...` — fully keyword-only. Always compliant, needs nothing.
- `def f(subject, *, opt1, opt2): ...` — a positional subject (including a lone one, `def render(node)`) is legal ONLY under a **subject grant** recorded in `subject_grants.toml` at the repo root: `make subject-grant FUNC="<path>::<qualname>" RATIONALE="…"` (alias `sgr`). Grant when the call reads as a verb–object sentence with a single obvious operand; when in doubt, go keyword-only.
- A second bare positional (`def f(a, b)`, `def truncate(text, max_length=80)`) is always a violation, grant or not.
- A `bool`/`int`/`float` subject (incl. `Optional`/union-with-`None` forms) is banned outright — grants are impossible; `f(True)` call sites are never acceptable.

The rule is mechanically enforced by the `check-keyword-only` AST guard, which runs in `make agent-check`, in the `make check` aggregate, and in CI; the tree is fully compliant, so it hard-blocks on **any** violation, and staleness is symmetric (a grant whose def was renamed, moved, demoted, or deleted fails the check until the registry is cleaned up). Carve-outs (dunders, pydantic validators/serializers, Typer/pytest/Jinja2 framework entrypoints, `@override` impls) are skipped automatically. A genuinely justified one-off uses an inline `# kw-only: ignore` comment on the `def` line (place it right after the open paren so `ruff format` keeps it on the header line). Watch for functions a framework or the interpreter invokes positionally (callbacks, `__import__` hooks, route handlers): the type checker is blind to those, so `make agent-test` is the safety net. ⚠ `make agent-check` runs the auto-fixer, which will silently keyword-only an ungranted subject — record the grant BEFORE running checks if the subject should stay positional.

The full specification — the grant registry and rubric, the symmetric-tuple allowlist, the carve-out list, the escape hatch, and worked examples — is in [`docs/contribute/keyword-only-arguments.md`](docs/contribute/keyword-only-arguments.md).

## Writing Docs

We use Material for MkDocs. All markdown in our docs must be compatible with Material for MkDocs and done using best practices to get the best results with Material for MkDocs.

### MkDocs Markdown Requirements

- Always add a blank line before any bullet lists or numbered lists in MkDocs markdown.
