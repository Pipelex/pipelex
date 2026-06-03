# BundleValidator review findings (post-Checkpoint A2)

Findings from the `xhigh` multi-agent code review (9 finder angles → verify → gap-sweep) of the **Phase 2 `BundleValidator`** work — commits `23f936cd` (service) + `68568de5` (SHA record) on branch `feature/Validate-with-signatures-4-fix-dry-run`. Scope diff: `git diff 5c52d4c4...HEAD` (== `@{upstream}...HEAD` at review time).

**Nothing here is broken on this branch today** — `BundleValidator` has **zero callers** (the old `pipe_run/dry_run.py` is still wired to everything). Every correctness item is **latent**: it manifests only when Phase 3 wires callers (or Part C adds concurrency). Two items (**#1, #2**) are baked into the new code and *will* bite at wiring time — treat them as Phase-3a prerequisites.

## Cold-start protocol (verifying these in a fresh session)

1. Read this file + the **Priority** table below + [`D-plan.md`](D-plan.md) decisions **D3 / D6 / D7** (§4.2) and the [`/TODOS.md`](../../TODOS.md) Phase-3a checklist — several findings are the *same* concerns those decisions/TODOs already track, now pinned with line evidence.
2. **Line numbers are indicative** (pinned to `23f936cd`). **Verify by symbol** — grep the function/class, never trust the line. The "Anchor" field on each finding names the symbol.
3. To re-confirm a finding, re-read the named symbols and (where noted) compare against the OLD behavior in `pipelex/pipe_run/dry_run.py` (`dry_run_pipe` / `dry_run_pipes`) and `pipelex/cli/commands/validate/_validate_core.py` (`do_validate_all_libraries_and_dry_run`).
4. The **Refuted** section lists candidates that were chased and disproven — do **not** re-open them without new evidence.

## Priority

| # | Severity | Verdict | Kind | Must-handle-by | One-line |
|---|---|---|---|---|---|
| 1 | High | CONFIRMED | correctness regression | **Phase 3a** | step-1 `validate_with_libraries` aborts sweep instead of SKIPPED for controllers w/ unloaded sub-pipes |
| 2 | High | CONFIRMED | correctness (config lockstep) | **Phase 3a** | `allowed_to_fail` matches namespaced `pipe_ref` but `pipelex.toml` still has bare codes |
| 3 | Medium | PLAUSIBLE | correctness (concurrency) | Part C | report registry keyed by global constant id → concurrent sweeps collide; undefaulted `close_registry` pop masks exceptions |
| 4 | Med-low | PLAUSIBLE | efficiency + latent correctness | Phase 3 / Part B | per-pipe `assemble_graph_on_output` (trace I/O) via `PipeRun.run`, keyed by constant id |
| 5 | Low | PLAUSIBLE | correctness (edge) | when used | `acquire_and_validate` self-teardown if `prev_library_id == acquired_id` |
| 6 | Medium | — | cleanup (altitude) | anytime | restore-then-teardown `finally` duplicated ~6 sites → shared context manager |
| 7 | Medium | — | test gap | Phase 3 | `acquire_and_validate` has zero tests |
| 8 | Low | — | cleanup (transitional) | Phase 4 | `_signature_pre_pass` + classify strings duplicate `dry_run.py` |
| 9 | Low | — | simplification | anytime | `_aggregate` builds `successful/skipped` lists used only in one log line |
| 10 | Low | — | altitude (transitional) | Phase 4 | re-export inverts layering (`pipe_run` ← `pipeline`) |
| 11 | Low | — | altitude (forward) | Part C | `__init__` hardcodes `PipeRun`, no injection seam for `scoped_content_generator` |
| 12 | Low-med | — | test quality | Phase 3 | integration tests cover only SUCCESS; weak no-stray-events assertion |

---

## Correctness

### 1. ✅ `validate_with_libraries` step-1 pass aborts the sweep instead of SKIPPED (controllers with unloaded/cross-package sub-pipes)

- **Anchor:** `BundleValidator.validate_pipes` step 1 — `for pipe in pipes: pipe.validate_with_libraries()` (`pipelex/pipeline/bundle_validator.py` ~L178), which runs **outside any try/except** (the sweep's `try` only opens at `open_registry`, ~L197).
- **Mechanism (verified):** `validate_with_libraries` (`pipelex/core/pipes/pipe_abstract.py` ~L188, `@final`) → `generic_validate_inputs_with_library` calls `self.required_variables()` (~L204) then `self.needed_inputs()` (~L219). These controller overrides call `get_required_pipe` **unguarded**, so an unloaded/cross-package sub-pipe raises `PipeNotFoundError` (which **is** a `PipelexError` — `pipelex/libraries/pipe/exceptions.py`: `PipeNotFoundError(PipeLibraryError(PipelexError))`):
    - `PipeBatch.required_variables` → `get_required_pipe(branch_pipe_code)` (`pipe_controllers/batch/pipe_batch.py` ~L55)
    - `PipeParallel.needed_inputs` → `get_required_pipe(sub_pipe.pipe_code)` (`pipe_controllers/parallel/pipe_parallel.py` ~L79)
    - `PipeCondition.required_variables` → `get_required_pipe(...)` (`pipe_controllers/condition/pipe_condition.py` ~L58)
    - `PipeSequence` is the **guarded counter-case** (`pipe_sequence.py` `needed_inputs`/`validate_output_with_library` skip cross-package via `get_optional_pipe`) — it does **not** trip.
- **Why it's a regression:** the OLD `dry_run_pipe` called `validate_with_libraries()` **inside** the `try` whose `except PipeNotFoundError → SKIPPED` arm (`pipe_run/dry_run.py` ~L45, ~L51) classified the pipe SKIPPED and let `dry_run_pipes` keep iterating. The new step-1 loop has no such guard.
- **Scope of the regression:** it affects the **D6 inner-sweep callers** (`validate_bundle`, `validate_pipe_in_bundle`, build CLIs) — they had **no** separate `validate_with_libraries` loop and relied on `dry_run_pipe`'s internal SKIPPED. It is **not** a regression for `validate --all`: `do_validate_all_libraries_and_dry_run` (`cli/commands/validate/_validate_core.py` ~L84) *already* has an unguarded `validate_with_libraries` loop today, so it already aborts.
- **Failure scenario:** Phase 3a points `validate_bundle` at `validate_pipes`; a partially-stubbed bundle whose `PipeParallel`/`PipeBatch`/`PipeCondition` references a cross-package (or otherwise unloaded) sub-pipe now aborts the entire sweep with an uncaught `PipeNotFoundError`, where the old `validate_bundle` SKIPPED it and passed.
- **Note (corroborating, from the SKIPPED-walk verifier):** even the cross-package `PipeParallel` case that D-plan intends to be SKIPPED at the *run* stage never reaches the run — it aborts in this step-1 pass first. So the cross-package tolerance for controllers does not actually take effect through this path.
- **Suggested fix:** in step 1, wrap each pipe's `validate_with_libraries()` and on `PipeNotFoundError` record it as SKIPPED + drop it from the pipes carried into the signature pre-pass and the sweep. This preserves D7 (wiring check before signature pre-pass) *and* restores the cross-package SKIPPED tolerance. Add a test: a controller pipe whose `validate_with_libraries` raises `PipeNotFoundError` → SKIPPED in the result map, sweep not aborted.

### 2. ✅ `allowed_to_fail` keys off namespaced `pipe_ref`, but `pipelex.toml` still holds bare codes (must migrate in lockstep)

- **Anchor:** `BundleValidator._aggregate` — `unexpected_failures = {... for pipe_ref in failed_pipes if pipe_ref not in allowed_to_fail_pipes}` (`bundle_validator.py` ~L295). The dict key is the namespaced `domain.pipe_code`.
- **Mechanism (verified):** `get_config().pipelex.dry_run_config.allowed_to_fail_pipes` in `pipelex/pipelex.toml` (~L374) still lists **bare** codes (`infinite_loop_1`, `pipe_builder`). `"failing_pipelines.infinite_loop_1" not in ["infinite_loop_1", "pipe_builder"]` is always `True`, so a pipe that should be tolerated lands in `unexpected_failures` → `DryRunError`. (The OLD `dry_run_pipes` matched `results[...].pipe_code` — bare — so it worked.)
- **Why latent / why it matters:** no caller in Phase 2 → no live mismatch. But the moment `BundleValidator` replaces `dry_run_pipes` **without** the config migration, every configured allowed-to-fail pipe regresses to a hard failure. This is the **explicit Phase-3a TODO** (`/TODOS.md`: migrate `infinite_loop_1` → `failing_pipelines.infinite_loop_1`, **delete the obsolete `pipe_builder` entry**, single aggregate match). Flagged here so it is not missed: **the toml migration and the wiring must land in the same change.**
- **Suggested fix:** do the toml migration in the Phase-3a wiring commit; add a pos/neg matching test (namespaced ref matches; bare code does not) + the collect-all test (≥2 non-allowed failures both reported).

### 3. ⚠️ Report registry keyed by the global constant `DRY_RUN_UNTITLED` → concurrent sweeps collide (Part C landmine)

- **Anchor:** `BundleValidator.validate_pipes` — `get_report_delegate().open_registry(pipeline_run_id=SpecialPipelineId.DRY_RUN_UNTITLED)` (~L197) / `close_registry(...)` in `finally` (~L202). Constant: `pipeline/pipeline_models.py` `SpecialPipelineId.DRY_RUN_UNTITLED = "dry_run_untitled"`.
- **Mechanism (CONFIRMED in code; trigger is the planned Part-C topology):**
    - `_usage_registries` is a **process-global dict** on the singleton `ReportingManager` (`reporting/reporting_manager.py` ~L61); `get_report_delegate()` returns that one process-global instance shared across all coroutines.
    - `open_registry` **raises** `ReportingManagerError("... already exists")` if the id is present (`reporting_manager.py` ~L217-221).
    - `close_registry` does an **undefaulted** `self._usage_registries.pop(pipeline_run_id)` (~L393-394) → `KeyError` if already popped (contrast `clear_event_log` ~L95 which uses `pop(..., None)`).
- **Failure scenario:** two sweeps share the process (two concurrent `act_validate_bundle` activities on one worker — the D5 design; or direct-mode API validating two bundles; or two `BundleValidator` instances under `asyncio.gather`). The 2nd `open_registry` raises "already exists"; or, interleaved closes — sweep A's `finally` pops the slot, sweep B's `finally` then raises `KeyError` that **masks B's in-flight exception**.
- **Why latent:** no in-process concurrent sweeping exists today (no `gather`/`TaskGroup` over `validate_pipes`/`acquire_and_validate`). The D-plan *already* solves the identical concurrency hazard for the content generator with `_content_generator_override: ContextVar` + `scoped_content_generator` (D5 / `followup-temporal-validation-activity.md` Phase C1) but leaves the registry on the constant id.
- **Suggested fix:** key the per-sweep registry on a unique id (e.g. `DRY_RUN_UNTITLED` + a per-`validate_pipes` token), mirroring the planned scoped content-generator remedy; and independently harden `close_registry` to `pop(pipeline_run_id, None)` so it can never mask an in-flight exception.

### 4. ⚠️ Per-pipe `assemble_graph_on_output` (trace I/O) added by routing through `PipeRun.run`

- **Anchor:** `_classify_pipe` runs `await self._pipe_run.run(pipe_job)` (`bundle_validator.py` ~L256). `PipeRun.run`'s `finally` (`pipe_run/pipe_run.py` ~L56-76) calls `assemble_graph_on_output(pipe_output, pipeline_run_id=DRY_RUN_UNTITLED, ...)` whenever `pipe_output is not None` (i.e. every SUCCESS pipe).
- **Mechanism:** `assemble_graph_on_output` (`pipe_run/graph_assembly.py`) is gated on `tracing_config.is_enabled` (**default `true`** — `pipelex/pipelex.toml` ~L351, ndjson backend), **not** on `execution_config.is_generate_graph` — so the `generate_graph=False` override (`bundle_validator.py` ~L192) does nothing here. It does `make_event_log(...)` + `read_events('.pipelex/traces/dry_run_untitled')` + `close()` per pipe. The OLD `dry_run_pipe` called `pipe.run_pipe(...)` **directly** (no `PipeRun.run` wrapper), so none of this ran.
- **Failure scenario:** (a) efficiency/fs — a large `validate --all` sweep does one event-log read cycle per successful pipe against `.pipelex/traces`, new I/O in a previously fs-silent operation; (b) latent correctness — because the id is the shared constant, stale events left under `.pipelex/traces/dry_run_untitled/` by any prior tracer-opening DRY run would be read and assembled onto unrelated pipes' `pipe_output.graph_spec` (assembly errors are swallowed as warnings → silent contamination). (b) is low-likelihood today: nothing currently opens a tracer under that id, and the sweep itself passes `graph_context=None` so emits no events.
- **Note:** Finder E independently judged the empty-events case a "cheap no-op"; the concern is the *unconditional* per-pipe call + the shared constant id, not a crash. Tie this to the same constant-id smell as #3 — a per-sweep id fixes both.
- **Suggested fix:** either a per-sweep unique `pipeline_run_id` (so reads are scoped + empty), or skip the `PipeRun.run` graph-assembly path for validation (the sweep never wants a graph). Lowest-risk: per-sweep id.

### 5. ⚠️ `acquire_and_validate` self-teardown when `prev_library_id == acquired_id`

- **Anchor:** `acquire_and_validate` `finally` (`bundle_validator.py` ~L141-148): `if prev_library_id is not None: set_current_library(prev_library_id) ... get_library_manager().teardown(acquired_id)`.
- **Mechanism:** if a caller passes an explicit `library_id` equal to the already-current library, then `prev_library_id == acquired_id`; the `finally` restores current to that id and then tears that same library down → current-library pointer dangles at a torn-down id.
- **Why low:** the default `validate --all` path uses `library_id=""` → `acquire_library` adopts a fresh uuid from `open_library`, so `prev` can never equal `acquired`. Only an explicit-matching-id caller triggers it.
- **Suggested fix:** guard (`if prev_library_id is not None and prev_library_id != acquired_id`) or a docstring caveat that `library_id` must not alias the caller's current library.

---

## Cleanup / altitude

### 6. restore-prev-current-then-teardown `finally` duplicated across ~6 sites

- **Anchor / sites:** `bundle_validator.acquire_and_validate` (~L141), `execution_seams.acquire_library` (~L122-130), `pipeline_run_setup` (~L283-287), and `validate_bundle.py` (the `finally` blocks of `validate_bundle`, `validate_bundles_from_directory`, `load_concepts_only`, `load_concepts_only_from_directory`). Each repeats the same "restore outer current FIRST (so the guarantee survives a teardown raise); route the None case through `teardown_current_library`; then `library_manager.teardown(...)`" logic + comment.
- **Cost:** a subtle, load-bearing invariant copied 6×; a fix to the ordering must touch all of them, and the next "simplification" of one site silently diverges the rest into the exact library-leak / current-clobber bug the comments exist to prevent.
- **Suggested fix:** extract a `with acquired_library(...)` context manager (or `restore_and_teardown_library(...)` helper) in `execution_seams.py` and call it from every site. (The seam-extraction review already noted this as deferred — see [`seam-extraction-review-fixes.md`](seam-extraction-review-fixes.md) "Not in scope"; it's now stronger with one more copy.)

### 7. `acquire_and_validate` has zero tests

- Only `validate_pipes` is exercised (unit + integration). `acquire_and_validate`'s current-restore `finally` (the exact bug class the sibling `TestValidateBundleRestoresOuterLibraryOnFailure` in `tests/integration/pipelex/pipeline/test_validate_bundle_library_lifecycle.py` pins for `validate_bundle`) and its `is_signature` strict-mode filter are unverified.
- **Suggested fix:** add an integration test (set an outer current-library, call `acquire_and_validate` with a small bundle, assert teardown + outer-current restored on both success and a raised-mid-sweep path) and a signature-filter test. Note: testing it against `library_dirs=None` sweeps the base/PIPELEXPATH libraries — pass `library_dirs=[]` or assert only on lifecycle, not the full pipe set.

### 8. `_signature_pre_pass` + classify/error strings duplicate `dry_run.py` (transitional)

- `_signature_pre_pass` (`bundle_validator.py` ~L208) is near-verbatim `dry_run_pipes`' pre-check (`dry_run.py` ~L111-135). The classify strings (~L263, ~L267, ~L269) mirror `dry_run.py` ~L53/65/68/70 (with `pipe.code`→`pipe.pipe_ref`), and the aggregate message (~L303) drifted from `dry_run.py` ~L190 (quoting/pluralization). Acceptable for the migration window — both die when `dry_run.py` is deleted in **Phase 4** — but track the drift so the still-live `validate --all` path and the new validator don't emit two different messages for the same bundle.

### 9. `_aggregate` builds `successful_pipes` / `skipped_pipes` only to `len()` them in one log line

- `bundle_validator.py` ~L281-291: three accumulator lists + an exhaustive `match`, but only `failed_pipes` feeds logic. Carried over from `dry_run.py`. Counts are derivable inline; the bucketing is dead state that forces touching this block on any new `DryRunStatus` member. Low.

### 10. Transitional re-export inverts layering (`pipe_run` ← `pipeline`)

- `pipe_run/dry_run.py` ~L22 imports `DryRunOutput`/`DryRunStatus` from `pipeline/bundle_validator.py` (the execution layer importing from the higher validation layer). Documented Phase-4-temporary, no cycle today — but if Phase 4 slips, the shim ossifies and two import paths for the same symbol proliferate. Track Phase-4 deletion.

### 11. `__init__` hardcodes `PipeRun(PipeRouter(ObserverNoOp()))` — no injection seam for Part C

- `bundle_validator.py` ~L103. Correct *layer* (deliberately not `get_pipe_run()` — that's the whole point), but the run stack is frozen at `__init__`. Part C's `scoped_content_generator` work (forcing the inline content generator inside a Temporal activity) will have to reopen `__init__` or wrap each `_classify_pipe`. Forward-looking; revisit when Part C lands.

### 12. Integration tests cover only the SUCCESS path; weak no-stray-events assertion

- All three integration tests drive one valid `PipeLLM` on the SUCCESS path. No integration coverage of real FAILURE/SKIPPED classification or the real `allowed_to_fail` config match (the C-7 fix is only exercised against a *mocked* config in the unit suite — see #2). The `test_one_pipe_dry_run_event_and_no_stray_pipeline_events` assertion checks the **absence** of `PIPELINE_EXECUTE`/`PIPELINE_COMPLETE`, which `validate_pipes` is structurally incapable of emitting, and the spy is attached *after* `acquire_library` — so it passes for the wrong reason and wouldn't catch a regression that emitted those during acquisition. Low-med; tighten when Phase 3 adds real callers.

---

## Refuted (do NOT re-chase without new evidence)

- **`_root_cause_is` `__cause__`/`__context__` over-breadth** (both sub-claims REFUTED). (a) No realistic dry-run path chains an *unrelated* genuine error onto a handled `PipeNotFoundError` via `__context__` — Python only sets `__context__` while the `except` is active; the one site that catches-and-reraises (`PipeParallel._dry_run` ~L240-242, `raise PipeRunError(...) from exc`) chains the `PipeNotFoundError` as the *genuine* cause. (b) A same-bundle missing/typo sub-pipe fails **earlier** — at library load, `library.validate_library()` → `validate_pipe_library_with_libraries` (`libraries/library.py` ~L126-140) raises `LibraryError`, or the unguarded step-1 pass (#1) raises a bare `PipeNotFoundError` — so it never reaches the cause-walk classifier. The wrapped-`PipeNotFoundError` shape only arises for *cross-package* deps, the intended SKIPPED case. The unit test `test_skipped_when_run_raises_wrapped_pipe_not_found` hand-builds that shape and is a fair pin.
- **Per-pipe `get_crate` O(N) rebuild** (REFUTED): `LibraryManager.get_crate` is cached in `_crate_cache` keyed by `library_id` (`libraries/library_manager.py` ~L207-215). The sweep uses one constant `library_id`, so the crate builds once (first pipe) and every later pipe is a cache hit. The crate is also genuinely consumed in DRY mode. (Separate from #4, which is about the trace event-log read, not the crate.)
- **Circular import / missing `pipe_ref` / boot requirement** (REFUTED): no transitive import of `dry_run` from `bundle_validator`'s graph; every `DryRunOutput(...)` site (4 in `dry_run.py`, 4 in `bundle_validator.py`) passes the new required `pipe_ref`; `BundleValidator()` constructs fine pre-boot and is never built at module scope; the `PipeRunProtocol` annotation under `TYPE_CHECKING` is safe (PEP 526 — not evaluated inside `__init__`).
- **`get_config()` called twice per sweep** (REFUTED): it's a singleton-field read, negligible.

## Cross-references

- Design: [`D-plan.md`](D-plan.md) §4.2 (the validation-sweep order), decisions **D3** (union catch + SKIPPED cause-walk), **D6** (two lifecycles / inner-sweep loaded-on-success contract — the callers in #1), **D7** (wiring pass before signature pre-pass — the ordering #1 must preserve while adding SKIPPED tolerance), **D5 / §4.9** (concurrent activity hosting — the trigger for #3/#4) and [`followup-temporal-validation-activity.md`](followup-temporal-validation-activity.md) (the `scoped_content_generator` remedy #3 should mirror).
- Execution: [`/TODOS.md`](../../TODOS.md) — Phase-3a checklist already lists the #2 toml migration and the #1-adjacent caller wiring; the Checkpoint-A2 handoff block already flags #7 (acquire_and_validate untested) and the #1-adjacent validate_bundle-vs-validate_pipes distinction.
- Prior review: [`seam-extraction-review-fixes.md`](seam-extraction-review-fixes.md) — its "Not in scope" already names the #6 shared-teardown-helper cleanup.
