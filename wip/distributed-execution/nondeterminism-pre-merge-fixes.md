# PR #987 pre-merge fixes — PipelineManager resubmission 500 + eager temporalio import

> **STATUS: BOTH FIXES IMPLEMENTED (2026-06-11).** As built:
>
> - **Fix 1:** `remove_pipeline` (tolerant pop) added to `PipelineManagerAbstract` + `PipelineManager`; called from `execute_pipeline`'s `finally` (after `close_tracer` — tracer-shield ordering) AND from `pipeline_run_setup`'s own failure path. The setup-side removal goes beyond the original fix shape: the runner can't clean setup failures (it never learns the id when setup raises), and the window between `add_new_pipeline` and the old `try` (i.e. `acquire_library`) also stranded the entry — the setup `try` now starts before `acquire_library` with a `library_acquired` guard preserving the old teardown ownership split. Concurrent-duplicate raise kept (load-bearing tracer shield), pinned by unit test. Tests: `tests/unit/pipelex/pipeline/test_pipeline_manager.py`, `tests/integration/pipelex/pipeline/test_pipeline_run_id_resubmission.py` (red-first).
> - **Fix 1 caveat:** the fire-and-forget `/pipeline/start` path (pipelex-api `ApiRunner.start_pipeline`) has no submitter-side terminal hook, so a started run's id stays registered for the submitter process lifetime — resubmission there now gets a clean 409 instead of a 500, but is still process-permanent. Recorded with the deeper keying/lifecycle question as item 7 in [nondeterminism-follow-ups-decisions-needed.md](nondeterminism-follow-ups-decisions-needed.md).
> - **409 mapping:** landed in `pipelex-api` on branch `fix/pipeline-run-id-conflict-409` (override entry + route-level tests + changelog + `docs/error-responses.md` status-code section, which also gained the previously-undocumented 501 override). Uncommitted in that repo's working tree, agent-check + full suite green.
> - **Fix 2:** module-level temporalio import replaced by a `sys.modules` sniff in `_is_in_temporal_activity`; `bridge.py`'s lazy-import docstring claim is true again (no edit needed there). Tests: `tests/unit/pipelex/reporting/test_temporal_activity_gate_lazy_import.py` incl. subprocess boot-cost guard (red-first); temporal integration True-branch suites green.
>
> Original brief below, kept for context.

> **Cold-start brief.** Two findings from the pre-merge xhigh review of PR #987 (`fix/Config`, "fix(temporal): workflow determinism") that should be fixed before merge. Everything else the review surfaced is either already captured in [nondeterminism-follow-ups-decisions-needed.md](nondeterminism-follow-ups-decisions-needed.md), recorded as breakage item 7 in [bridge-changes-sibling-repo-reconciliation.md](bridge-changes-sibling-repo-reconciliation.md) (the `pipelex-mistralai-workflows` reporting-path change), or is low-priority cleanup. Both fixes below were adversarially verified against the working tree on 2026-06-11 — line numbers were exact then; re-verify before editing, they drift.
>
> Repo norms apply: red-first TDD for behavior changes, `make agent-check` clean, CHANGELOG `[Unreleased]` entries, no new bare `except Exception`.

## Fix 1 — `PipelineManager` makes resubmission of the same `pipeline_run_id` a process-permanent 500

### The bug

`PipelineManager` is the one per-run registry PR #987 did NOT make self-healing, and unlike the three it patched (library / tracer / event-log context), it has **no per-run removal at all**:

- `pipelex/pipeline/pipeline_manager.py:40-46` — `add_new_pipeline` raises `PipelineManagerAlreadyExistsError` when `pipeline_run_id` is already in `self.root`. This is the exact pre-M1 raise-on-collision shape the PR removed from `GraphTracerManager.open_tracer`.
- `pipelex/pipeline/pipeline_manager.py:20-21` — the only cleanup is whole-process `teardown()` (`self.root.clear()`). Grep confirms no `remove`/`pop`/per-run forget anywhere; the abstract has only setup/teardown/get/add.
- `pipelex/pipeline/runner.py:206` — the runner's `finally` meticulously closes the tracer, clears the event-log context, and tears down the per-run library, but **never touches the PipelineManager entry**. Every run permanently strands its key.

### Trigger (real today, not latent)

`pipelex/pipeline/pipeline_run_setup.py:141` calls `add_new_pipeline(pipe_code=pipe_code, pipeline_run_id=pipeline_run_id)` **before anything else** (before `acquire_library` at ~153 and `open_tracer` at ~205). The hosted runner API threads a **client-supplied** id into it: `pipelex-api/api/routes/pipelex/pipeline.py:83-99` passes `pipeline_run_id` from the request (`extras.pipeline_run_id`, populated externally, e.g. by an API gateway). So: two POSTs to the start endpoint with the same `pipeline_run_id` against the same long-lived server process → the second raises `PipelineManagerAlreadyExistsError` → `pipelex-api/api/exception_handlers.py` has **no** AlreadyExists/409 mapping → **unhandled 500** — and since the key is never removed, every retry of that id 500s until process restart.

This directly contradicts PR #987's own changelog, which names "resubmission of the same `pipeline_run_id`" as a real, supported scenario (it's one of the motivations for the run-id rekeying). Worker-side retry/reset/replay does NOT re-enter `add_new_pipeline` (it's submitter-side), which is why the PR's worker-side fixes don't cover it.

Aggravating detail: the registry is effectively write-only — `get_pipeline`/`get_optional_pipeline` have zero production callers in `pipelex/` or `pipelex-api/`. Today the dict exists to mint ids and raise on collision.

### ⚠️ Coupling — do NOT just make it self-healing

The raise at `pipeline_manager.py:41` is currently the **only** thing shielding direct mode from a second PR-#987 finding: `GraphTracerManager.open_tracer`'s new pop-and-replace healing (`pipelex/graph/graph_tracer_manager.py:139-149`) assumes "an existing key can only be a stale leftover", which is proven only for run-unique Temporal `run_id` keys. In direct mode the tracer key is the caller-suppliable `pipeline_run_id` (`pipeline_run_setup.py` ~205 opens with `tracer_key=None`, so `key = pipeline_run_id`). Two **concurrent** runs with the same id would have run 2 silently pop run 1's LIVE tracer (cross-wired graphs, then run 1's `finally` `close_tracer` pops run 2's tracer) — today that can't happen only because `add_new_pipeline` raises first, at line 141, before `open_tracer` is reached. A bare overwrite-on-collision in `add_new_pipeline` would unshield that path.

### Recommended fix shape

Keep the collision raise for **concurrent** duplicates (it's load-bearing, see above); fix the **process-permanence** and the API surface:

1. **Per-run removal in the runner's `finally`** (`pipelex/pipeline/runner.py:206` block): add a `remove_pipeline(pipeline_run_id)` (tolerant pop) to `PipelineManagerAbstract` + `PipelineManager` and call it alongside the existing tracer/event-log/library cleanup. Serial resubmission of a completed/failed run id then works; only genuinely concurrent same-id runs still collide — which is the correct, loud behavior given the tracer coupling.
2. **Map the collision to a 4xx in `pipelex-api`**: add `PipelineManagerAlreadyExistsError` → 409 in `pipelex-api/api/exception_handlers.py` so a true concurrent duplicate is a client-visible conflict, not a 500. (This is a `pipelex-api` change — per workspace rules it lands in that repo, with its own changelog entry.)
3. Leave the deeper question — whether `PipelineManager` should adopt run-unique keying / self-heal like the three patched siblings, and whether `open_tracer`'s healing should be gated to run-scoped keys — to the decisions doc; don't solve it in this PR. If you DO decide to self-heal here instead, you must simultaneously harden `open_tracer` (heal only run-scoped keys, or make direct-mode keys run-unique at registration).

### Tests (red-first)

- Unit (`tests/unit/pipelex/pipeline/`): resubmitting a `pipeline_run_id` after the previous run's cleanup ran → `add_new_pipeline` succeeds (RED before fix 1). A second `add_new_pipeline` while the first is still registered → still raises (pins the concurrent-duplicate guard and the tracer shield).
- Integration: a full `execute_pipeline` run followed by a second run with the same explicit `pipeline_run_id` succeeds end-to-end; the runner `finally` removes the entry even when the pipe fails (assert on the manager after a failing run).
- Note: removal must be tolerant (pop, not raise) — the entry may legitimately be absent if setup failed before line 141 committed it.

## Fix 2 — module-level `temporalio` import puts ~130ms + the Rust bridge on every pipelex boot

### The bug

`pipelex/reporting/reporting_manager.py:25-28`:

```python
try:
    from temporalio import activity as _temporal_activity
except ImportError:
    _temporal_activity = None  # type: ignore[assignment]
```

`reporting_manager.py` is imported by `pipelex/pipelex.py` (module import chain), i.e. on **every** `Pipelex.make()` / CLI invocation. Wherever the `pipelex[temporal]` extra is installed — including processes that never touch Temporal (CLI `validate` runs, direct-mode servers, the `pipelex-api` runner image) — this now pays the full temporalio import at boot: **measured ~131ms** in this venv (`.venv/bin/python -c 'import time;t=time.perf_counter();from temporalio import activity;print(time.perf_counter()-t)'`), plus the Rust-bridge/protobuf memory footprint. It also silently breaks the documented lazy-import contract: `pipelex/runtime_bridge/bridge.py`'s module docstring still says "The Temporal extra is lazy-imported only inside the temporal-mode branches" — now false.

### Recommended fix shape

Replace the eager import with a `sys.modules` sniff — strictly better than a lazy cached import, because a process that never imported temporalio **cannot** be inside a Temporal activity (the activity context is set by temporalio's own machinery, which requires the module to be imported):

```python
import sys

def _is_in_temporal_activity() -> bool:
    """True when the current call stack runs inside a Temporal activity.

    sys.modules sniff instead of importing temporalio: if temporalio.activity was never
    imported in this process, no activity context can exist, and importing it here would
    put the entire temporalio extra (Rust bridge, protobuf) on every boot's critical path.
    """
    activity_module = sys.modules.get("temporalio.activity")
    if activity_module is None:
        return False
    return activity_module.in_activity()
```

Delete the module-level try/except entirely (no top-level `temporalio` name should remain). Worker processes are unaffected: by the time any activity runs, `temporalio.activity` is necessarily in `sys.modules`. Keep the gate's behavior contract identical — the existing unit suite (`tests/unit/pipelex/reporting/test_emit_runner_fallback.py`) pins it.

### Tests (red-first)

- Unit: `_is_in_temporal_activity()` returns False when `temporalio.activity` is absent from `sys.modules` (monkeypatch `sys.modules` with the key removed) and delegates to `in_activity()` when present — RED while the module-level import exists (the monkeypatch test can't even simulate "not imported" today since module import already bound the name).
- Boot-cost guard (the actual regression): a subprocess check asserting `import pipelex.reporting.reporting_manager` does **not** pull `temporalio` into `sys.modules`. Cheap and pins the lazy-import contract the docstring promises. Suggested home: `tests/unit/pipelex/reporting/`.
- Existing temporal integration suite must stay green — the H1 routing tests (`test_wf_pipe_router_costs_only_flush_nondeterminism.py`, split-worker tracing tests) exercise the True branch for real.

## Acceptance

- [x] Both fixes implemented with their red-first tests; the concurrent-duplicate raise and the tracer-shield coupling explicitly pinned by a test.
- [x] `pipelex-api` 409 mapping landed in that repo (branch `fix/pipeline-run-id-conflict-409`, uncommitted working tree, suite green).
- [x] `pipelex/runtime_bridge/bridge.py` module docstring's lazy-import claim is true again.
- [x] CHANGELOG `[Unreleased]` entries for both (pipelex), plus pipelex-api's changelog for the 409 mapping.
- [x] `make agent-check` clean; targeted suites (unit reporting + pipeline, temporal integration) green along the way; full `make agent-test` green at the end.
