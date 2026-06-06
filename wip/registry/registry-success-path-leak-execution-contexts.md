# Revisit: the registry leak across execution contexts (DIRECT vs Temporal)

**Status:** Refines the recommendation in [`registry-success-path-leak-assessment.md`](registry-success-path-leak-assessment.md) after accounting for the execution backend, not just the entry point. It does change the view: the registry turns out to be a DIRECT-mode construct, and the leak is one of two separate problems currently conflated. No implementation plan here — design framing only.

> **Superseded for the recommendation by [`registry-lifecycle-synthesis.md`](registry-lifecycle-synthesis.md)** — once distributed cost aggregation entered the picture, "the registry is DIRECT-only" became "the registry is a per-run cost-aggregation buffer whose *close* (the leak) and *replay-populate* (cost reporting) are one lifecycle." The findings below still hold; the synthesis carries the current direction. Start at the folder [`README.md`](README.md).

> Line/symbol references are indicative (this branch at time of writing).

## Why the entry point alone was the wrong lens

The assessment classified consumers by **entry point** (CLI / agent CLI / API `/execute` / API `/start`). But what determines whether the registry is even *usable* is the **execution backend**, which is chosen independently at `Pipelex.make()`:

- `pipelex/pipelex.py` (~`:456-461`): if `temporal.is_enabled` → `set_pipe_run(make_temporal_pipe_run())`; else → `set_pipe_run(PipeRun(pipe_router=...))`.

So there are two orthogonal axes:

- **Axis A — submitter entry point:** CLI, agent CLI, API `/execute`, API `/start`.
- **Axis B — execution backend:** DIRECT (in-process `PipeRun`) vs TEMPORAL (`TemporalPipeRun`; in production the worker is `EXTERNAL`, a separate process).

The registry is always opened by `pipeline_run_setup`, **in the submitter process**, *before* the backend is consulted. Whether it ever gets populated depends entirely on Axis B.

## The decisive fact: where inference runs

The registry is populated by `report_inference_job` → `_try_add_to_registry`, which only adds **if a registry for that `pipeline_run_id` exists in this process**. So:

- **DIRECT** (`PipeRun.run()` via the in-process pipe router): inference runs in the submitter process. The registry opened by `pipeline_run_setup` is in the same process → **populated**. The CLI's post-run `generate_report` reads real data.
- **TEMPORAL** (`TemporalPipeRun.run()` *or* `.start()`): inference runs on the worker.
    - `TemporalPipeRun.run()` is blocking (`temporal_pipe_run.py` ~`:47-88`) — it dispatches `WfPipeRun`, waits for completion, and returns the rehydrated `PipeOutput`. But the work happened on the worker, so the **submitter's registry stays empty**.
    - The worker (`wf_pipe_router.py`) only calls `set_event_log` / `clear_event_log` — it **never opens a registry**. On the worker, `_try_add_to_registry` skips (`KeyError`) and usage is emitted as `UsageReportEvent`s into the event-log backend instead.
    - Reassembling those events into a registry is what `inject_tokens_usages` is for — and it has **no caller**. So under Temporal the cost report from the registry is empty, today, independent of the leak.

`worker_environment=INTERNAL` (in-process worker, used by tests) is the one case where a Temporal run *could* land in the same process as the open — but production hosted runs `EXTERNAL`, and the leak happens identically regardless.

## The full matrix

| Submitter | Backend | Registry opened in | Populated there? | Read there? | Closed on success? | Outcome |
|---|---|---|---|---|---|---|
| CLI `run` | DIRECT | submitter | yes | yes | no | correct report; leak bounded by process exit |
| CLI `run --temporal` | TEMPORAL | submitter | **no** | yes → **$0 report** | no | report already broken; leak bounded by process exit |
| agent CLI `run` | DIRECT | submitter | yes | no | no | leak bounded by process exit |
| API `/pipeline/execute` | DIRECT | server | yes | no | no | **leak on long-lived server** (written, never read) |
| API `/pipeline/execute` | TEMPORAL | server | **no** | no | no | **leak on long-lived server** (empty) |
| API `/pipeline/start` | TEMPORAL | server | **no** | no | no | **leak on long-lived server** (empty, pure dead weight) |
| worker (`WfPipeRun`) | — | not opened | n/a | n/a | n/a (`clear_event_log` only) | no registry leak; emits events |

The hosted product runs Temporal-enabled, so in production **both** API endpoints leak an **empty** registry per request. A self-hosted open-source `pipelex-api` without Temporal leaks **populated-but-unread** registries instead. Either way: unbounded growth on a long-lived server.

## What this changes

**1. The registry is a DIRECT-mode, in-process accumulation buffer — nothing more.** It only ever holds real data when inference runs in the submitter process. Opening it in `pipeline_run_setup` (shared by every entry point and both backends, before the backend is even known) is the structural mistake: in every Temporal path it is opened somewhere it can never be filled.

**2. There are two separate problems, currently conflated:**

- **(P1) The leak.** The registry is never closed on success, in every path. Real damage on long-lived servers; harmless on CLIs (process exit). This is the brief's bug.
- **(P2) Distributed cost reporting is not wired.** Under Temporal, usage lives on the worker as events; the submitter-side assembly (`inject_tokens_usages`) is dead code, so a Temporal run yields no registry-based cost report. The CLI `--temporal` cost report is already empty today. This predates and is independent of the leak.

**3. The assessment's Part 1 needs a caveat.** "Generate the report inside `execute_pipeline`, read before close" is only meaningful for DIRECT — under Temporal there is nothing in the submitter's registry to read, so the read-order subtlety is moot and only the *close* matters. Folding report generation into `execute_pipeline` would produce an empty report for Temporal runs (no worse than today, but it does not fix P2).

## Refined target design (leak / P1)

Make the registry's lifecycle match where it is actually used — owned by the in-process execution scope, opened only when inference runs in-process:

- **Stop opening the registry unconditionally in `pipeline_run_setup`.** It is pure setup shared by DIRECT/Temporal and execute/start — the wrong altitude for an in-process buffer. Nothing between the current `open_registry` and the return touches the registry, so removing the open from here is safe.
- **DIRECT path owns open + close around the in-process run** (in `PipeRun.run()` or `execute_pipeline`), closing in `finally`. Because DIRECT populates the registry, the report read is valid — provided the read happens before the close (assessment Part 1's cleaner variant: surface `tokens_usages` on the response and render from it, so the registry never needs to outlive the run).
- **Temporal paths (`/execute` and `/start`) open no submitter-side registry at all.** Usage is the worker's concern (events). This makes the API leak structurally impossible (nothing is opened to leak) and removes the misleading empty registry — strictly better than bolting a `close_registry` onto each handoff `finally`.

This subsumes the assessment's "Part 2" (no special `start_pipeline` close needed if `start` never opens) and is more "solid over quick" than adding closes in two `finally` blocks. The minimal stopgap (close where opened, in `execute_pipeline.finally` + `start_pipeline.finally`) still fixes P1 without restructuring, if a small diff is wanted first.

## Strategic note (P2 — separate effort)

The elegant unification: carry per-run `tokens_usages` on `PipeOutput` / `PipelexPipelineExecuteResponse`. In DIRECT mode the submitter fills it from its own registry; in Temporal mode the worker attaches its usage to the `PipeOutput` that already flows back through `rehydrate_pipe_output_with_crate`. Cost reporting would then render from the returned object in all modes, the registry singleton could shrink to an in-process accumulation detail (or disappear), and dead `inject_tokens_usages` goes away. This is the direction the leak fix should not contradict — but it is its own piece of work, not part of closing the leak.

## Is the recommended design clear?

Yes, with the refinement above. The leak fix (P1) is well-scoped and ready to plan: own the registry in the in-process execution scope, do not open it on Temporal submitter paths, and don't let it outlive the run that fills it. Distributed cost reporting (P2) is a deliberately separate effort and should not be smuggled into the leak fix. The one decision still open for P1 is presentation ownership — whether the DIRECT cost report is generated inside the runner (flag-gated) or rendered by the CLI from usage carried on the response; that is an implementation-planning question, deferred per instruction.
