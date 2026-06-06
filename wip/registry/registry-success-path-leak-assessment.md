# Assessment: verifying the `UsageRegistry` success-path leak

**Status:** Verification + analysis of [`registry-success-path-leak-brief.md`](registry-success-path-leak-brief.md). Confirms the bug, extends the blast radius, and recommends a direction. Superseded in part by [`registry-success-path-leak-execution-contexts.md`](registry-success-path-leak-execution-contexts.md), which revisits the recommendation through the DIRECT-vs-Temporal lens — read that one second.

> Line references are indicative (this branch at time of writing); the symbol names are the durable anchors.

## Verdict

Confirmed. `pipeline_run_setup` opens a per-run `UsageRegistry` in the process-global `ReportingManager` singleton and only closes it on the **failure** path. Every **successful** run leaves one `UsageRegistry` in `_usage_registries` forever. On the hosted server this is worse than the brief spells out — see the blast radius below.

## The mechanism

The asymmetry is entirely inside `pipeline_run_setup` (`pipelex/pipeline/pipeline_run_setup.py`):

- `open_registry(...)` then `registry_opened = True` (~`:209-210`), unconditional once the library is acquired.
- The happy path sets `success = True` and returns the `PipeJob` (~`:261-262`).
- The `finally` gates **all** cleanup behind `if not success:` (~`:263-281`). So on success the `close_registry` (~`:281`) never runs.

The registry then has no other owner on the success path:

- `PipelexRunner.execute_pipeline`'s `finally` (`pipelex/pipeline/runner.py` ~`:202-226`) closes the graph tracer, clears the event log, and tears down the library — but **not** the registry. It is the one resource it forgets.
- The only production `close_registry` call sites are `BundleValidator` (the dry-run sweep — closes correctly in `finally`, `bundle_validator.py` ~`:248`) and the failure-only branch in `pipeline_run_setup`.
- `ReportingManager.setup()` clears the dict and seeds the `UNTITLED` baseline, but it runs once at `Pipelex.make()`, not per run.

So the dict grows by one entry per successful run, for the life of the process.

## Blast radius — who actually leaks

Every in-process run funnels through `execute_pipeline` → `pipeline_run_setup`. The consumers:

| Path | Opens registry | Reads it after run | Closes it | Net |
|---|---|---|---|---|
| CLI `cli/commands/run/_run_core.py` (`generate_report` after return) | yes | yes | **no** | leaks, but process tears down → harmless |
| agent CLI `agent_cli/.../run/_run_core.py` | yes | no | **no** | leaks, process tears down → harmless |
| **`pipelex-api` `/pipeline/execute`** | yes | no | **no** | **leaks on a long-lived server** |
| **`pipelex-api` `/pipeline/start`** | yes | no | **no** | **leaks — registry is pure dead weight** |

Two corrections/extensions to the brief:

1. **Both** API endpoints leak, not just "the API runner path" generically. `/pipeline/execute` goes through `execute_pipeline`; `/pipeline/start` calls `pipeline_run_setup` directly, bypassing `execute_pipeline`. This matters for the fix: anything that only touches `execute_pipeline` will **miss `/pipeline/start`**.
2. **`/pipeline/start` is the worst case.** It opens the registry, hands the job to Temporal, and returns. The pipe runs on the worker, where the registry was never opened — `_get_registry_strict` / `_try_add_to_registry` deliberately skip on `KeyError` and the worker emits `UsageReportEvent`s instead. So the API-process registry from `/pipeline/start` is **never written, never read, and never closed**. It exists only to leak.

The worker itself does **not** leak via this mechanism (it never opens a registry).

## Secondary findings

- **`inject_tokens_usages` is dead code.** Its docstrings describe a "P1 cross-worker assembly path" that reads the registry back for distributed runs — but it has **zero callers in the workspace**. Nothing depends on the `/pipeline/start` registry staying alive, which removes the main reason to hesitate before closing it on the handoff path.
- **Caller-supplied `pipeline_run_id` → latent 500.** `open_registry` *raises* `ReportingManagerError` on a duplicate id, and `/pipeline/start` accepts a caller-supplied `pipeline_run_id`. Because the prior run's registry leaks, an idempotency-style retry with the same id collides on `open_registry` and surfaces a 500 — the same singleton-keyed-by-ad-hoc-id fragility class the brief's "Related" section calls out for the `/validate` race.
- **`cocode` double-counts.** `cocode/swe/swe_cmd.py` calls `generate_report()` with **no** `pipeline_run_id`, which iterates the entire `_usage_registries` dict. In a multi-run `cocode` process, leaked registries from earlier runs get re-reported every time.

## Why it isn't a one-liner

Dropping `close_registry` into `execute_pipeline`'s `finally` breaks the CLI. The CLI reads the registry **after** `execute_pipeline` returns; a close in the `finally` means the subsequent `generate_report(pipeline_run_id=...)` hits `_get_or_create_registry`, which **silently creates a fresh empty registry** and prints a $0.00 cost report. Not a crash — a silent wrong number, which is worse. And that one-liner still would not touch `/pipeline/start`.

## Recommended direction (as of this assessment)

The root cause is that the registry's lifetime escapes the runner for exactly one reason: the CLI's post-return read. Kill that reason and the lifecycle collapses into the runner cleanly. Two parts:

**Part 1 — in-process path (covers CLI, agent CLI, API `/execute` in one place).** Give `execute_pipeline` full ownership: generate the report *inside* it (before the `finally`), then close the registry in the `finally` alongside the tracer / event-log / library teardown it already does. The CLI stops calling `generate_report` itself and passes its `--cost-report` override + print/CSV intent into the runner. Because all in-process consumers share `execute_pipeline`, this fixes them with one `finally`.

- Cleaner variant: surface the run's `tokens_usages` on `PipelexPipelineExecuteResponse`, close the registry in `execute_pipeline`'s `finally`, and have the CLI render from the response via `CostRegistry.generate_report(tokens_usages=...)` (which already takes a usage list). The registry becomes a pure internal detail and the read-after-run hazard disappears — at the cost of a response-model field + a small `ReportingProtocol` getter.

**Part 2 — handoff path (`/pipeline/start`, in `pipelex-api`).** This bypasses `execute_pipeline`, so it needs its own fix. Since the registry is dead weight there, wrap setup+handoff in a `try/finally` that calls `close_registry`.

The brief's bare "caller-owned close" is the most fragile option (multiple sites to keep in sync forever; new `execute_pipeline` consumers silently reintroduce the leak) — fine only as a minimal stopgap, not the target.

> **Note (post-revisit):** the execution-contexts analysis sharpens Part 1 — "generate the report inside `execute_pipeline`, read before close" is only meaningful for DIRECT execution; under Temporal the submitter's registry is always empty. See the companion doc.

## Verification for the eventual fix

- Success-path characterization: `_usage_registries` returns to its baseline (just the `UNTITLED` seed) after a successful full run through `execute_pipeline` — the mirror of the existing failure-path test in `test_pipeline_run_setup_characterization.py`.
- CLI cost report still prints correct non-zero usage (read happens before the close).
- `pipelex-api`: `/pipeline/start` and `/pipeline/execute` leave no registry behind across successive requests on a persistent app; reusing a `pipeline_run_id` on `/pipeline/start` no longer 500s on `open_registry`.
- Full `make agent-test`, since this touches shared run/teardown infrastructure.
