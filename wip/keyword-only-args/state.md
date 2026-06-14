# Keyword-only arguments — cold-start state

Status: **Checkpoint B VERIFIED — Wave 1 landed** (branch `refactor/Function-calling-3`, all uncommitted). Guard built (Checkpoint A); rule strictness + gate placement confirmed; `convention.md` correct. Phase 1 committed earlier (`d18a63fc`, `a58456f3`); `dev` merged twice (v0.31.0, v0.33.0 at `fc23505c8`), baseline reconciled at each (812 → 822 → 844). **Wave 1 (`tools/` + `errors/` + `reporting/` + `observer/` + `tracing/`) now converted: 844 → 690.** `make agent-check` clean (pyright 0, mypy 2190 ok, guard PASSED 690 known-debt); full `make agent-test` GREEN; guard unit tests 32/32. Baseline regenerated (690 entries, all Wave 1 packages pruned). Next: Wave 2 (domain core: `core/` → `language/` → `kit/` → `libraries/`).

This is the running cold-start log for the keyword-only-arguments refactor. Read this file plus [`../../TODOS.md`](../../TODOS.md) and you have everything needed to resume with zero lost context. The convention itself lives in [`convention.md`](convention.md).

## Guard

The guard is the `check-keyword-only` dev CLI command. It walks every `.py` under `pipelex/` (excluding `__pycache__` and `tests/`), parses each with `ast`, evaluates the carve-outs then the keyword-only rule per def, compares the found violations against the committed baseline, and fails (exit 1) only on NEW violations not present in the baseline.

- Command: `.venv/bin/pipelex-dev check-keyword-only` (flags: `--report` for the full inventory grouped by package, `--regen-baseline` to rewrite the baseline with all current violations, `--quiet` / `-q` for the single-line Make mode).
- Makefile target: `make check-keyword-only` (alias `make cko`), which runs `$(VENV_PIPELEX_DEV) check-keyword-only --quiet`.
- Wired into the `check:` aggregate (Makefile around line 1156, in the `check-* ` cluster) and listed in `.PHONY`.
- Source: `pipelex/cli/dev_cli/commands/check_keyword_only_cmd.py`.
- Registration: `pipelex/cli/dev_cli/_dev_cli.py` (import, the `list_commands` entry, and the `@app.command("check-keyword-only")` Typer wrapper).
- Tests: `tests/unit/pipelex/cli/dev/test_check_keyword_only_cmd.py`.
- Baseline: `wip/keyword-only-args/violations-baseline.txt` — newline-delimited `relpath::qualified_name` keys, no line numbers, sorted lexicographically. Strictly shrinks as waves land; the guard warns about and prunes (via `--regen-baseline`) stale entries that no longer violate; remove the file entirely once the tree is fully compliant.
- Inventory: `wip/keyword-only-args/inventory.json` — machine-readable `total` + `per_package_counts` + `violations_by_package`.

The guard currently passes against its own baseline (all current violations known-debt; zero NEW violations). The guard's own command module is fully compliant with the convention.

## Per-package violation inventory (baseline)

Current baseline total after Wave 1: **690** (down from the 844 waterline; Wave 1 removed `tools` 136 + `errors` 5 + `reporting` 5 + `observer` 2 + `tracing` 6 = 154). Wave 1 packages are fully pruned from the baseline.

| Package | Violations | Wave |
| --- | --- | --- |
| `cogt` | 139 | 3 |
| `cli` | 111 | 5 |
| `core` | 110 | 2 |
| `plugins` | 50 | 3 |
| `system` | 44 | 5 |
| `pipe_operators` | 40 | 4 |
| `graph` | 39 | 4 |
| `temporal` | 39 | 5 |
| `libraries` | 28 | 2 |
| `builder` | 21 | 5 |
| `pipe_run` | 16 | 4 |
| `pipeline` | 15 | 4 |
| `runtime_bridge` | 13 | 4 (with pipe_run/pipeline helpers) |
| `kit` | 8 | 2 |
| `pipe_controllers` | 6 | 4 |
| `<root>` (`hub.py` ×1, `pipelex.py` ×3) | 4 | 5 (public API) |
| `language` | 4 | 2 |
| `pipe_signature` | 2 | (its own / Wave 4) |
| `test_extras` | 1 | (shipped pytest plugin) |

**Wave 1 DONE (was, now 0):** `tools` 136→0, `errors` 5→0, `reporting` 5→0, `observer` 2→0, `tracing` 6→0.

Note the `<root>` 4 are all public-API (`hub.py`, `pipelex.py`) — Wave 1's nominal "root modules" (`types.py`, `config.py`, `urls.py`, `base_exceptions.py`, `exceptions.py`) had **zero** violations, so the only root-level work is the public surface, correctly deferred to Wave 5.

**Growth at each `dev` merge.** Merging `dev` imports code written before the guard existed, so the baseline grows at each merge (it strictly shrinks only *between* merges, as waves land):

- **First merge (v0.31.0): 812 → 822.** +13 new from incoming files (`tools/tabular/csv_codec.py`, the new `pipe_signature/` package, dry-run-with-signatures changes in `pipeline/` and the `cli` validate cores, `core/` CSV-stuff factories), −3 stale pruned (the old `pipe_run/dry_run*` functions `dev`'s #953 reshaped).
- **Second merge (v0.33.0): 822 → 844.** +38 new, −16 stale (net +22). The new violations come from the framework-agnostic runtime-bridge extraction (`runtime_bridge/`, #969, +13 — a brand-new package), `cogt/content_generation/` dry-mock + search-assignment changes (+7), the additive-multi-file `libraries/` reconciliation (#970, +4), `errors/` page-generator (+2), and `pipeline/` (+1). The −16 stale entries are functions `dev` *relocated* — e.g. `pipe_run/dry_run_pipeline.py` → `pipeline/dry_run_pipeline.py`, `graph/graph_context.py::GraphContext.copy_for_child` → `graph/trace_context.py::TraceContext.copy_for_child`, the `temporal/tprl_pipe/hydration.py` helpers → `runtime_bridge/primitives/hydration.py` — so the same violations reappear at their new paths and count as "new".

The "strictly shrinks" invariant resumes from the 844 waterline; the incoming violations get burned down within their normal packages/waves (`csv_codec` → `tools` wave, `pipe_signature` → its own, the runtime-bridge/dry-run helpers → `pipe_run`/`pipeline`/their packages).

These are the burn-down targets ordered into waves in [`README.md`](README.md). The wave order is risk-based (leaf packages first, framework/public surface last), not violation-count order — so a high-count leaf like `tools/` lands in Wave 1 while a smaller but framework-sensitive package like `cli/` waits for Wave 5.

## Decisions log

- Override handling — skip any def carrying `@override`. We deliberately did NOT introduce a `@kw_exempt` decorator and did NOT attempt base-aware / import-resolving detection. Rationale: `pyproject.toml` sets `reportImplicitOverride = true`, so any method overriding a nominal base MUST carry `@override` or `make agent-check` (pyright) fails before this guard runs — making `@override` a complete, self-maintaining signal. `reportIncompatibleMethodOverride = error` means an overriding method cannot freely re-shape its signature, so the convention is applied at the base/Protocol definition and impls inherit it; skipping `@override` impls is consistent with that. The rare Protocol-implementor-without-`@override` is covered by the `# kw-only: ignore` escape hatch. Matched structurally: `ast.Name` with `id == "override"` OR `ast.Attribute` with `attr == "override"` (covers both `override` and `typing_extensions.override` without import resolution). The pyright invariant lives at `pyproject.toml` line 176.
- Symmetric-tuple allowlist — exempt the WHOLE function only for genuine ordered tuples under a recognized convention, keyed by EXACT qualified name AND file path (both must match), no pattern guessing. The list is intentionally short and conservative. Entries: `pipelex.system.environment.set_env` (`set_env(key, value)`), `pipelex.kit.single_file_agent_rules.unified_diff` (`unified_diff(before, after, path)`), `pipelex.tools.misc.diff.diff_files` (`diff_files(path1, path2)`), `pipelex.tools.misc.diff.diff_dirs` (`diff_dirs(dir1, dir2)`). Deliberately EXCLUDED: `has_diff_dirs`, `copy_file`, `sync_toml_values` — each has a genuine ordered leading pair but also trailing options; a whole-function exemption would let those options go positional too. They stay off the allowlist and are flagged as violations, resolved per-function at burn-down (see the Exception-2 open question below). Erring toward keyword-only is the safe default; adding to the allowlist is a deliberate, justified act.
- Carve-out decorators (def never inspected when any matches) — dunder/operator names matching `^__[A-Za-z0-9_]+__$` full-match on the NAME node only (so `____` cannot match and name-mangled half-dunders like `__private` remain subject to the rule); pydantic `field_validator` / `model_validator` / `field_serializer` / `model_serializer` / `validator` / `root_validator` (call-form or bare, matched on the unqualified decorator name); framework entrypoints — Typer/click `*.command` / `*.callback` (matched on the attribute suffix, since the receiver varies: `app` / `graph_app` / `show_app` / `kit_app` / `build_app`), Temporal `activity.defn` / `workflow.run` / `workflow.signal` / `workflow.query` / `workflow.update` (matched on the trailing two attribute segments, scanned across the WHOLE decorator stack so a custom decorator stacked below `@activity.defn` does not hide it), and `pytest.fixture`; and `@override` (see above). The escape hatch `# kw-only: ignore` on the def line suppresses exactly one violation.
- Typer call-style entrypoint detection (closes the decorator-blind gap) — some Typer commands are registered via `app.command(name=...)(fn)` against functions in separate modules that carry NO decorator. The guard treats a def as a framework entrypoint when any parameter's `Annotated[...]` metadata contains a call to `typer.Argument(...)` or `typer.Option(...)`, without resorting to a broad path-based exclusion of CLI modules.
- The rule itself — after dropping a leading `self`/`cls` and the single allowed subject parameter, a def is a VIOLATION iff one or more positional-or-keyword params remain (i.e. two or more non-self/cls positional-or-keyword params total and no bare `*` already separating them). Keyword-only params (already past a bare `*`), `*args`, and `**kwargs` do not count as violations. Single-param / subject-only defs are compliant under Exception 1.
- Rule strictness (confirmed with user) — STRICT: only the subject may be positional; every other parameter must be keyword-only, so `def f(a, b)` and `def truncate(text, max_length=80)` are violations. The subject exception is a *permission* (the Swift `_` readability case), never a requirement — making the subject keyword-only too (`def f(*, a, b)`) is always compliant and often preferable. The guard already enforces this; `convention.md` was corrected to match (it had drifted to a looser "one trailing positional is fine" reading that contradicted both the code and the 812 baseline).
- Gate placement (confirmed with user) — `check-keyword-only` runs in BOTH `make agent-check` (fast everyday gate) and `make check` (heavy gate + CI), so a new violation is caught in the tight edit loop, not only at `make check`.
- **Jinja2 filter carve-out (added in Wave 1).** Jinja2 filter/test/global callables carrying `@pass_context` / `@pass_environment` / `@pass_eval_context` are invoked POSITIONALLY by the Jinja2 engine from template syntax (`{{ value | tag("name") }}` → `tag(context, value, "name")`), so their arguments cannot be keyword-only — the same framework-entrypoint category as Typer/Temporal/pytest. Added those three decorator names to `BARE_FRAMEWORK_DECORATOR_NAMES` in the guard (matched bare or attributed, like `fixture`), reverted the `*` on `text_format` / `tag` / `with_images`, added two guard tests, and documented it in `convention.md`. This was discovered the hard way: the type checkers are blind to the engine's dynamic positional invocation, so the breakage only surfaced in `make agent-test` (513 e2e failures, all the prompt-render path through the `format` filter). Single-arg filters (`escape_script_tag`) are compliant anyway; a future multi-arg filter without one of these decorators falls back to the `# kw-only: ignore` hatch.
- **The existing-`*` trap (Wave 1 mechanical learning).** A function can carry a bare `*` and STILL be a violation when two-or-more positional-or-keyword params sit BEFORE it (`def f(a, b, *, c)` — `b` is a second positional). The fix is to MOVE the `*` to right after the subject, not skip the function. Six functions were initially mis-skipped by the signature agents on a naive "already has a `*`" check (`render_jinja2_sync/async`, `_compile_jinja2_template`, `make_jinja2_env_from_loader`, `_register_filters`, and three csv_codec writers) and fixed by hand. Instruct signature-editing agents to move an existing-but-too-late `*`, not skip.
- **Override cascades are deep — fix tree-wide in one pass.** Changing a base/Protocol signature (`PrettyRenderable.rendered_pretty`, `ContextProviderAbstract.get_typed_object_or_attribute`, `SecretsProviderAbstract.*`, `ReportingProtocol.set_event_log`) forces every `@override` impl to match (pyright `reportIncompatibleMethodOverride`). `rendered_pretty` had ~25 impls across `core/stuffs/` and `builder/` in a multi-level inheritance tree where pyright only surfaces the next level after the current one is fixed — so a single tree-wide replacement of the identical signature is far faster than chasing pyright level by level. These impls are `@override` (guard-carved-out), so they don't affect baseline counts but DO require the `*` for type-checker parity.

## Current position

**Checkpoint B VERIFIED — Wave 1 landed, all uncommitted on `refactor/Function-calling-3`.** Wave 1 converted `tools/`, `errors/`, `reporting/`, `observer/`, `tracing/` (baseline 844 → 690). `make agent-check` and full `make agent-test` both green; guard unit tests 32/32. Files changed in the working tree: the ~40 source files in those packages (signatures), their call sites tree-wide (incl. `tests/` and a handful of cross-package callers in `cli/`, `cogt/`, `core/`, `system/`, `libraries/`), the `@override` impl signatures forced by the base changes (`core/stuffs/*`, `builder/pipe/*`, `builder/*` `rendered_pretty`; `core/memory/working_memory.py`; `tools/secrets/env_secrets_provider.py`), the guard (`check_keyword_only_cmd.py` — jinja2 carve-out) + its tests, `convention.md`, `CHANGELOG.md`, the regenerated `violations-baseline.txt` (690) + `inventory.json`, this file, and `TODOS.md`. **Next: Wave 2** — domain core `core/` → `language/` → `kit/` → `libraries/` (Phase 3). `core/` (110) is the biggest call-site diff in the project; consider giving it its own reviewable slice.

**Exception-2 directional-pair resolution (decided in Wave 1):** `copy_file`, `has_diff_dirs`, `sync_toml_values` were all resolved by the simple reshape — subject stays positional, the second operand and all options become keyword-only (`copy_file(source_path, *, target_path, overwrite=True)`). We did NOT extend the allowlist with a per-entry leading-positional-count; the reshape is fully compliant and the src/dst split at call sites reads fine. Apply the same reshape to any future directional-pair-plus-options helper.

**Execution recipe that worked for Wave 1 (reuse for later waves):**

1. Get the package's violations: `.venv/bin/pipelex-dev check-keyword-only --report` (writes to stderr; grep the package section).
2. Add the bare `*` after the subject param of each flagged function — parallelizable across conflict-free subagents partitioned by file (signature edits only; warn them about the existing-`*` trap above). For a big package do this in file-disjoint groups.
3. Run `.venv/bin/pyright --outputjson` and bucket errors by rule: `reportCallIssue` (broken call sites) + `reportIncompatibleMethodOverride` (base/Protocol changes cascading to `@override` impls). The `reportUnknown*` errors are downstream noise that clears once the calls type-check — ignore them.
4. Fix override impls tree-wide first (one replacement per identical signature), then fix call sites — parallelizable across subagents partitioned by CALLER file (disjoint → conflict-free). Map positional→keyword by reading each callee's new signature; the `*` position tells you which args must be named. Caveat: agents must call pyright with ABSOLUTE venv paths (a `cd && .venv/bin/pyright` resets cwd between bash calls and silently returns "0 errors" — false green).
5. `make agent-check` until clean (pyright + mypy + guard).
6. **`make agent-test` is non-negotiable** — pyright/mypy are BLIND to dynamic positional invocation (Jinja2 filters, `getattr`, `**kwargs` forwarding, `functools.partial`). Wave 1's 513-failure regression came entirely from the Jinja2 filter path and would have shipped on a green agent-check. Marker: `-m "(dry_runnable or not (inference or llm or img_gen or extract or search)) and not pipelex_api"`.
7. `.venv/bin/pipelex-dev check-keyword-only --regen-baseline` to prune the now-fixed entries, then `make cko` to confirm the guard is green against the shrunk baseline.

## Resume commands

Run from the repo worktree root (`/Users/lchoquel/repos/Pipelex/_calls`), using the project virtualenv.

```bash
# 1. Verify Checkpoint A: lint + full suite must pass (do this FIRST).
make agent-check
make agent-test

# 2. Confirm the guard is green against its baseline (single-line Make mode).
make check-keyword-only            # alias: make cko

# 3. Inspect the full inventory grouped by package (drives the wave burn-down).
.venv/bin/pipelex-dev check-keyword-only --report

# 4. After migrating a package: delete its now-fixed keys from the baseline,
#    then regenerate to prune any remaining stale entries and re-verify.
.venv/bin/pipelex-dev check-keyword-only --regen-baseline
make check-keyword-only

# 5. Run the guard's own unit tests.
.venv/bin/pytest -q tests/unit/pipelex/cli/dev/test_check_keyword_only_cmd.py
```
