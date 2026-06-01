# Dry-Run Validation Consolidation — Implementation Tracker

Execution spine for the in-process dry-run / validation consolidation on branch `feature/Validate-with-signatures-4-fix-dry-run`. This file tracks **what to do and what's done** for the consolidation only. The **design rationale** lives in [`wip/dry-run-refactor-draft/D-plan.md`](wip/dry-run-refactor-draft/D-plan.md) — referenced below as **§X** (this work is D-plan's "Part A", decisions D1–D3). When this tracker and D-plan disagree, D-plan is the source of truth for *intent*; update this tracker to match reality.

**Two backend follow-ups are deferred to their own branches** (split out 2026-06-01 to keep this tracker single-workstream and remove the Part-vs-Checkpoint naming clash):

- [`followup-leaf-run-mode-mock.md`](wip/dry-run-refactor-draft/followup-leaf-run-mode-mock.md) — move the LIVE/DRY decision down to the cogt leaf so DRY honors the Temporal backend (D-plan Part B / D4 / req 1).
- [`followup-temporal-validation-activity.md`](wip/dry-run-refactor-draft/followup-temporal-validation-activity.md) — run validation as a standalone Temporal activity (D-plan Part C / D5 / req 2).

## Eng-review decisions — 2026-06-01 (`/plan-eng-review`, locked)

Decisions from the review (apply these as you implement; they override the original phase prose where they conflict):

- **D1 — scope.** Ship **the consolidation alone** on this branch (Checkpoint C is the ship point). The two backend follow-ups move to their own branches (links above). The pipelex-api coupling is handled by D2, not a shim.
- **D2 — pipelex-api migrated in this branch's train (no compat shim).** `pipelex-api/api/routes/pipelex/build/runner.py:6` imports `dry_run_pipes` at **module scope** — deleting it boot-breaks pipelex-api. Migrate that route to the **public inner sweep** (see D6) in this consolidation's release train (Phase 3b).
- **D3 — union catch (intentional widening, not a port).** `BundleValidator`'s per-pipe classify-catch is `except (PipelexError, ValidationError, FactoryException)`. **This widens the catch on purpose — it is not the current surface.** Today `dry_run_pipe` uses a *narrow* tuple, `except (PipeStackOverflowError, ValidationError, PipeComposeError, FactoryException)` (`dry_run.py:84`), preceded by a **separate** `except PipeNotFoundError` clause (`dry_run.py:79`) that returns SKIPPED on the *bare top-level* error (today's `dry_run_pipe` calls `pipe.run_pipe()` directly, so the bare error surfaces). `PipeStackOverflowError` and `PipeComposeError` are both `PipelexError` subclasses (verified), so base `PipelexError` *subsumes* them. The widening is **required** by the refactor: `BundleValidator` runs each pipe through `PipeRun.run`, which re-raises the original (`pipe_run.py:99-100`) and the router may add `__cause__` links — so a cross-package dep no longer arrives as a bare `PipeNotFoundError`, it arrives **wrapped** (e.g. in a `PipeRunError`, itself a `PipelexError`). Only a base-`PipelexError` catch lets the recursive cause-walk reach it and reclassify SKIPPED. `ValidationError` (pydantic) and `FactoryException` (polyfactory) are **not** `PipelexError` subclasses, so they stay listed explicitly (the `FactoryException` arm is how a `PipeSignature` mint surfaces cleanly, comment `dry_run.py:85-87`). Wrap **both** `prepare_pipe_job` (mock-input build) and the run in one `try`; keep the `format_pydantic_validation_error` branch and the recursive `_root_cause_is(exc, PipeNotFoundError)` walk for SKIPPED — the helper must test `exc` **itself** and then its `__cause__`/`__context__` chain (not just the chain). **Behavior change to pin (new Phase-2 test):** a *non-dependency* `PipelexError` raised mid-run — one the narrow tuple would today let *escape and abort* the sweep — now classifies as a per-pipe **FAILURE**, not a sweep abort.
- **D4 — characterization test BEFORE Phase 1.** Pin `pipeline_run_setup`'s current observable behavior on **both** the success path (library open/teardown, `PIPELINE_EXECUTE` emitted, ContextVar restored) and the **load-failure** path (teardown still runs, no leak, exception propagates) before extracting the seams. "No behavior change" is a claim, not a fact, on a 364-line ordering-sensitive function.
- **D6 — two explicit lifecycles (generalizes D2).** `BundleValidator.acquire-and-sweep` owns acquire+teardown **only** for the standalone `validate --all` sweep. A **public inner sweep** classifies pipes against a caller's **already-open** library and **never tears down**. `validate_bundle()` today tears down **only on failure** — on success it deliberately leaves the library loaded+current, and these callers depend on that: `builder/operations/inputs_ops.py:47`, `output_ops.py:32`, `cli/commands/build/runner/_runner_core.py:71`, `build/inputs/_inputs_core.py:52`, `build/output/_output_core.py:53`, `validate_ops.py:181` (`validate_pipe_in_bundle`), plus pipelex-api. All of these use the **inner sweep** and keep the loaded-on-success contract. *(Found by the outside-voice pass — was a blind spot in the original plan.)*
- **D7 — preserve error precedence.** In `BundleValidator`, run the **`validate_with_libraries` pass first, then the aggregated signature pre-pass, then the sweep** (swap the plan's §4.2 step 3/4). Today `validate --all` runs `validate_with_libraries()` before the signature pre-pass (`_validate_core.py:49` → `dry_run.py:139`); do not flip it (protects the freshly-hardened signature e2e in `36914511`/`76b96992`).

**Fold-in corrections (no decision needed — just do them):**

- **Phase 0 rewire MISS:** `tests/integration/pipelex/temporal/library_crate/conftest.py:11` also imports `convert_to_working_memory_format` — add it to the rewire list (a missed rewire there fails the whole Temporal integration suite at collection). The Phase-3 list also names `test_pipe_sequence_dry_run.py`, which imports nothing from `dry_run` (uses `@pytest.mark.dry_runnable`); the real importer is `test_pipe_sequence_list_output_bug.py`. Trust a fresh grep, not the list.
- **Phase 1 traps (pin in the D4 char-test):** preserve the **truthiness** check at `pipeline_run_setup.py:246` (empty `PipelineInputs` behaves like no inputs → `working_memory=None` unless mock; do **not** switch to `inputs is not None`); decide consciously about the `search_domain_codes` **list mutation** at `:217` (a "pure" builder will be tempted to copy it — that's a behavior change, pin or intend it); keep **bare `pipe.code`** for graph/trace naming at `:215/236/301` (do not switch to `pipe_ref` while namespacing validation data).
- **Phase 2 registry lifecycle:** the one-per-sweep report registry uses the **constant** `SpecialPipelineId.DRY_RUN_UNTITLED` (`dry_run.py:75`), so a second sweep hits "registry already exists" unless you `close_registry()` in `finally` (`reporting_manager.py:217`). The synthetic dry LLM report genuinely needs the registry (`content_generator_dry.py:76`), so it can't be skipped.
- **Phase 3 `allowed_to_fail` — collapse to ONE aggregate match (not two) + a model field:** today the match exists at **both** `dry_run.py:89` (per-pipe — which *also* does an immediate `raise` on the first non-allowed failure, `:92-94`) and `:186` (aggregate). In `BundleValidator` use a **single** match site at the aggregate step (per D-plan §4.2 step 6): the per-pipe step classifies SUCCESS/FAILURE/SKIPPED **only** (no `allowed_to_fail` check, no immediate raise); the aggregate step matches `allowed_to_fail` once on `pipe.pipe_ref`, builds the full unexpected-failures set, and raises **one** error listing all of them. **Drop the redundant per-pipe match and the early-abort** — do not port the first-failure raise. `DryRunOutput` carries only bare `pipe_code` — **add a `pipe_ref` field** (or namespaced matching silently regresses to bare-code). **New test:** a sweep with ≥2 non-allowed failures reports **both** (collect-all, not first-failure-abort).
- **Phase 3 flag-and-fix (pre-existing bug):** `cli/agent_cli/commands/validate/_validate_core.py:91` discards the dry-run result and reports every pipe as `"SUCCESS"`. When `BundleValidator` returns explicit `SUCCESS/FAILURE/SKIPPED`, make this caller consume it (otherwise allowed-failures/skips vanish from agent output).

## How to use this doc

- Work **top to bottom**. Tick `- [ ]` → `- [x]` as each item lands. Keep the **Status at a glance** table in sync.
- **⛔ CHECKPOINT = mandatory hard stop.** Do **not** cross a ⛔ in the same session. At each one: run the verification block, fill the **Handoff** block in place, commit, then end the session. The next session cold-starts from there.
- **Line numbers in D-plan are indicative** (pinned to the branch state when written). **Verify by symbol** (grep for the function/class), never trust a line number. Do not edit by line number.
- **TDD (red → green → refactor).** Each phase lists *Tests first*, then *Implement*. Write the failing test, make it pass, then tidy. (Project preference.)
- **Verification commands** (from `CLAUDE.md` — never `make test`):
    - `make agent-check` — lint + types (ruff, pyright, mypy, plxt). Must be clean.
    - `make agent-test` — full suite, silent on success. Must be green at every ⛔.
- **No backward-compat** (project rule): change things outright; note breaking changes. No shims — the pipelex-api consumer is migrated in lock-step (D2, Phase 3b).

## Cold-start protocol (a fresh session starts here)

1. Read this section + the **Eng-review decisions** block + **Status at a glance** + the **Handoff** block of the last completed ⛔ checkpoint.
2. Skim [`D-plan.md`](wip/dry-run-refactor-draft/D-plan.md) §1–§4 for the model (two operations; run-mode ⟂ backend) and §4.1–§4.5 for the consolidation (decisions D1–D3). The eng-review decisions above govern where they conflict.
3. Resume at the **"Next entry point"** named in that Handoff block. Re-verify referenced symbols still exist before editing.

## Handoff block template (fill at every ⛔)

> **Completed:** which boxes/phases landed this session.
> **Decisions locked:** any in-phase decision resolved, + the choice.
> **Final names/signatures:** the concrete signatures or names to record (e.g. `acquire_library(...)`, `prepare_pipe_job(...)`, the `BundleValidator` acquire-and-sweep + public inner-sweep signatures, `DryRunOutput.pipe_ref`).
> **Files touched (new/changed/deleted):** paths.
> **Deviations from plan + why.**
> **Surprises / new risks** discovered.
> **Test state:** last green commit SHA; anything skipped/xfail and why.
> **Next entry point:** exact phase + first action for the next session.

---

## Status at a glance

| Phase | Title | Status | Commit |
|---|---|---|---|
| 0 | Unblock the leaf (relocate helpers) | ☑ done | `f04c4c7a` |
| 1 | Extract `acquire_library` / `prepare_pipe_job` seams | ☑ done | `f04c4c7a` |
| | **⛔ CHECKPOINT A** | | |
| 2 | Build `BundleValidator` (two-lifecycle, union catch) | ☐ | |
| | **⛔ CHECKPOINT A2 — built + tested, zero callers** | | |
| 3a | Migrate in-repo callers + tests + config | ☐ | |
| 3b | Migrate `pipelex-api` runner.py (cross-repo PR) | ☐ | |
| | **⛔ CHECKPOINT B** | | |
| 4 | Delete dead code | ☐ | |
| | **⛔ CHECKPOINT C — consolidation done (shippable)** | | |

Status legend: ☐ not started · ◐ in progress · ☑ done.

---

## Phase 0 — Unblock the leaf (§4.7)

- [x] Confirm importers of the two helpers by grep: `convert_to_working_memory_format`, `convert_stuff_spec_to_typed_named`.
- [x] Relocate both into `WorkingMemoryFactory` (`pipelex/core/memory/working_memory_factory.py`) as **classmethods** (`WorkingMemoryFactory.convert_to_working_memory_format`, `WorkingMemoryFactory.convert_stuff_spec_to_typed_named`). Chose the factory (not a `mock_inputs.py`) — verified empirically that importing `pipelex.hub` does **not** pull in `working_memory_factory`, so the new top-level `from pipelex.hub import get_class_registry` can't cycle.
- [x] Rewire importers — grep-confirmed live set: `pipe_signature/pipe_signature.py`, `pipeline/pipeline_run_setup.py`, **`pipe_run/dry_run.py`** (its own internal call at `:71`), **`pipe_run/dry_run_with_graph.py`** (also an importer — omitted from the original list), `tests/integration/pipelex/temporal/library_crate/conftest.py`, `tests/integration/pipelex/pipe_signature/test_pipe_signature.py`.
- [x] `make agent-check` clean. Targeted suites green (pipe_run, pipe_signature, pipeline, core — 1266 passed); temporal-crate + signature-e2e collection clean. Full `make agent-test` runs at ⛔ CHECKPOINT A (Phase 0 + Phase 1 land in one commit). No behavior change.

> **(soft stop — after Phase 0).** Phase 0 is mechanical and ends green; it's a safe commit point. Phase 1 now front-loads the characterization test (D4), so if context is tight, commit Phase 0 and resume at Phase 1 next session. No Handoff block required (no decisions taken) — just note the green SHA in the commit.

## Phase 1 — Extract the execution seams (§4.1 / D2)

- [x] *Tests first (D4):* characterization test landed — `tests/integration/pipelex/pipeline/test_pipeline_run_setup_characterization.py` (4 tests, green on today's code). Pins: success path (DRY+mock job correctness, **library left OPEN+current on success** — caller owns teardown, one `PIPELINE_EXECUTE`, pipeline registered); `search_domain_codes` **in-place mutation** of a non-empty caller list (pinned to preserve); empty `PipelineInputs` ≡ no inputs (`if inputs:` truthiness — note: not robustly distinguishable at the job level because `make_pipe_job` does `working_memory or make_empty()`, so I also keep `if inputs:` verbatim in the extraction). **⚠️ FINDING (D4 assumption was wrong):** the load-failure path **currently LEAKS** the library — a pre-`try` failure (here `pipe_code` absent → `PipeNotFoundError` at `get_required_pipe`) does **not** tear down, because open/load runs *outside* `pipeline_run_setup`'s `try` and `execute_pipeline`'s `finally` only fires when setup returned a `library_id`. D4 assumed "teardown still runs, no leak" — false. The char-test pins the **current leak** (green now); the `acquire_library` extraction **fixes** it (moves load under try/teardown, matching the already-hardened `validate_bundle`), and I flip that test's assertions to teardown==+1 + current-library-cleared as a **noted intentional bug-fix**. Bare `pipe.code` naming (`:215`) pinned indirectly via `pipe.code == "echo_topic"`.
- [x] *Tests first:* `tests/integration/pipelex/pipeline/test_execution_seams.py` (`TestExecutionSeams`) — `acquire_library` loads a bundle + returns the domain-qualified main_pipe + leaves the library open/current; `acquire_library` tears down + restores outer current-library on a load failure; `prepare_pipe_job` builds an equivalent `PipeJob` (pipe, DRY run_mode, pipeline_run_id, library_crate, mock input) against a pre-opened library.
- [x] Extracted `acquire_library(...)` + `prepare_pipe_job(...)` into a **new module** `pipelex/pipeline/execution_seams.py` (NOT inside `pipeline_run_setup.py`, so the Phase-2 `BundleValidator` can compose the seams without importing the runner's wrapper).
- [x] **Signature deviation from the §4.1 sketch (settled — see Handoff):** `acquire_library` is **load-only** and returns `tuple[str, str | None]` = `(library_id, qualified_main_pipe)`; it does **not** resolve the pipe. `prepare_pipe_job` takes a resolved **`pipe: PipeAbstract`** (not `pipe_code`). Pipe resolution stays in the wrapper because graph-tracer open needs the resolved pipe and must precede `prepare_pipe_job`.
- [x] Recomposed `pipeline_run_setup` as the thin wrapper: `add_new_pipeline` → `acquire_library` → (resolve pipe → search_domain mutation → tracer → run-mode → registry/event-log → otel) inside one `try/finally` → `prepare_pipe_job` → `PIPELINE_EXECUTE` → return. Runner public API untouched. The post-acquire `except Exception` became a `try/finally + success` block (covers `BaseException`/`CancelledError`, matching `validate_bundle`).
- [x] LIVE + self-contained DRY paths unchanged: D4 char-test (3 success pins green; load-failure assertion flipped to teardown==+1 as the intended fix) + the seams tests + broad targeted run (pipeline + pipes + pipe_signature + pipe_run + graph e2e + signature e2e = 407 passed).
- [x] `make agent-check` clean · `make agent-test` **fully green** ("All tests passed").

> ### ⛔ CHECKPOINT A — after Phase 1 — **MANDATORY STOP**
>
> Seams exist; self-contained path recomposed with no behavior change (pinned by the D4 char-test); signature runtime no longer depends on `dry_run.py`. Nothing consumes the seams for batch use yet — clean boundary.
>
> **Verify:** `make agent-check` clean · `make agent-test` green (incl. the D4 char-test) · commit.
>
> **Handoff:**
> - **Completed:** Phase 0 (helpers relocated to `WorkingMemoryFactory`) + Phase 1 (seams extracted, `pipeline_run_setup` recomposed). Both land in the Checkpoint-A commit.
> - **Decisions locked:**
>     - Helpers relocated as **classmethods on `WorkingMemoryFactory`** (`convert_to_working_memory_format`, `convert_stuff_spec_to_typed_named`) — verified `hub` doesn't import `working_memory_factory`, so the new top-level `from pipelex.hub import get_class_registry` can't cycle.
>     - Seams live in a **new module `pipelex/pipeline/execution_seams.py`** (so Phase-2 `BundleValidator` composes them without importing the runner wrapper).
>     - `acquire_library` is **load-only** (does NOT resolve the pipe) and returns the domain-qualified `main_pipe`; the wrapper resolves the pipe. `prepare_pipe_job` takes a resolved **`pipe` object**, not a `pipe_code`.
>     - `acquire_library` mirrors `validate_bundle`'s hardened idiom: open → capture `prev_library_id` → `try: set_current + load` → `finally: if not success → restore prev current-library (or clear), then teardown`. (Restore-prev, not clear — required for the Phase-3 `validate_bundle` callers' contract.)
> - **Final names/signatures:**
>     - `acquire_library(library_id: str, *, library_dirs: list[str] | None = None, mthds_contents: list[str] | None = None, bundle_uris: list[str] | None = None) -> tuple[str, str | None]` → `(library_id, qualified_main_pipe)`. Owns load-failure teardown. Sync.
>     - `async prepare_pipe_job(pipe: PipeAbstract, *, library_id: str, execution_config: PipelineExecutionConfig, pipe_run_mode: PipeRunMode, pipeline_run_id: str, user_id: str, inputs: PipelineInputs | WorkingMemory | None = None, search_domain_codes: list[str] | None = None, graph_context: GraphContext | None = None, otel_context: OtelContext | None = None, output_name: str | None = None, output_multiplicity: VariableMultiplicity | None = None, dynamic_output_concept_ref: str | None = None, request_id: str | None = None) -> PipeJob`. **Pure** (no registration/telemetry/graph-open/library-mutation).
>     - `pipeline_run_setup` public signature **unchanged** (`-> tuple[PipeJob, str, str]`); internal recomposition only. Its post-acquire `except Exception` is now a `try/finally + success` block (covers `BaseException`/`CancelledError`).
> - **Files touched:**
>     - New: `pipelex/pipeline/execution_seams.py`; tests `tests/integration/pipelex/pipeline/test_pipeline_run_setup_characterization.py`, `.../test_execution_seams.py`.
>     - Changed (Phase 1): `pipelex/pipeline/pipeline_run_setup.py`.
>     - Changed (Phase 0): `pipelex/core/memory/working_memory_factory.py` (+2 classmethods), `pipelex/pipe_run/dry_run.py`, `pipelex/pipe_run/dry_run_with_graph.py`, `pipelex/pipe_signature/pipe_signature.py`, `tests/integration/pipelex/temporal/library_crate/conftest.py`, `tests/integration/pipelex/pipe_signature/test_pipe_signature.py`.
> - **Deviations + why:** (1) seam boundary differs from the §4.1 sketch — `acquire_library` load-only + returns `main_pipe`; `prepare_pipe_job` takes a resolved `pipe`; pipe resolution stays in the wrapper because graph-tracer open needs the pipe and must precede `prepare_pipe_job`. (2) Seams in their own module (Phase-2 reuse). (3) **Intentional behavior change (bug fix, NOT a regression):** load/resolve failures now tear down the library — `acquire_library` owns load-time teardown, the wrapper's `try/finally` owns the post-acquire window. Previously these **pre-`try` failures leaked** the library (D4's "no leak today" assumption was wrong — verified). The flipped char-test `test_load_failure_tears_down_library` pins the fix.
> - **Surprises / new risks:** (a) the load-failure leak finding above. (b) **Asymmetry now RESOLVED (seam-extraction review fixes, Fix 3):** `acquire_library` *restores* the outer current-library on failure (validate_bundle contract); the wrapper's post-acquire `finally` formerly *cleared* current to `None`. It now captures `prev_library_id` before acquire and restores-current-first-then-tears-down the library, so both paths follow the same convention. (c) Within the wrapper, working-memory build now happens after the registry/otel side-effects (no dependency between them — verified green); the truthiness `if inputs:` is kept verbatim in `prepare_pipe_job` (now pinned discriminatingly by `test_prepare_pipe_job_skips_normalize_for_empty_inputs`).
> - **Test state:** `make agent-check` clean · `make agent-test` **fully green** ("All tests passed"). Green SHA: **`f04c4c7a`** (Checkpoint-A commit on `feature/Validate-with-signatures-4-fix-dry-run`). No skips/xfails introduced by this work.
> - **Seam-extraction review fixes: APPLIED + verified** — [`seam-extraction-review-fixes.md`](wip/dry-run-refactor-draft/seam-extraction-review-fixes.md) (see its Status block). The `open_library`-id teardown-all landmine (Fix 1), the report-registry leak on the wrapper's failure path (Fix 2), the asymmetric current-library-restore (Fix 3), and the misleading truthiness test (Fix 4) are all fixed, each with TDD tests (verified RED→GREEN). `make agent-check` clean; targeted suite + full `make agent-test` green. Flagged-not-fixed: a **pre-existing** success-path registry leak (production never closes the registry even on success — `runner.py:196-211`); separate change, out of this brief's scope.
> - **Next entry point:** **Phase 2 — Build `BundleValidator`** (`pipelex/pipeline/bundle_validator.py`), composing `acquire_library` + `prepare_pipe_job` against a direct in-process `PipeRun`. Re-verify the seam symbols still exist before editing.

## Phase 2 — Build `BundleValidator` (§4.2, D1/D3)

- [ ] *Tests first:* port `tests/unit/pipelex/pipe_run/test_dry_run.py` coverage onto the service surface; add a cross-package partial-validation test (the `PipeNotFoundError → SKIPPED` recursive `__cause__` walk); add a third-party-exception classify test (a pipe failing with pydantic `ValidationError` / polyfactory `FactoryException` → FAILURE, not a sweep abort — D3); add the **widening test** (a non-dependency `PipelexError` raised mid-run → per-pipe FAILURE, *not* a sweep abort — D3); add the **collect-all test** (a sweep with ≥2 non-allowed failures reports both, not first-failure-abort); add a two-consecutive-sweeps test (registry `close_registry()` in `finally`).
- [ ] Implement `pipelex/pipeline/bundle_validator.py` with **two lifecycles (D6)**: (a) `acquire-and-sweep` owns `acquire_library` once + `try/finally` teardown for the standalone `validate --all` case; (b) a **public inner sweep** that classifies pipes against a caller's already-open library and **never tears down** (used by `validate_bundle`, the build CLIs, pipelex-api). Composition: `validate_with_libraries` pass → aggregated signature pre-pass → per-pipe `prepare_pipe_job` + direct in-process `PipeRun` (locally-constructed `PipeRun(PipeRouter(observer=ObserverNoOp()))`, **not** `get_pipe_run()`) → `SUCCESS/FAILURE/SKIPPED` classify → single `PIPE_DRY_RUN` event.
- [ ] **Order (D7):** `validate_with_libraries` pass **before** the signature pre-pass (preserve today's error precedence).
- [ ] **Catch (D3 — intentional widening to base `PipelexError`):** `except (PipelexError, ValidationError, FactoryException)` wrapping both `prepare_pipe_job` and the run (subsumes today's narrow `PipeStackOverflowError`/`PipeComposeError` tuple; needed so router-wrapped deps reach the cause-walk); keep the `format_pydantic_validation_error` branch; `SKIPPED` = recursive `_root_cause_is(exc, PipeNotFoundError)` walk that tests `exc` **itself** then its `__cause__`/`__context__` chain (§4.2 step 5 / §8). Per-pipe step classifies only — **no `allowed_to_fail`, no immediate raise** (those live at the aggregate step).
- [ ] Relocate `DryRunStatus` / `DryRunOutput` into the `bundle_validator` module; **add `DryRunOutput.pipe_ref`** (namespaced matching, C-7).
- [ ] Report registry: open **one** per sweep, `close_registry()` in `finally` (constant `DRY_RUN_UNTITLED` id collides on the 2nd sweep otherwise). Assert exactly one `PIPE_DRY_RUN`, no stray `PIPELINE_EXECUTE`/`PIPELINE_COMPLETE`.
- [ ] Built behind no callers yet, against the still-present `dry_run.py`. `make agent-check` + `make agent-test` green.

> ### ⛔ CHECKPOINT A2 — after Phase 2 — **MANDATORY STOP**
>
> The cleanest handoff boundary in the consolidation: `BundleValidator` is **built and fully tested, with zero callers** depending on it (the old `dry_run.py` is still present and still wired to everything). Nothing can break from stopping here. Upgraded from a soft stop (eng-review D8) because Phase 2 and Phase 3 are each large, distinct concerns and this is where context most easily bleeds into a too-big Phase 3.
>
> **Verify:** `make agent-check` clean · `make agent-test` green (ported `test_dry_run.py` + cross-package SKIPPED test + third-party-classify test + exactly-one-`PIPE_DRY_RUN` test + two-consecutive-sweeps test) · commit.
>
> **Handoff (fill in):**
> - Completed:
> - Decisions locked: (confirm D3 union catch, D6 two-lifecycle, D7 order, registry close-in-finally, `pipe_ref`)
> - Final names/signatures: `BundleValidator` public API = **acquire-and-sweep** signature = … ; **public inner sweep** (borrows open library, no teardown) signature = … ; `DryRunStatus`/`DryRunOutput` new home = … ; `DryRunOutput.pipe_ref` field shape = … ; per-pipe catch surface confirmed = `(PipelexError, ValidationError, FactoryException)`.
> - Files touched:
> - Deviations + why:
> - Surprises / new risks:
> - Test state (green SHA):
> - Next entry point: **Phase 3a — Migrate in-repo callers** (then 3b — pipelex-api).

## Phase 3a — Migrate the in-repo callers (D3 / D6)

- [ ] Point at the **acquire-and-sweep** entry: `validate_bundle` / `validate_bundles_from_directory`, both `cli/.../validate/_validate_core.py`, `builder/operations/validate_ops.py`, `builder/operations/runner_code_ops.py`.
- [ ] Point the **caller-owned-library** flows at the **public inner sweep** (no teardown — D6), preserving the loaded-on-success contract: `builder/operations/inputs_ops.py`, `output_ops.py`, `cli/commands/build/{runner,inputs,output}/_*_core.py`, `validate_pipe_in_bundle` (`validate_ops.py:181`). Add caller tests asserting `get_required_pipe()` still works after validation.
- [ ] Fix the pre-existing agent-CLI bug: `cli/agent_cli/commands/validate/_validate_core.py:91` discards results and reports all-`SUCCESS` — consume the `SUCCESS/FAILURE/SKIPPED` map (C-8).
- [ ] Rewire tests importing soon-to-be-deleted symbols (`dry_run_pipe`/`dry_run_pipes`/`DryRunStatus`/`convert_to_working_memory_format`): the `pipe_signature` integration tests, the `pipe_sequence` dry-run tests, the signature-validation e2e (grep to confirm the current set — don't trust a stale list).
- [ ] Migrate `pipelex.toml` `allowed_to_fail_pipes` to namespaced refs: `infinite_loop_1` → `failing_pipelines.infinite_loop_1`; **delete the obsolete `pipe_builder` entry**. Match on `pipe.pipe_ref` at the **single aggregate site** (not the two former sites — see the Phase-3 `allowed_to_fail` fold-in: per-pipe classifies only, aggregate matches once and collects all). Add a pos/neg matching test + the collect-all test (≥2 non-allowed failures both reported).
- [ ] Verify single-pipe `validate <pipe>` / `--pipe` slice + friendly `SignaturesNotAllowedError` rendering still fire.
- [ ] `make agent-check` + `make agent-test` green.

> **(soft seam — between 3a and 3b).** 3a is self-contained and green within `pipelex` (a valid in-repo commit). 3b is a **separate PR in the `pipelex-api` repo** with its own verification. Natural place to break sessions: finish/commit 3a here; do 3b (cross-repo) next, coordinated with the `pipelex` pin bump. Note the green `pipelex` SHA before crossing.

## Phase 3b — Migrate `pipelex-api` (cross-repo, D2)

- [ ] In `../pipelex-api`: replace the module-level `from pipelex.pipe_run.dry_run import dry_run_pipes` + per-pipe call (`api/routes/pipelex/build/runner.py:6,64`) with the **public inner sweep** against runner.py's already-open library (it keeps the library open for `generate_runner_code` afterward — do **not** adopt acquire-and-teardown here).
- [ ] Coordinate the release: this PR + the `pipelex` pin bump land together (no compat shim — D2). `pipelex-api` tests green.

> ### ⛔ CHECKPOINT B — after Phase 3a + 3b — **MANDATORY STOP**
>
> All validation traffic now goes `BundleValidator` → shared seam; `dry_run.py` execution functions unreferenced *inside this repo* **and** in `pipelex-api` (migrated in Phase 3b, D2 — no shim). Nothing references the soon-to-be-deleted symbols anymore.
>
> **Verify:** signature e2e + `pipe_signature` integration suites green · full `make agent-test` green · commit.
>
> **Handoff (fill in):** (use template) — **Next entry point: Phase 4 — Delete dead code.**

## Phase 4 — Delete dead code (§5)

- [ ] Delete `pipe_run/dry_pipe_router.py`, `pipe_run/dry_run_with_graph.py`, and the now-unreferenced `pipe_run/dry_run.py` (grep to confirm zero in-repo importers first).
- [ ] Settle `dry_run_pipeline.py` (keep thin, or inline into `graph/graph_rendering.py`).
- [ ] `make cleanderived` if collection gets confused; `make agent-check` + `make agent-test` green.

> ### ⛔ CHECKPOINT C — after Phase 4 — **Consolidation complete (shippable)** — **MANDATORY STOP**
>
> The branch's goal is met and pipelex-api is already migrated (Phase 3b), so shipping is clean — no shim, no ordering caveat. DRY still mocks at the pipe level (pre-D4) — fine; the leaf-run-mode follow-up changes *where* the mock is minted, not the validation outcomes.
>
> **Verify:** full `make agent-test` green · `make agent-check` clean · commit (open the PR for the consolidation here).
>
> **Handoff (fill in):** (use template) — **Next:** the deferred backend follow-ups, on their own branches — start with [`followup-leaf-run-mode-mock.md`](wip/dry-run-refactor-draft/followup-leaf-run-mode-mock.md) (resolve its Pre-flight items first).

---

## GSTACK REVIEW REPORT

Eng review of this plan (`/plan-eng-review`), 2026-06-01. **Pass 1** (commit `4f90703f`): scope reduced to the in-process consolidation (D-plan Part A) + outside-voice fold-ins. **Pass 2** (commit `49d9a1da`, code-grounded verification): verified ~20 of the plan's `file:line`/symbol claims against the actual tree — all confirmed but one — and folded two corrections into D3 and the Phase-3 `allowed_to_fail` fold-in.

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 2 | CLEAR (PLAN) | P1: scope→consolidation; D1–D8 locked; outside-voice fold-ins. P2: ~20 claims verified (19 confirmed, 1 drift), 2 findings folded in, 0 critical gaps |
| Outside Voice | `codex` | Independent 2nd opinion | 1 | issues_found | caught the teardown-on-success blind spot + fold-in corrections |

**PASS-2 VERIFICATION (code-grounded).** Confirmed against the current tree: the pipelex-api module-scope `dry_run_pipes` import (D2 boot-break), the two `allowed_to_fail` sites + the `DRY_RUN_UNTITLED` registry-id collision, `DryRunOutput` carrying only bare `pipe_code`, the temporal conftest import, the six D6 inner-sweep callers + their post-validate `get_required_pipe()` use, `validate_bundle`'s teardown-on-failure-only, the agent-CLI all-SUCCESS bug, the delete/relocate importer sets, and the Phase-3 test-rewire correction. **One drift found**, plus one tracker/D-plan inconsistency — both folded in:

- **D3 catch tuple (drift).** D3 stated today's catch is `(PipelexError, ValidationError, FactoryException)`; the actual code (`dry_run.py:84`) is the narrow `(PipeStackOverflowError, ValidationError, PipeComposeError, FactoryException)` + a separate `except PipeNotFoundError` for SKIPPED. D3's proposed base-`PipelexError` catch is correct and *necessary* (post-refactor `PipeRun.run` re-raises and the router wraps `PipeNotFoundError` in a `PipelexError`, so only a base catch reaches the SKIPPED cause-walk) — but it is a real *widening* of sweep tolerance. **Resolved (option A):** keep the base catch, corrected D3's description to state the real current surface and frame the widening as intentional, added a Phase-2 test (a non-dependency `PipelexError` raised mid-run → per-pipe FAILURE, not a sweep abort).
- **`allowed_to_fail` one-vs-two sites (inconsistency).** The Phase-3 fold-in said "migrate both sites"; D-plan §4.2 step 6 wants a single aggregated raise, and today's per-pipe site also early-aborts on the first non-allowed failure (`:92-94`). **Resolved (option A):** single aggregate match on `pipe.pipe_ref`, per-pipe step classifies only (no early-abort), added a collect-all test (≥2 non-allowed failures both reported).

**OUTSIDE VOICE (codex, pass 1):** surfaced the `validate_bundle()` loaded-on-success blind spot (~6 callers depend on it → D6 two-lifecycle) + an error-precedence flip (→ D7) and concrete fold-ins (registry close-in-finally, `DryRunOutput.pipe_ref`, Phase-1 truthiness/mutation/bare-code traps, the agent-CLI bug).

**CROSS-MODEL:** two pass-1 tensions (teardown model, step order); both resolved toward preserving current behavior (D6, D7). No residual disagreement.

**Decisions locked:** D1 scope→consolidation alone · D2 migrate pipelex-api now (no shim) + public inner sweep · D3 union catch — **base `PipelexError` (intentional widening)** + `(ValidationError, FactoryException)` · D4 characterization test before Phase 1 · D6 two explicit teardown lifecycles · D7 preserve `validate_with_libraries`→signature order · D8 checkpoint split (A2, Phase-0/3 seams) · **pass-2: single aggregate `allowed_to_fail` match, collect-all (no per-pipe early-abort).**

**UNRESOLVED:** none — all decisions answered.

**VERDICT:** ENG CLEARED (scope = in-process consolidation) — verified against the code, ready to implement starting at Phase 0. The two backend follow-ups (leaf run-mode mock, Temporal validation activity) are deferred to their own branches and tracked in `wip/dry-run-refactor-draft/`.
