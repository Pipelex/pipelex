# Standards related to developing the Pipelex codebase

## Spec vs Blueprint Architecture

- **Blueprints** (`pipelex/pipe_operators/`, `pipelex/pipe_controllers/`, `pipelex/pipe_machinery/`, `pipelex/mthds_parsing/`, `pipelex/core/`) are the MTHDS language reference — what `.mthds` files parse into. The base `PipeBlueprint` lives in `pipe_machinery/`, the bundle blueprint the parser produces in `mthds_parsing/`, and the concept/domain blueprints in `core/`.
- **Specs** (`pipelex/builder/pipe/`) are a convenience authoring format for AI agents. Each spec has `to_blueprint()` that transforms it into the corresponding blueprint. Spec-level fields may differ from blueprint-level fields.

When adding validation or fields, decide which layer they belong to. Language rules go on blueprints; authoring convenience goes on specs. See `pipelex/builder/CLAUDE.md` for details.

## Main config

- The main config model is defined using `ConfigModel` classes, derived from `pydantic BaseModel`
- The model is defined in `pipelex/system/configuration/configs.py`, some of the submodels being defined in their respective sub-packages
- When adding new configs, place them where it makes most sense, ask the user if you need arbitrage
- As per our python standards, use StrEnum for multiple-value enums. In that case they must not be strict pydantic fields, i.e. add `= Field(strict=False)`
- **Important**: NEVER EVER set default values for config attributes in the class definition. All the default values are defined in the main config file `pipelex/pipelex.toml`. The only exception si for Optional values which must be set to `None` in the class definition.
- If (and only if) you add some config that will clearly make sense for client projects to override, for instance if it's a case of user preference, then you can also add a copy of the settings to the project override config file `.pipelex/pipelex.toml`. NEVER add them commented out: commented-out TOML is never parsed or validated, so it rots silently when keys are refactored. Instead, write the actual default values (matching `pipelex/pipelex.toml`, even empty ones like `activity_queues = {}`) so the override file stays valid and behaves like setting nothing. Plain prose comments explaining the setting are fine — it's commented-out keys/values that are forbidden.
- The different `pipelex.toml` files and the python model `configs.py` must be up to date with each other in terms of structure and attributes, otherwise the loading of teh config fails. To check quickly that you're good, just run `make tb` which tests the boot sequence, which includes the config loading.

## Keyword-only arguments

Non-subject function parameters across `pipelex/` source must be **keyword-only**, so call sites are self-documenting: `do_thing(retries=3, timeout=30)` over the opaque `do_thing(3, 30)`. The compliant shapes:

- `def f(*, opt1, opt2): ...` — fully keyword-only. Always compliant, needs nothing.
- `def f(subject, *, opt1, opt2): ...` — a positional subject (including a lone one, `def render(node)`) is legal ONLY under a **subject grant** recorded in `subject_grants.toml` at the repo root: `make subject-grant FUNC="<path>::<qualname>" RATIONALE="…"` (alias `sgr`). Grant when the call reads as a verb–object sentence with a single obvious operand; when in doubt, go keyword-only.
- A second bare positional (`def f(a, b)`, `def truncate(text, max_length=80)`) is always a violation, grant or not.
- A `bool`/`int`/`float` subject (incl. `Optional`/union-with-`None` forms) is banned outright — grants are impossible; `f(True)` call sites are never acceptable.

The rule is mechanically enforced by the `check-keyword-only` AST guard, which runs in `make agent-check`, in the `make check` aggregate, and in CI; the tree is fully compliant, so it hard-blocks on **any** violation, and staleness is symmetric (a grant whose def was renamed, moved, demoted, or deleted fails the check until the registry is cleaned up). Carve-outs (dunders, pydantic validators/serializers, Typer/pytest/Jinja2 framework entrypoints, `@override` impls) are skipped automatically. A genuinely justified one-off uses an inline `# kw-only: ignore` comment on the `def` line (place it right after the open paren so `ruff format` keeps it on the header line). Watch for functions a framework or the interpreter invokes positionally (callbacks, `__import__` hooks, route handlers): the type checker is blind to those, so `make agent-test` is the safety net. ⚠ `make agent-check` runs the auto-fixer, which will silently keyword-only an ungranted subject — record the grant BEFORE running checks if the subject should stay positional.

The full specification — the grant registry and rubric, the symmetric-tuple allowlist, the carve-out list, the escape hatch, and worked examples — is in [`docs/contribute/keyword-only-arguments.md`](docs/contribute/keyword-only-arguments.md).
