# Autofix — steps 3 + 4 design: hardened loop + agent apply surface

Detailed design and working plan for master-plan steps 3 (hardened loop — real multi-file targeting) and 4 (agent apply surface — `pipelex-agent fix bundle`), landing together on the stacked branch `feature/Autofix-step4-Agnt-Apply` (base: `feature/Autofix-step2`, PR #1031). Map: [master-plan.md](master-plan.md). Architecture and per-checkpoint findings: [suggested-fixes-design.md](suggested-fixes-design.md).

**Status: STEP 4 CODE COMPLETE (2026-07-08) — `make agent-check` + touched tests green, CHECKPOINT 2 review NOT yet run.** CHECKPOINT 1 review on the step-3 diff is complete; confirmed bugs were fixed in this pass (signature-only sibling headers no longer block valid concrete renames, input-drift source threading is pinned, collision-map rebuilds are pinned, and `files_written` order/dedupe is pinned). Step 4 now ships `pipelex-agent fix bundle`, the CLI-free fix renderer, command/unit/integration/e2e coverage, agent CLI docs, and a CHANGELOG entry. The current step-4/checkpoint-review changes are **uncommitted** on `feature/Autofix-step4-Agnt-Apply` (base commit `a6ffae486`).

**NEXT ACTION (cold start): run CHECKPOINT 2** — fresh-context `/code-review` fan-out on the step-4 diff (from `a6ffae486` to the current working tree), plus the checkpoint-1 review fixes listed above. Fix confirmed bugs, defer tradeoffs to a new `deferred-checkpoint-e-review-items.md` only if real tradeoffs remain, then update this doc, the master plan, and the README before landing.

### Implementation record (what a cold session needs to know beyond the design)

- **D3.1** — `_backfill_pipe_error_source` in `pipelex/pipeline/validate_bundle.py`, called first thing in the `except PipeValidationError` arm of `_translate_to_validate_bundle_error`. Full-pipe_ref lookup only; miss leaves `file_path=None`. Pins: 3 new pipe-channel tests in `test_validate_bundle_source_threading.py`.
- **D3.2–D3.5** — `fix_loop.py` was substantially rewritten. Helper names: `_safe_fixes` (SAFE + single-file gate + select/ignore filters), `_partition_by_write_scope`, `_pipe_codes_by_file` (per-file map over entry + resolved dirs, rebuilt per iteration), `_colliding_op_name` + `_split_cross_file_collisions` (per-target), `_fix_target_path` (source → resolved Path, else entry). `FixBundleResult.files_written: list[str]` = **resolved** paths, first-write order, deduped. Out-of-scope bail wording: `fixes target files outside write scope: <paths> — pass their directory with -L/--library-dir to allow writing`. Cross-file bail wording changed to `…would write a pipe code (…) already declared in a sibling bundle` (covers renames AND main_pipe set_keys). Mixed scope proceeds with in-scope fixes (no all-or-nothing).
- **D3.6 categorizer half** — `_main_pipe_strip_would_retarget` → `_main_pipe_strip_is_safe` (XOR predicate: safe iff exactly one of dotted/bare exists as a `[pipe]` key) in `validation_error_categorizer.py`; call site inverted (`not _main_pipe_strip_is_safe`). Cross-ref comment in `pipelex_bundle_blueprint.py` updated.
- **D3.6 loop half** — the `main_pipe` `SET_KEY` drop needs only ONE condition (`value in other-file pipe codes`): "paired rename was dropped as colliding" is subsumed, since a rename is dropped iff its `new_key` is declared elsewhere, and that `new_key` equals the `main_pipe` value.
- **Step-4 early items already DONE**: `fix_bundle_file(..., select_codes=None, ignore_codes=None)` filtering inside `_safe_fixes` + `KNOWN_FIX_CODES` frozenset in `planner.py` (pins: `tests/unit/pipelex/pipeline/fixes/test_fix_loop_select_ignore.py`); shared `pipelex/cli/agent_cli/commands/bundle_path_resolver.py` (`resolve_bundle_target(path, *, library_dir) -> tuple[str, list[str] | None]`) adopted by `validate bundle` verbatim-behavior (its now-stale `# type: ignore[arg-type]` comments removed; validate tests green).
- **CHECKPOINT 1 review fixes DONE**: `_pipe_codes_by_file` now excludes typeless signature-only sections from hard collision checks, because same-batch crate merge permits a concrete pipe to replace a matching `PipeSignature`; new pins cover sibling signature headers, input-drift `source` on entry and sibling files, per-iteration collision-map rebuilds, and first-write-order `files_written`.
- **Step 4 implementation DONE**: new `fix` agent CLI group registered after `validate`; `fix bundle` uses shared bundle-path resolution, validates mutually-exclusive/unknown rule filters, initializes Pipelex with the validate profile, runs `fix_bundle_file`, emits success via `format_fix_markdown`, and emits still-invalid verdicts as `FixBundleError` with the full `FixBundleResult` payload. Tests added: renderer unit tests, patched command-format unit tests, real-loop command integration tests, and subprocess e2e tests.
- **Corruption-regression fixture gotcha**: a dotted `main_pipe = "domain.pipe"` is itself invalid (strip-namespace fires) — multi-file fixtures must use the bare form (`main_pipe` resolution is bundle-local, so bare codes duplicated across domains in sibling files are fine).
- Unit tests drive the loop with `mocker.patch("pipelex.pipeline.fixes.fix_loop.validate_bundle", side_effect=[...])` and, for ambient-dir cases, patch `...fix_loop.resolve_library_dirs`; pass `max_iterations` explicitly (or patch `...fix_loop.get_config`) to avoid needing a booted config.

## Scope

- **Step 3** replaces the spike's conservative scoping guard with real multi-file targeting: pipe-channel errors get a populated `source`, the single-file gate derives from *resolved* library dirs, fixes apply to the file that declares the offending item, and only user-passed files are ever written. Closes deferred items 0 and 1 ([deferred-checkpoint-0-review-items.md](deferred-checkpoint-0-review-items.md)) and the two halves of checkpoint-C item 1 ([deferred-checkpoint-c-review-items.md](deferred-checkpoint-c-review-items.md)). Also wires the orphaned `fix_loop_max_attempts` config.
- **Step 4** ships `pipelex-agent fix bundle`: a thin command over `fix_bundle_file` following the agent CLI's two-stream output conventions, plus `--select`/`--ignore` rule filtering in the loop, a CLI-free markdown renderer, and e2e CLI tests. This is the milestone where an agent runs validate → fix → re-validate entirely from the CLI.

**Out of scope** (unchanged deferrals): the human CLI (`pipelex fix` + the `💡 Suggested fix` line — step 5, gated on this branch), `--diff` preview (step 5, see D4.2), checkpoint-C item 2 (one-rename-per-iteration convergence cap — mitigated here by the config default, the aggregate-raise refactor is its own chunk), checkpoint-D item 1 (dotted-key controller inputs — accepted fail-safe), wave-2 surfaces (API `POST /fix`, MCP, editor).

## Where the code stands (step-2 exit)

- **The guard to replace.** `_applicable_safe_fixes` (`pipelex/pipeline/fixes/fix_loop.py:64-83`) keeps a source-less fix only when `is_single_file`, and a sourced fix only when `Path(source) == mthds_file_path`. The call site computes `is_single_file=library_dirs is None` (`fix_loop.py:172`) — wrong in both directions: explicit `[]` (documented "no libraries") is treated as multi-file (fixes over-dropped), and `None` can fall through to hub defaults / `PIPELEXPATH` and load other files while being treated as single-file.
- **Pipe-channel `source` is dead code.** `categorize_pipe_validation_with_libraries_error` reads `pipe_error.file_path` (`pipelex/core/pipes/handle_pipe_errors.py:199`), but no raise site ever sets it — so `match-sequence-output` and `sync-controller-inputs` fixes are source-less and get dropped whenever library dirs are in play. The blueprint channel (`strip-native-concept-redecl`, `strip-namespace`) is already populated from `blueprint_dict["source"]`.
- **Provenance already exists — no new bookkeeping needed.** `LibraryManager._pipe_source_map: dict[str, Path]` (pipe_ref → declaring `.mthds` file, `pipelex/libraries/library_manager.py:101`) is populated during load (`library_manager.py:505-507`, fed by `LibraryCrate.source_map`, which tracks the winning declaration across duplicates) and exposed via `get_pipe_source()` (`library_manager.py:235`). Population happens in the same loop that builds pipes, *before* `library.validate_library()` runs — so the map is live when any pipe-validation error propagates.
- **Pipes deliberately do not carry their source.** `_make_pipe_data_for_registry` (`pipelex/core/pipes/pipe_abstract.py:160-167`) grafts `source` from the crate map at serialization time precisely because `PipeAbstract` has no such field. Step 3 must respect that design.
- **The loop is single-file and nothing calls it.** One DOM load / one write per iteration (`fix_loop.py:205-215`); the applier (`apply_fix_ops` / `serialize_and_format`) is already per-DOM and needs no change. `fix_bundle_file` has no production caller — the fingerprint already includes `source`, so cross-file no-progress detection works unchanged. The config `fix_loop_max_attempts = 10` (`pipelex/pipelex.toml:53`, `BuilderConfig` in `pipelex/system/configuration/configs.py`) is defined but unwired; the code hardcodes `max_iterations: int = 5`.

## Step 3 — hardened loop

### D3.1 — Thread `source` at the catch boundary, not the raise sites

Backfill `pipe_error.file_path` in the shared translate funnel in `pipelex/pipeline/validate_bundle.py` (the `except PipeValidationError` arm, ~line 135), immediately before `categorize_pipe_validation_with_libraries_error` runs: when `file_path` is `None` and both `domain_code` and `pipe_code` are present, look up `get_library_manager().get_pipe_source(f"{domain_code}.{pipe_code}")` and set it. Use the full pipe_ref only — never the bare-code suffix fallback (bare codes are ambiguous across domains; that ambiguity is exactly what checkpoint C's cross-file guard defends against).

Why here and not the alternatives from deferred item 1:

- **Not a `source` field on `PipeAbstract`.** The codebase deliberately keeps provenance out of the runtime pipe model and looks it up from the crate when needed (see `_make_pipe_data_for_registry`); adding the field would change the pipe serialization surface for one consumer's benefit.
- **Not per-raise-site threading.** The raise sites (`pipe_abstract.py` input checks, `pipe_sequence.py` output checks) don't know the file, and every future enriched raise site would have to remember the same plumbing. One interception point covers them all, including the un-enriched raise sites (their errors gain a `source` locator for free — better error reports even without a fix).
- **Not a domain-qualifier check in the loop.** Domains legitimately span files, so a domain match cannot prove which file declares the pipe.

Lookup misses (either code absent, or the ref not in the map) leave `file_path` as `None` — the fix stays source-less and falls under the conservative single-file rule, which is the safe direction. The wrapped blueprint-stage `PipeValidationError` path in the categorizer already prefers `wrapped_pipe_error.file_path or source` and needs no change.

### D3.2 — Derive the single-file gate from resolved dirs

At loop start, resolve once: `effective_dirs, _ = resolve_library_dirs(library_dirs)` (`pipelex/hub.py:699` — per-call → hub instance default → `PIPELEXPATH` → none), and set `is_single_file = not effective_dirs`. This fixes both directions of deferred item 0: `[]` is now genuinely single-file (source-less fixes apply), and a `None` that fell through to ambient dirs is now multi-file (source-less fixes conservatively dropped). `validate_bundle` resolves through the same function internally, so the gate matches what validation actually loaded. The sibling pre-scan gate (`fix_loop.py:162`, currently `library_dirs is not None`) switches to `effective_dirs` too.

### D3.3 — Write-scope policy: only user-passed files are written

Per the rule guard already decided in the design doc ("only files the user passed to the command get written"):

- **Writable:** the entry `mthds_file_path`, plus any `.mthds` file under the *per-call* `library_dirs` argument when one was explicitly provided.
- **Read-only:** files loaded via ambient resolution (hub defaults, `PIPELEXPATH`) — the user did not pass those to *this* command. Fixes sourced there are excluded from the applicable set.
- Path comparisons normalize both sides with `.resolve()` (the current guard compares raw paths).

When applicable fixes exist but every one of them targets a read-only file, the loop returns `is_valid=False` with a bail reason naming the out-of-scope files ("fixes target files outside write scope: … — pass their directory with -L to allow writing"), so the outcome is loud and actionable rather than a silent no-op. The remaining errors still carry their `suggested_fix` (with `source`), so a consumer can see exactly what would have been done and where.

### D3.4 — Per-file apply, `files_written`, per-target collision scan

The apply phase groups the iteration's new fixes by target file (`Path(fix.source).resolve()`, defaulting to the entry file for source-less fixes), loads one tomlkit DOM per distinct target, applies that group's ops, and writes each changed file through `serialize_and_format` — the same load/apply/write shape as today, per file. `FixBundleResult` gains `files_written: list[str]` (ordered, deduped across iterations; additive field on a runtime-only model).

The cross-file rename-collision machinery becomes per-target: the sibling scan builds a per-file pipe-code map over *all* loaded files (still flat across domains — the checkpoint-C ambiguity rule stands), rebuilt each iteration now that multiple files can mutate, and a `RENAME_TABLE_KEY` targeting file F collides iff the bare `new_key` exists as a pipe key in any loaded file other than F.

### D3.5 — Wire `fix_loop_max_attempts`

`fix_bundle_file`'s signature becomes `max_iterations: int | None = None`; `None` resolves to `get_config().pipelex.builder_config.fix_loop_max_attempts` (config default 10). The hardcoded 5 is deleted — per the config rules, the default lives in `pipelex/pipelex.toml` only. This also softens (without fixing) checkpoint-C item 2's convergence cliff.

### D3.6 — Checkpoint-C item 1 lands here (both halves)

Step 3 rewrites exactly the code sites this deferral names, and multi-file writes make both failure modes more reachable, so the pair is in scope:

- **Categorizer half:** extend `_main_pipe_strip_would_retarget` (`pipelex/core/interpreter/validation_error_categorizer.py`) into a `_main_pipe_strip_is_safe` gate with the two-disjunct predicate from the deferral doc — the strip is enriched only when the bare tail already exists as a pipe key OR the dotted code itself exists as a key (its paired rename will materialize the target). Kills the "typo'd tail → SAFE fix rewrites `main_pipe` to a nonexistent pipe" mutation while keeping the convergent dotted-declaration happy path.
- **Fix-loop half (the PR #1031 cubic P2 gap):** in the cross-file collision split (`fix_loop.py:112-141` today), also drop a root `main_pipe` `SET_KEY` whose paired declaration rename was dropped as cross-file colliding, or whose value collides with a sibling file's pipe code — the categorizer cannot see cross-file state, so this suppression must live in the loop.

### Step-3 tasks (TDD — red tests first per layer)

- [x] Integration: `test_validate_bundle_source_threading.py` grows pipe-channel assertions — `INADEQUATE_OUTPUT_*` and input-drift errors carry `source` for entry-file and sibling-file pipes; lookup-miss leaves `source` absent.
- [x] `validate_bundle.py` funnel backfill (D3.1).
- [x] Unit: `is_single_file` derivation cases (`[]` single, `None`+hub-default multi, explicit dirs multi) in `test_fix_loop_multi_file_scoping.py`; loop switch to `resolve_library_dirs` (D3.2).
- [x] Unit: write-scope policy — sourced fix under `-L` applies to the declaring sibling; ambient-dir fix excluded with the out-of-scope bail reason (D3.3).
- [x] Loop rework: per-file grouping + `files_written` + per-target collision scan rebuilt per iteration (D3.4), with unit pins for grouping and collision.
- [x] Integration: `test_fix_convergence_loop.py` multi-file cascade — an error declared in a sibling file is fixed *in the sibling*; both files written and reported; **regression pin for the original corruption scenario** (same pipe code in two domains across two files → the fix patches the declaring file, never the entry file's same-named table).
- [x] Config wiring (D3.5) + `make tb` boot check.
- [x] Checkpoint-C item 1 pins per the deferral doc's "if revisited" notes: typo'd-tail strip suppressed (file untouched), dotted-declaration path still converges, two-file `main_pipe` `SET_KEY` dropped alongside its blocked rename (D3.6).
- [x] `make agent-check` + `make agent-test` green (full suite, 2026-07-08).

### Exit — CHECKPOINT 1 (step-3 exit)

Fixes apply correctly across multi-file bundles, targeting the declaring file only; the drop-everything guard is gone; the corruption-scenario regression test is green. House pattern: fresh-context `/code-review` fan-out on the step-3 diff; confirmed bugs fixed, tradeoffs deferred to a `deferred-checkpoint-e-review-items.md`. Update this doc's status block and the master plan, then hand off to step 4 (natural session boundary — step 4 opens the CLI surface, a different area).

## Step 4 — `pipelex-agent fix bundle`

### D4.1 — Command layout: mirror the `validate` group exactly

New group `fix` beside `validate`/`run`/`inputs`: `pipelex/cli/agent_cli/commands/fix/app.py` (`fix_app = typer.Typer(add_completion=False, no_args_is_help=True)`, one `bundle` subcommand, no group callback — options live on the subcommand, house style) and `commands/fix/bundle_cmd.py`. Register with `app.add_typer(fix_app, name="fix", ...)` in `_agent_cli.py` and add `"fix"` to `PipelexAgentCLI.list_commands()` right after `validate`. Init via `make_pipelex_for_agent_cli(library_dirs=..., needs_inference=False, needs_model_specs=True)` (same profile as validate — the loop's re-validation dry-runs, no live inference), `asyncio.run(fix_bundle_file(...))`, teardown in `finally`, `except typer.Exit: raise` before the catch-all — the full validate handler cascade.

### D4.2 — Options

| Option | Semantics |
| --- | --- |
| `path` (arg) | `.mthds` file or directory — same resolution as `validate bundle` (auto-detect the default bundle file name or a single `*.mthds`; ambiguous → exit 2; a directory injects itself into the library dirs, and being user-passed it is **writable** under D3.3). |
| `-L/--library-dir` | Repeatable, as in validate. Per D3.3 these dirs are the write scope beyond the entry file. |
| `--max-iterations` | `int | None`, min 1; `None` → the `fix_loop_max_attempts` config default. |
| `--select` / `--ignore` | Repeatable fix-rule codes; mutually exclusive (both → exit 2). Unknown code → exit 2 listing the known codes (exported as a frozenset beside the planner's fix-code constants). Implemented in the loop as keyword-only `select_codes`/`ignore_codes` filtering inside `_applicable_safe_fixes`, so step 5's human command inherits it for free. Failing fast on a typo beats lenient-ignore here: the flag selects *behavior* (what gets written), not presentation. |
| `--format` / `--error-format` | The two-stream convention: markdown default on stdout; `--error-format` inherits `--format` when omitted; first body line is `set_agent_cli_error_format(error_format or output_format)`. |

Deliberately absent: `--diff` (preview belongs to the human command, step 5 — agents run in repos and inspect diffs themselves, the loop has no no-write mode yet, and the result payload already names every op applied); `--pipe` (fix is whole-bundle by design); `--allow-signatures` (signatures are never errors and the fixer never touches them — runnability is validate's concern, and an agent chains fix → validate anyway); `--unsafe` (no UNSAFE rule exists in wave 1; the SAFE-only filter stays hardwired until the first UNSAFE rule arrives with its flag).

### D4.3 — Verdict, streams, exit codes

Mirrors `validate bundle`'s precedent (negative verdict → error stream):

- **Valid after the loop** (including already-valid, `iterations=0`): success payload on stdout via `agent_success_formatted(result, markdown_renderer=format_fix_markdown, output_format=...)`, exit 0.
- **Still invalid**: `agent_error(...)` on stderr with `error_type="FixBundleError"`, exit 1, message summarizing the outcome (iterations run, fixes applied, errors remaining, bail reason), and the full structured payload as envelope extras. Partial progress is normal here — the payload, not the exit code, tells the agent what advanced.
- **No verdict** (bad path, ambiguous bundle, init failure, unexpected exception): exit 2, same handlers as validate.

Contract vs presentation, per the workspace conventions: machine consumers branch on `is_valid` / `fixes_applied` / `remaining_errors`, never on the exit code.

### D4.4 — JSON contract

Both arms carry the same structured core — `FixBundleResult` dumped `mode="json", exclude_none=True` plus the envelope keys: `is_valid`, `bundle_path`, `iterations`, `fixes_applied[]` (full `SuggestedFix` dumps: `fix_code`, `description`, `safety`, `source`, `ops[]`), `files_written[]` (step 3), `remaining_errors[]`, `bail_reason` (omitted when absent). `remaining_errors[]` items are the same `ValidationErrorItem` shape as `validate`'s `validation_errors[]` (same builder), so an agent parses one error schema across both commands. Success arm adds `success: true`; error arm rides the standard `agent_error` envelope (`error_type`, `message`, extras).

### D4.5 — Markdown renderer (CLI-free)

`format_fix_markdown(result: dict[str, Any]) -> str` in a new `pipelex/pipeline/fixes/fix_render.py` — beside the engine, importable without Typer so the wave-2 API can reuse it (the design doc's stated placement intent). Success-arm rendering: `# Fix applied — bundle is valid` (or `# Bundle already valid` when nothing was applied), one bullet per applied fix (`fix_code` — description, naming the file when it isn't the entry bundle), a `Files written` list, and the iteration count. The still-invalid arm goes through the generic `agent_error` markdown envelope with the summary message; if agents turn out to need richer failure markdown, that refinement lands with step 5's human renderer, which will want the same thing.

### D4.6 — Shared bundle-path resolution helper

Factor `validate_bundle_cmd`'s path→bundle resolution (`commands/validate/bundle_cmd.py:94-131` — directory auto-detect, ambiguity errors, library-dir injection) into a shared helper module under `commands/`, adopted by both `validate bundle` and `fix bundle` in this change (no behavior change for validate; identical resolution is a correctness requirement — fix must patch exactly the file validate judged). Adoption by `run bundle` / `inputs bundle` is a follow-up, not scoped here.

### Step-4 tasks (TDD)

- [x] Loop: keyword-only `select_codes`/`ignore_codes` on `fix_bundle_file` + known-codes frozenset beside the planner constants, with unit pins (filtering, unknown code raises at the CLI layer only). (Landed early, with step 3.)
- [x] Shared path-resolution helper factored out + adopted by validate (D4.6), validate's existing tests staying green. (Landed early: `commands/bundle_path_resolver.py`.)
- [x] Renderer: `fix_render.py` + unit tests (fixed / already-valid / multi-file arms).
- [x] Command: `fix/app.py` + `fix/bundle_cmd.py` + registration (D4.1-D4.3), with `tests/unit/pipelex/cli/agent_cli/test_fix_format.py` mirroring `test_validate_format.py` (patched core; both format arms; exit 0/1; `--select`/`--ignore` mutual exclusion and unknown-code rejection).
- [x] Integration: `tests/integration/pipelex/cli/test_agent_fix_bundle.py` — the command function against the real loop on `tmp_path` *copies* of fixtures (the command mutates files): fixable bundle → exit 0 + file actually fixed on disk; unfixable → structured error payload; `--select` honored end-to-end.
- [x] E2E: `tests/e2e/agent_cli/test_fix_bundle.py` — subprocess `pipelex-agent fix bundle` in the hermetic/offline harness (`tests/e2e/agent_cli/conftest.py` pattern), asserting the JSON contract, stdout-cleanliness, and exit codes. (The master plan says "snapshot tests"; the repo has no snapshot framework — subprocess + JSON/string assertions is the house e2e pattern, and that's what ships.)
- [x] Docs plumbing: update `pipelex/cli/agent_cli/CLAUDE.md` (output-format section gains the fix command); CHANGELOG `[Unreleased]` entry for the new command. The user-facing docs page stays in step 6 per the master plan; the `mthds-agent` output-audit update is a cross-repo step-7 hand-off note.
- [x] `make agent-check` green; touched test slice green (`55 passed`: renderer/command/select-ignore/unit scoping/integration/e2e/checkpoint pins). Full `make agent-test` was not run in this pass.

### Exit — CHECKPOINT 2 (step-4 exit)

The command is shipped on the agent CLI and an agent can run validate → fix → re-validate entirely from the CLI; e2e tests green. House-pattern review fan-out on the step-4 diff. Update this doc, the master plan (steps 3 + 4 → DONE), and the wip README; record the step-5 hand-off list (what step 5 reuses: the loop's select/ignore params, `fix_render.py`, the shared path helper; candidate refinement: richer still-invalid markdown).

## Test map (new / extended)

- `tests/integration/pipelex/pipeline/test_validate_bundle_source_threading.py` — pipe-channel `source` backfill (D3.1).
- `tests/unit/pipelex/pipeline/fixes/test_fix_loop_multi_file_scoping.py` — resolved-dirs gate, write scope, out-of-scope bail (D3.2, D3.3).
- `tests/integration/pipelex/pipeline/test_fix_convergence_loop.py` — multi-file cascades, corruption-scenario regression, `files_written` (D3.4).
- `tests/integration/pipelex/pipeline/test_strip_namespace_enrichment.py` + `tests/unit/pipelex/pipeline/fixes/test_fix_convergence_loop.py` pins for checkpoint-C item 1 (D3.6).
- `tests/unit/pipelex/pipeline/fixes/test_fix_loop_select_ignore.py` — loop `select_codes`/`ignore_codes` pins (step 4, DONE).
- `tests/unit/pipelex/pipeline/fixes/test_fix_render.py`, `tests/unit/pipelex/cli/agent_cli/test_fix_format.py`, `tests/integration/pipelex/cli/test_agent_fix_bundle.py`, `tests/e2e/agent_cli/test_fix_bundle.py` — step 4 (TODO).

## Sequencing

Step 3 lands first and clears CHECKPOINT 1 before step 4 starts: the CLI's contract tests pin `FixBundleResult` (including `files_written` and the write-scope bail reasons), so the loop semantics must be frozen first. Both steps ship on this branch; step 5 (human CLI) remains gated on this branch's exit per the master plan's sequencing doctrine.
