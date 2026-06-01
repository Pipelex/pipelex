# Seam-extraction review fixes (post-Checkpoint A)

Follow-up fixes from the `xhigh` code review of the Phase-1 seam extraction (Checkpoint A, commit `f04c4c7a` on branch `feature/Validate-with-signatures-4-fix-dry-run`). Apply these **before** starting Phase 2 (`BundleValidator`), because Phase 2 composes the seams that fixes #1 and #3 harden.

Scope: **fixes 1–3 + tidy one test.** The orphan-trace telemetry residual (handle_trace_start firing before working-memory assembly) is the *same reorder root* as fix #2 but is **out of scope here** — note only.

## Cold-start

1. `git log --oneline -3` should show `f04c4c7a refactor(dry-run): extract execution seams (Phase 0+1, Checkpoint A)` (+ the docs SHA commit on top).
2. Re-verify the seam symbols still exist: `acquire_library` / `prepare_pipe_job` in `pipelex/pipeline/execution_seams.py`; the recomposed wrapper in `pipelex/pipeline/pipeline_run_setup.py`.
3. TDD: write the failing test first for each fix, then the fix. Verify with `make agent-check` + the targeted run at the bottom, then full `make agent-test`.
4. These are small, surgical edits to already-green code — do **not** re-architect the seams.

---

## Fix 1 — `acquire_library` must use `open_library`'s returned id (CONFIRMED, do first)

**File:** `pipelex/pipeline/execution_seams.py`, in `acquire_library` (currently ~line 74).

**Problem:** `acquire_library` calls `library_manager.open_library(library_id=library_id)` but **discards the return** and returns its own `library_id` param. `open_library` (`pipelex/libraries/library_manager.py:144`) generates a fresh UUID when given a *falsy* id (`if not library_id: library_id = self.generate_library_id()`). And `teardown(library_id="")` (`library_manager.py:114`) falls past the `if library_id:` guard and **tears down ALL libraries**; `get_crate("")` returns `None`. Safe today (the sole caller always passes a concrete id) but a landmine the moment a Phase-2 caller passes `library_id=""` (a valid `str`, since the signature is `library_id: str`).

**Change:** capture the canonical id from `open_library`:

```python
# was:  library_manager.open_library(library_id=library_id)
library_id, _ = library_manager.open_library(library_id=library_id)
```

Everything downstream (`set_current_library`, `load_*`, `get_crate`, `teardown`, the returned tuple) then uses the id `open_library` actually keyed the Library under.

**Test (add to `tests/integration/pipelex/pipeline/test_execution_seams.py`, `TestExecutionSeams`):**

- `acquire_library(library_id="", mthds_contents=[_SEAMS_MTHDS])` returns a **non-empty** library_id (the generated one) and leaves *that* library current/loaded; `get_required_pipe` against the returned main_pipe works. Tear down the **returned** id in a finally.
- Regression for the catastrophe: with an unrelated library open first, force a load failure (patch `resolve_library_dirs` to raise, as the existing fail-test does) while passing `library_id=""`, and assert `teardown_spy` was called with the **generated** id (not a falsy id) — i.e. only the just-opened library is torn down, not all of them.

---

## Fix 2 — close the report registry on the wrapper's failure path (CONFIRMED)

**File:** `pipelex/pipeline/pipeline_run_setup.py`, the wrapper's `try/finally` (currently ~lines 201 open_registry, ~254–267 finally).

**Problem:** the reorder moved working-memory assembly into `prepare_pipe_job`, which now runs **after** `get_report_delegate().open_registry(pipeline_run_id=...)`. The `finally` tears down tracer/event-log/library/current but never closes the registry. `close_registry` (`pipelex/reporting/reporting_manager.py:393`) exists and is called **nowhere**; `runner.py` doesn't close it either. So a failure inside `prepare_pipe_job` (bad concept → `make_from_pipeline_inputs` raises; or `await normalize_data_urls_to_storage` raises) leaks a `UsageRegistry` keyed by `pipeline_run_id`, unbounded in a long-lived runner. This also covers the **pre-existing** leak (failures after open_registry in the original) — per the repo "flag and fix" rule.

**Critical nuance:** `close_registry` does a bare `self._usage_registries.pop(pipeline_run_id)` — **no default**, so it raises `KeyError` if the registry was never opened. The wrapper's `finally` also runs for failures **before** `open_registry` (pipe resolution, graph-open, run-mode). So you **must guard** with a flag — do NOT call close_registry unconditionally.

**Change:**

```python
# before the try, alongside graph_context / event_log / success:
registry_opened = False
...
        get_report_delegate().open_registry(pipeline_run_id=pipeline_run_id)
        registry_opened = True   # <-- immediately after open_registry
...
    finally:
        if not success:
            if graph_context is not None:
                ... close_tracer ...
            if event_log is not None:
                get_report_delegate().clear_event_log(context_key=pipeline_run_id)
            if registry_opened:
                get_report_delegate().close_registry(pipeline_run_id=pipeline_run_id)
            ... (fix 3 current-library restore, then library teardown) ...
```

**Test (add to `test_pipeline_run_setup_characterization.py`):** patch `pipeline_run_setup`'s `prepare_pipe_job` (module-level name) to raise; spy on `get_report_delegate().close_registry`; call `pipeline_run_setup(...)` (with a valid resolvable `pipe_code`, so the failure lands *after* open_registry); assert `close_registry` was called once with the run's `pipeline_run_id`. Add a second case: an **early** failure (`pipe_code="absent_pipe"`, fails *before* open_registry) must **not** call close_registry and must **not** raise `KeyError` — proves the guard.

---

## Fix 3 — wrapper's failure path must restore the outer current-library (PLAUSIBLE; do with #2, same finally)

**File:** `pipelex/pipeline/pipeline_run_setup.py` (wrapper finally) + its hub import block.

**Problem:** `acquire_library`'s finally **restores** the caller's outer current-library (`prev_library_id`); the wrapper's post-acquire finally calls `teardown_current_library()` **unconditionally** (clears to `None`). Asymmetric — and diverges from the codebase convention (every `validate_bundle.py` entry point + `hub.scoped_current_library` restore-prev). A post-acquire failure clobbers an outer caller's current-library to `None`. Latent today (sole caller `runner.execute_pipeline` sets no outer current-library) but bites the Phase-2 `BundleValidator`-looping reuse the seams exist for.

**Change:**

1. Re-add hub imports the refactor dropped: `set_current_library`, `get_current_library_id_or_none` (currently the wrapper imports neither).
2. Capture `prev_library_id = get_current_library_id_or_none()` **before** the `acquire_library(...)` call (acquire sets current to the new id, so capture must precede it).
3. In the finally, mirror `validate_bundle` — restore current-library **first** (so the guarantee survives a teardown raise), then teardown the library:

```python
            if prev_library_id is not None:
                set_current_library(library_id=prev_library_id)
            else:
                teardown_current_library()
            library_manager.teardown(library_id=library_id)
```

**Tests:**

- The existing `test_load_failure_tears_down_library` (no outer context) **still passes** (prev is `None` → `teardown_current_library` → `None`). Keep it.
- **Add** a case (in `test_pipeline_run_setup_characterization.py`): set an outer current-library, then trigger a post-acquire failure (`pipe_code="absent_pipe"`), and assert `get_current_library_id_or_none()` is **restored to the outer id**, not `None`. (Mirror `TestValidateBundleRestoresOuterLibraryOnFailure` in `test_validate_bundle_library_lifecycle.py`; tear the outer down in a finally.)

---

## Fix 4 — tidy the misleading truthiness test

**File:** `tests/integration/pipelex/pipeline/test_pipeline_run_setup_characterization.py`, `test_empty_inputs_behave_like_no_inputs`.

**Problem:** it claims to pin `if inputs:` vs `inputs is not None`, but it doesn't discriminate them: an empty `PipelineInputs` through `make_from_pipeline_inputs` also yields an empty `.root`, so the assertion passes under either semantic. The invariant is unguarded.

**Where the truthiness actually matters:** the normalize gate `if working_memory and is_normalize_data_urls_to_storage and not is_mock_inputs` in `prepare_pipe_job`. With empty `PipelineInputs` + `is_normalize=True` + `mock=False`: `if inputs:` is falsy → `working_memory` stays `None` → normalize **skipped**. Under `inputs is not None` it would be an empty WorkingMemory (always truthy → no `__bool__`) → normalize **runs**.

**Change (pick one):**

- **Preferred (discriminating):** add/repurpose a `prepare_pipe_job` unit test that patches `execution_seams.normalize_data_urls_to_storage` (spy), passes `inputs=PipelineInputs()` with an `execution_config` where `is_normalize_data_urls_to_storage=True, is_mock_inputs=False`, and asserts normalize was **not** called (proving `inputs` was treated as falsy / no working memory built). A `inputs is not None` regression would then call normalize → test fails.
- **Minimum:** relabel the test + docstring to assert only what it can (empty `PipelineInputs` → empty working memory, no crash) and drop the "pins `if inputs:`" claim, so it stops over-promising.

---

## Verification

```bash
make agent-check
.venv/bin/pytest -n auto -m "(dry_runnable or not (inference or llm or img_gen or extract or search)) and not pipelex_api" -o log_level=WARNING --tb=short -q \
  tests/integration/pipelex/pipeline/ tests/integration/pipelex/pipes/ tests/integration/pipelex/pipe_signature/ tests/e2e/pipelex/graph/
make agent-test   # full suite, must stay green
```

Note: `make agent-test` runs under xdist — current-library / library-manager singleton state is **shared per worker across sequentially-run tests**. Tests that assert on `get_current_library_id_or_none()` or teardown counts must capture a `prev`/`before` baseline and restore/clean up in a `finally` (a fixed-`is None` assertion already bit us once — see `test_acquire_library_tears_down_on_load_failure`). Use unique library ids or fixture-managed teardown.

## Not in scope (residuals noted by the review, defer)

- **Orphan trace-start** (`pipeline_run_setup.py` ~226): `handle_trace_start` now fires before WM assembly, so a WM/normalize failure emits a named PostHog trace with zero spans. Same reorder root as fix #2; closing the registry does **not** fix it. A deeper fix would re-split `prepare_pipe_job` so open_registry/otel/event_log run after WM build — defer, don't bundle here.
- Cleanup/altitude (reuse): `main_pipe`-derivation duplicated across `execution_seams` / `dry_run_pipeline.py` / `inputs_ops.py` → extract `find_main_pipe_ref(blueprints)`; `acquire_library`'s restore-or-teardown finally is a 5th copy of `validate_bundle`'s → extract a shared helper/contextmanager; `convert_to_working_memory_format` / `convert_stuff_spec_to_typed_named` share a registry-lookup+fallback core → delegate. Consider folding into the Phase-2 work since it touches the same seams.
- `acquire_library` runs `main_pipe` derivation even when the caller passed `pipe_code` (negligible cost; tied to the responsibility-split cleanup above).
