# Autofix — step 5 design: human CLI surfacing

Detailed design and working plan for master-plan step 5 (human CLI surfacing: `pipelex fix bundle` + the `💡 Suggested fix:` line in `pipelex validate`), on branch `feature/Autofix-step5` (base: the PR #1035 squash `611644e82`, which landed steps 3 + 4). Map: [master-plan.md](master-plan.md). Architecture and per-checkpoint findings: [suggested-fixes-design.md](suggested-fixes-design.md). Steps 3 + 4 record: [step3-step4-hardened-loop-and-agent-apply.md](step3-step4-hardened-loop-and-agent-apply.md).

**Status: ALL PHASES (A–D) DONE — `--diff` shipped (GO); awaiting CHECKPOINT B (exit review fan-out).**

**NEXT ACTION (cold start): CHECKPOINT B** — fresh-context `/code-review` on the step-5 diff, triage, then flip the master plan to step 5 DONE and record the step-6 hand-off notes. Phases A + B landed exactly per the design below; decisions taken and deltas from plan:

- **Shared human resolver** (`pipelex/cli/commands/bundle_path_resolver.py`): parameterized by `command` name + a per-command `not_a_bundle_hint` (validate's wording preserved verbatim); the `~`-expansion gap the agent side had fixed in PR #1035 triage **did** exist on the human side and is fixed in the helper (pinned by tests).
- **Flag-and-fix, telemetry**: `execute_validate` double-suffixed its `CLI_COMMAND` tag ("validate bundle bundle") — it now tags `telemetry_command_label` verbatim.
- **Flag-and-fix, rendering (beyond the planned factory-error change)**: routing the human renderer through the shared items means (a) a message-only `ValidateBundleError` (e.g. TOML parse failure) now renders the fallback residual item — previously the human saw NO detail at all; (b) pipe-validation errors now show `└─ Source:` when the item carries it. Both pinned by tests.
- **Dry-run channel kept lossless**: the wire builder suppresses the dry-run residual when categorized errors exist; `handle_validate_bundle_error` still prints `exc.dry_run_error_message` in that case (pinned).
- **E2E**: human subprocess E2E reuses the agent hermetic-HOME harness via a `tests/e2e/pipelex/cli/conftest.py` fixture re-export.
- **GO on `--diff`**: mechanics look tractable; key subtlety recorded — when the entry file lies under an explicit `-L` dir (directory mode), the sandbox entry path must be the file *inside* the mirrored dir copy, not a separate copy, or the loop would load duplicate pipes.

## Both gates are met (sequencing doctrine)

The master plan gates step 5 on two bars, both cleared:

1. **Abstraction stress-tested by rules of different shapes** — the step-2 exit verdict in the design doc ("Step-2 exit — abstraction verdict"): `SuggestedFix`/`FixOp` survived multi-op, delete, blueprint-channel, and rename fixes with no structural change; `description` is a stable one-line human string across all four rules.
2. **The apply command exists** — `pipelex-agent fix bundle` shipped in step 4 (PR #1035), so the human hint has an action behind it.

## Scope

Two pieces, landed together for symmetry (per the master plan):

- **`pipelex fix bundle`** — human command wrapping the same `fix_bundle_file` loop, with Rich-rendered output that names every change made.
- **`💡 Suggested fix:` line** — per fixable error in `pipelex validate`'s error rendering, showing `SuggestedFix.description` only (ops stay machine-facing), plus an actionable footer naming the `pipelex fix` command.
- **`--diff` preview** (show, don't write) — listed in the design doc's wave-1 CLI surface and explicitly deferred from step 4 to here ("preview belongs to the human command"). Scoped as the last phase and **cuttable**: the step-5 exit criteria don't require it, so if it fights back it becomes a deferred item rather than blocking the step.

**Out of scope:** the step-6 release train (user-facing docs page, conformance fixture regen, release cut); wave-2 surfaces (API `POST /fix`, MCP, editor); `--unsafe` (no UNSAFE rule exists in wave 1); richer still-invalid *markdown* for the agent command (only if Phase B's item renderer makes it free — see D5.5).

## What step 5 builds on (verified inventory)

- **The loop** — `fix_bundle_file(mthds_file_path, *, library_dirs, allow_signatures, max_iterations, select_codes, ignore_codes) -> FixBundleResult` (`pipelex/pipeline/fixes/fix_loop.py:292`). `FixBundleResult` (frozen, `fix_loop.py:47`): `is_valid`, `iterations`, `fixes_applied: list[SuggestedFix]`, `files_written: list[str]` (resolved paths, first-write order), `remaining_errors: list[ValidationErrorItem]`, `pending_signatures`, `is_runnable`, `bail_reason`. `max_iterations=None` resolves to `builder_config.fix_loop_max_attempts` (default 10). `select_codes`/`ignore_codes` filtering lives inside the loop, so the human command inherits it for free (that was step 4's stated intent).
- **The planner** — `plan_fix_for_pipe_validation_error` / `plan_fix_for_blueprint_validation_error` (`pipelex/pipeline/fixes/planner.py:30` / `:132`): pure functions, one raw error-data item → `SuggestedFix | None`. `KNOWN_FIX_CODES` frozenset at `planner.py:20`. `SuggestedFix` (`pipelex/suggested_fix.py:65`): `fix_code`, `description`, `safety`, `source`, `ops`.
- **The items builder** — `build_validation_error_items` (`pipelex/pipeline/validation_errors.py:24`) is the single source of truth attaching `suggested_fix` to items; called by the agent CLI, the API 422 (`ValidateBundleError.to_error_report`, `pipelex/pipeline/exceptions.py:154`), and the fix loop. `ValidationErrorItem` (`pipelex/base_exceptions.py:269`) carries the **union** of every field the human renderer prints (`error_type`, `pipe_code`, `concept_code`, `domain_code`, `source`, `field_path`, `field_name`, `variable_names`, `message`, `category`) plus `suggested_fix` — this is what makes D5.5's item-routing viable.
- **The agent command to mirror** — `pipelex/cli/agent_cli/commands/fix/bundle_cmd.py` (options, rule-filter validation `_reject_invalid_rule_filters` at `:26`, runnability gate) and the CLI-free markdown renderer `format_fix_markdown` (`pipelex/pipeline/fixes/fix_render.py:16`). The markdown renderer is **not** reused for humans (headings/backticks are agent presentation); its *structure* — title by verdict, per-fix `fix_code` + description + source-when-not-entry, files written — is the template.
- **The human validate command to mirror** — group registration in `pipelex/cli/commands/validate/app.py`; path resolution inline in `pipelex/cli/commands/validate/bundle_cmd.py:50-99` (directory auto-detect of `DEFAULT_BUNDLE_FILE_NAME`, single-`*.mthds` fallback, ambiguous → exit 2, directory injects itself into library dirs); setup/run/teardown wrapper `execute_validate` in `commands/validate/_validate_core.py:208`.
- **The human renderer to change** — `_display_validation_error_details(console, *, exc)` (`pipelex/cli/error_handlers.py:251`) iterates the **raw** `exc.pipelex_bundle_blueprint_validation_errors` / `exc.pipe_validation_errors` lists by hand — which do not carry `suggested_fix`. Its wrapper `handle_validate_bundle_error` (`error_handlers.py:323`) already computes `report = exc.to_error_report()` (items included) at `:330` and already uses the emoji conventions (`❌`, `💡 Tip:`).
- **Human CLI registration** — root Typer app in `pipelex/cli/_cli.py`: `_CORE_COMMAND_ORDER` (`:27-39`) + `app.add_typer(...)` calls (~`:222-234`).

## Design decisions

### D5.1 — Command layout: `pipelex fix bundle`, mirroring the validate group

New group `fix` beside `validate`/`run`: `pipelex/cli/commands/fix/app.py` (one `bundle` subcommand, no group callback — house style) + `commands/fix/bundle_cmd.py` + `commands/fix/_fix_core.py` (the setup/run/teardown wrapper, modeled on `_validate_core.execute_validate`: Pipelex boot with the same profile validate uses, `asyncio.run(fix_bundle_file(...))`, teardown in `finally`, `except typer.Exit: raise` before the catch-all, telemetry label `fix bundle`). Register in `_cli.py`: add `"fix"` to `_CORE_COMMAND_ORDER` right after `"validate"` and `app.add_typer(fix_app, name="fix", ...)`.

Why a group with one subcommand rather than a bare `pipelex fix <path>`: symmetry with both the human `validate` group and the agent `fix` group — every bundle-shaped surface reads `<cli> <verb> bundle <path>`, and wave 2 may grow `fix pipe`/`fix method` the way validate did.

### D5.2 — Shared human bundle-path resolution (fix must patch exactly what validate judged)

Step 4's D4.6 established the principle on the agent side (shared `agent_cli/commands/bundle_path_resolver.py`); the human side still has the resolution inlined in `validate/bundle_cmd.py:50-99`. Factor it into `pipelex/cli/commands/bundle_path_resolver.py` (human-side helper, `typer.secho` + exit-2 presentation preserved verbatim) and adopt it in **both** `validate bundle` and `fix bundle` in this change — identical resolution is a correctness requirement, not a nicety, because a directory argument defines the write scope (D3.3: the injected dir is user-passed, hence writable).

Not unified with the agent resolver in this step: the two differ exactly in error presentation (human text stream vs agent error envelope), and parameterizing that is more machinery than duplicating ~40 lines of resolution whose *semantics* are pinned by tests on both sides. Candidate follow-up if a third consumer appears. **Flag-and-fix while in there:** the PR #1035 triage fixed a missing `~` expansion in the agent resolver — check whether the human validate path has the same gap and fix it in the new helper if so.

### D5.3 — Options

| Option | Semantics |
| --- | --- |
| `path` (arg) | `.mthds` file or directory — same resolution as human `validate bundle` via the D5.2 helper. |
| `-L/--library-dir` | Repeatable, as in validate. Per D3.3 these dirs are the write scope beyond the entry file. |
| `--max-iterations` | `int \| None`, min 1; `None` → the `fix_loop_max_attempts` config default. |
| `--select` / `--ignore` | Repeatable fix-rule codes; mutually exclusive (both → exit 2); unknown code → exit 2 listing `KNOWN_FIX_CODES`. Same *behavior* as the agent command; the validation check is tiny — reuse `_reject_invalid_rule_filters` if its error presentation is plain enough for the human stream, else duplicate the two checks with `typer.secho` wording. |
| `--allow-signatures` | Mirrors the agent fix gate: without it, a valid-but-not-runnable result (pending signatures) exits 1 with the signatures listed; with it, exit 0. |
| `--diff` | Show, don't write (Phase C — see D5.6). |

Deliberately absent: `--format`/`--error-format` (human command — Rich console only; the two-stream convention is the agent CLI's); `--orchestrator` (validate-specific boot-verification flag; the fix loop re-validates in-process by design); `--pipe` (fix is whole-bundle); `--unsafe` (no UNSAFE rule in wave 1).

### D5.4 — Human rendering of `FixBundleResult`

Rendered via `get_console()` Rich markup matching `error_handlers.py` conventions (`escape()` on all interpolated strings, `❌`/`💡`/`✅` emoji register). Rendering lives in the fix command layer (`_fix_core.py` or a small sibling `_render.py`), **not** in `fix_render.py` — that module stays the CLI-free agent/API markdown renderer.

- **Valid after the loop** (fixes applied): `✅ Bundle fixed — valid`, the bundle path, then a numbered list naming every change (the step-5 exit bar): `SuggestedFix.description`, with the `fix_code` dim and the source file named when it isn't the entry bundle; then `Files written:` (each resolved path) and the iteration count. Exit 0.
- **Already valid** (`iterations == 0`, nothing applied): `✅ Bundle already valid`, exit 0.
- **Valid but not runnable** without `--allow-signatures`: pending signatures listed, `💡 Tip:` explaining `--allow-signatures` vs providing implementations, exit 1 (mirrors the agent gate).
- **Still invalid**: what *was* applied (same named-change list — partial progress is normal), the `bail_reason` when present (the loop's bail wordings are already human-actionable, e.g. the out-of-scope one names the `-L` remedy), then the remaining errors rendered through the **same item renderer as validate** (D5.5) so the two commands can't drift, then the standard tip/links block. Exit 1.
- **No verdict** (bad path, ambiguous bundle, init failure, unexpected exception): exit 2, same handler cascade as human validate.

Exit codes are presentation; the human-facing "contract" is the rendered text. Ops are never rendered — `description` only, per the master plan.

### D5.5 — The `💡 Suggested fix:` line: route the human renderer through the shared items

Rewrite `_display_validation_error_details` to consume `ValidationErrorItem`s instead of the raw exception lists — `handle_validate_bundle_error` already computes `exc.to_error_report()` at `error_handlers.py:330`, so the items (with `suggested_fix` attached by the one shared builder) are already in hand; the renderer signature changes to take the report's items (or the exception grows nothing). Group items by `category` to keep the current section headers (`Blueprint Validation Errors:` / `Pipe Validation Errors:` / dry-run), keep the per-error field lines as today (every printed field exists on the item), and append per item, when `suggested_fix` is present:

```
   [green]💡 Suggested fix:[/green] {escape(item.suggested_fix.description)}
```

After the error sections, when at least one item is fixable, one actionable footer (this is the doctrine's "a hint needs an action behind it"): `💡 {n} of these errors can be fixed automatically — run: pipelex fix bundle {bundle_path}` (append the `-L` dirs when the invocation had them — thread `library_dirs` into `handle_validate_bundle_error` alongside the existing `bundle_path` param). The existing generic `💡 Tip:` line stays but yields to the footer when fixes exist (two stacked 💡 tips is noise — prefer the actionable one).

Why item-routing over calling the planner inline per raw error (the master plan names both): one engine feeding every surface is the track's guiding principle; the planner then runs in exactly one place (`build_validation_error_items`); and the item renderer is exactly what D5.4's still-invalid arm needs for `remaining_errors` (which are already items) — inline planner calls would leave the human path as the one surface with private wiring, which is the disease this track exists to cure. Fallback if item-routing churns the human output in ways review rejects: the planner functions are pure and take one raw error-data item, so the inline form stays a cheap plan B.

**Deliberate behavior change to pin:** the raw-list renderer silently skips `factory_errors`; the items include them (`PIPE_FACTORY` category). Routing through items makes factory errors visible in human validate output for the first time — that's a fix, not a regression (flag-and-fix rule); pin it with a test and note it in the CHANGELOG.

### D5.6 — `--diff` preview via a temp-copy sandbox (Phase C, cuttable)

The loop has no no-write mode, and re-validation loads from disk — so an honest preview runs the real loop against copies: mirror the entry file and each **explicit** `-L` dir into a scratch dir (preserving relative layout), remap `library_dirs` to the copies, run `fix_bundle_file` there, then render a unified diff (original vs copy) for each `files_written`, via Rich syntax highlighting. Originals untouched (pinned by test); exit codes keep the same verdict semantics (0 valid-after / 1 still-invalid) so `--diff` answers "would it converge?". Ambient-resolved dirs are not copied — they're read-only under D3.3 in the real run too, so behavior matches. Entry-only invocations (no `-L`) copy just the entry file and pass `library_dirs` through unchanged (`None` stays `None`: ambient dirs load identically from the copy's run since they're absolute).

If the temp-copy mechanics surface real complications (path remapping in rendered output, ambient-dir edge cases), cut the flag to a deferred item at the mid-step checkpoint — the exit criteria don't need it.

## Phases (TDD — red tests first per layer)

### Phase A — `pipelex fix bundle` — DONE

- [x] Factor the human bundle-path resolution helper (`commands/bundle_path_resolver.py`) out of `validate/bundle_cmd.py`; validate's existing tests stay green; check/fix the `~`-expansion gap (D5.2); unit tests for the helper.
- [x] `commands/fix/` package: `app.py`, `bundle_cmd.py`, `_fix_core.py`; registration in `_cli.py` (`_CORE_COMMAND_ORDER` + `add_typer`) (D5.1).
- [x] Options + validation: `--select`/`--ignore` mutual exclusion and unknown-code rejection (exit 2), `--max-iterations` min 1, `--allow-signatures` gate (D5.3).
- [x] Human rendering of all five verdict arms (D5.4), with unit tests asserting rendered output per arm (patched `fix_bundle_file`) at `tests/unit/pipelex/cli/commands/fix/test_fix_bundle_human_format.py`.
- [x] Integration: `tests/integration/pipelex/cli/test_fix_bundle_human.py` against the real loop on `tmp_path` bundles: fixable → exit 0 + file fixed on disk; unfixable → rendered failure + exit 1; `--select` honored; directory mode.
- [x] E2E: subprocess `pipelex fix bundle` at `tests/e2e/pipelex/cli/test_fix_bundle_cmd.py`, reusing the agent hermetic-HOME harness via a local conftest re-export.

### Phase B — `💡 Suggested fix:` in validate rendering — DONE

- [x] Tests: `tests/unit/pipelex/cli/test_validate_suggested_fix_rendering.py` (💡 line, footer with `-L` echo, footer-replaces-tip, factory-error section, dry-run kept lossless) + integration pin `tests/integration/pipelex/cli/test_validate_suggested_fix_integration.py`.
- [x] Rewrote `_display_validation_error_details` into the item-driven `display_validation_error_items` (D5.5); threaded `library_dirs` into `handle_validate_bundle_error` for the footer; section headers and per-field lines kept byte-comparable wherever the item carries the same data.
- [x] Wired D5.4's still-invalid arm to the same item renderer (remaining_errors) — one renderer, two commands.

### CHECKPOINT A (mid-step) — CLEARED

The step-5 exit criteria are functionally met: a human sees the suggestion in `validate` and applies it with `fix`, with output naming every change. Committed; status block updated. **GO on `--diff`** (see status block for the recorded sandbox-layout subtlety).

### Phase C — `--diff` preview — DONE (GO)

- [x] Temp-copy sandbox (`commands/fix/_diff_sandbox.py`: `mirror_bundle_for_preview` + `PreviewSandbox.to_original`) + diff rendering (`_print_preview_diffs`, would-be labels via `preview=True` in the result renderer, copy→original path remap for display); unit tests for the copy/remap helper (`test_diff_sandbox.py`) incl. the entry-inside-`-L`-dir layout subtlety; integration pins: `--diff` on a fixable bundle prints the diff with ORIGINAL paths, originals byte-identical, exit codes match the write-mode verdicts (0 would-converge / 1 would-still-be-invalid).

### Phase D — docs, changelog, gates — DONE

- [x] CHANGELOG `[Unreleased]`: `pipelex fix bundle` (+`--diff`), `💡 Suggested fix:` lines + actionable footer, item-routed human rendering changes (factory errors, parse-level message, pipe-error source), `~`-expansion fix, telemetry-label fix.
- [x] Repo docs sweep: new `docs/tools/cli/fix.md` reference page (+ mkdocs nav); fix rows/links added to `docs/tools/cli/index.md`, `docs/tools/cli/validate.md` ("Suggested Fixes" section), `docs/features/cli.md` (human + agent tables — the agent `fix` row was missing since step 4).
- [x] `make agent-check` green; full `make agent-test` green.

### Exit — CHECKPOINT B (step-5 exit)

House pattern: fresh-context `/code-review` fan-out on the step-5 diff; fix confirmed bugs, defer real tradeoffs to `deferred-checkpoint-e-review-items.md` (next free letter). Update this doc's status block, the master plan (step 5 → DONE), and the wip README. Record the step-6 hand-off notes: the CHANGELOG entry must also mention the additive `suggested_fix` wire field in `/validate` API payloads (deferred item 1c) and the conformance fixture regen (deferred item 2) — both are step-6 release-train items this step must not silently absorb.

## Test map (new / extended)

- `tests/unit/pipelex/cli/` — human fix command format tests (patched loop; all verdict arms; option validation), bundle-path-resolver helper tests, validate-rendering 💡 tests (Phase B pins).
- `tests/integration/pipelex/cli/` — `test_fix_bundle_human.py` mirroring `test_agent_fix_bundle.py`; validate-output integration pin for the 💡 line on a real fixable fixture.
- `tests/e2e/` — subprocess `pipelex fix bundle` (harness per Phase A's finding).
- Phase C adds copy-sandbox unit tests + the originals-untouched integration pin.

## Cold-start pointers

- Fixtures: `tests/data/fixes/` holds `<name>.mthds` + `<name>.golden.mthds` pairs per rule — reuse them (always on `tmp_path` copies; the command mutates files).
- Unit tests drive the loop with `mocker.patch("pipelex.pipeline.fixes.fix_loop.validate_bundle", side_effect=[...])` and patch `...fix_loop.resolve_library_dirs` for ambient-dir cases; pass `max_iterations` explicitly to avoid needing a booted config (step-3/4 doc, implementation record).
- Golden `.mthds` fixtures are processed by `plxt format` during `make agent-check` — write, format, then derive goldens; fresh worktrees need `pipelex-dev generate-mthds-schema` before `plxt lint`.
- A dotted `main_pipe = "domain.pipe"` is itself invalid (strip-namespace fires) — multi-file fixtures must use the bare form.
- Known-inert collision gap in `_split_cross_file_collisions` (intra-round duplicate bare codes): documented in [pr-1035-review-notes.md](pr-1035-review-notes.md) — don't re-report it; revisit only if blueprint-parse error accumulation changes.
