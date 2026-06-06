# Brief: `UsageRegistry` leak on the success path of a full pipeline run

**Status:** Deferred (known, not yet fixed). Surfaced during the `fix/For-API-update` work and the subsequent code review. **Not** the cause of the `/validate` 500 that branch fixes — it is a separate, pre-existing resource leak in the full-run path. Captured here so it can be picked up as its own focused, fully-tested change.

## Problem

`ReportingManager` (`pipelex/reporting/reporting_manager.py`) is a process-global singleton holding per-run `UsageRegistry` objects in `self._usage_registries`, keyed by `pipeline_run_id`. `open_registry` adds an entry; `close_registry` pops it (idempotent).

On a full pipeline run, the registry is opened in `pipeline_run_setup.py` but only closed on the **failure** path. So every **successful** run leaves its registry in the singleton dict forever — one leaked entry per successful run.

## Evidence

- `pipelex/pipeline/pipeline_run_setup.py:209` — `get_report_delegate().open_registry(pipeline_run_id=pipeline_run_id)`, unconditional after the library is acquired; `registry_opened = True` set on the next line.
- `pipelex/pipeline/pipeline_run_setup.py` `finally` block (~`:263`–`:281`) — the `close_registry` call is guarded by `if not success:`. `success = True` is set on the happy path (~`:261`), so the close is skipped on success.
- `pipelex/pipeline/runner.py` `execute_pipeline` `finally` (~`:202`–`:226`) — closes the graph tracer, clears the event log, tears down the library, but does **not** close the report registry.
- No other caller closes the per-run registry on success. The only `close_registry` call sites are `bundle_validator.py` (the dry-run sweep, which closes correctly in `finally`) and the `if not success` branch in `pipeline_run_setup.py`.
- `setup()` (`reporting_manager.py`) clears `_usage_registries` but is called once at `Pipelex.make()` startup, not per run — so the leak accumulates for the life of the process.

## Why it is not a one-line fix

The registry must stay open **past** `execute_pipeline`'s return, because the caller reads it afterwards:

- The CLI `pipelex/cli/commands/run/_run_core.py` calls `get_report_delegate().generate_report(pipeline_run_id=...)` **after** `execute_pipeline()` returns (~`:296`). The registry has to be alive for that read.
- The API runner path never calls `generate_report` and never closes the registry — so for the hosted API/worker it simply leaks.

Because the registry lifetime currently extends beyond the runner (caller-owned for the CLI, orphaned for the API), a naive `close_registry` inside `execute_pipeline`'s `finally` would **break the CLI's cost report** (it would read an empty/recreated registry). The fix has to relocate registry-close ownership across the CLI / runner / API consistently.

## Recommended direction

Decide on a single owner for the registry's full lifecycle and close on **both** paths there, after any `generate_report` read. Options, roughly in order of preference:

- **Centralize in the runner.** Have `execute_pipeline` own report generation (gated by a flag/config the CLI sets, the API leaves off) and close the registry in its `finally` after generating. Callers stop calling `generate_report` themselves. Cleanest; touches CLI + runner + API.
- **Caller-owned close.** Keep `generate_report` in the CLI but add `close_registry(pipeline_run_id)` immediately after it, and add a close on the API runner path (which never reads the registry). More surface area, easy to leave a path uncovered.
- **Scope guard.** Wrap the run in a context manager / `try/finally` that owns `open_registry`/`close_registry` around the whole run-plus-report window.

## Verification for the eventual fix

- Add a characterization test asserting `_usage_registries` returns to its baseline (just the startup `UNTITLED` entry) after a **successful** full run — the mirror of the existing failure-path test `test_pipeline_run_setup_characterization.py::test_failure_after_open_registry_closes_registry`.
- Confirm the CLI cost report still prints correct usage (the registry must be read before it is closed).
- Confirm the API/worker path no longer accumulates entries across successful runs.
- Run the full suite (`make agent-test`) since this touches shared run/teardown infrastructure.

## Related

Same class of process-global-singleton-keyed-by-ad-hoc-id fragility as the `/validate` race fixed on `fix/For-API-update` (the dry-run sweep now uses a unique `dry_run_`-prefixed id and closes in `finally`). That fix is independent of this leak and does not touch `pipeline_run_setup`.
