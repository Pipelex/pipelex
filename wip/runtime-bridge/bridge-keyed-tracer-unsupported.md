# Bridge + keyed tracers (tracer_key ≠ graph_id) — unreachable, unsupported by contract

**Status:** ✅ RESOLVED (refuted as unreachable; `lookup_key` kept with a precise comment; **no guard code** — that would be over-engineering for a configuration nothing produces). Bigger-hammer structural option recorded below for if keyed tracers ever need to flow through the bridge.

**Raised by:** PR #969 round-4 review — greptile-apps **P1** (`bridge.py:179`, "Separate tracer keys") + cubic-dev-ai **P2** (same line, confidence 6).

## The finding

`build_pipe_job_from_input` derives the run id, when no explicit `pipeline_run_id` is given, as `trace_context.lookup_key` (= `tracer_key or graph_id`). The reviewers observed: when a host's `tracer_key != graph_id`, trace events are emitted under the tracer's *event* `pipeline_run_id` (which falls back to `graph_id`), **not** under `tracer_key`. But `PipeRun.run` assembles tracing by `job_metadata.pipeline_run_id` (now = `tracer_key`). So assembly would read the `tracer_key` partition, find no events, and the run would silently return an empty graph + no cost data — even though events were emitted.

This is **correct analysis** of an abstract data-flow. It is **not a reachable bug**, and the convenient "fix" is wrong — so the resolution is a tightened comment + refutation, not new code.

## Why it is not a reachable bug

Verified against the code (`pipe_run.py`, `bridge.py`, `wf_pipe_router.py`, `trace_context.py`):

- The in-process `PipeRun.run` keys **both** `close_tracer` (pipe_run.py:60) **and** `assemble_tracing_on_output` (pipe_run.py:78) off the **single** `job_metadata.pipeline_run_id` (pipe_run.py:35). One key, not two — and events are emitted under `pipeline_run_id or graph_id`.
- The bridge **nulls `trace_context` for all non-DIRECT modes** (bridge.py:133), so only DIRECT runs ever receive one.
- The **only** place that opens a keyed tracer (`tracer_key != graph_id`) is the Temporal child path `wf_pipe_router` — and it **never calls the bridge** (`grep`-confirmed: no `build_pipe_job_from_input` / `run_pipe_via_bridge` under `pipelex/temporal/`). It uses its own activity-based assembly, not `PipeRun.run`.
- Every bridge-reachable caller opens its tracer the way `pipeline_run_setup` does — `graph_id == pipeline_run_id`, `tracer_key` unset — so `lookup_key == graph_id == event-partition` and all three keys coincide.

So the divergence requires a *host integrator* to hand-build a Temporal-style keyed `TraceContext` and force it through the DIRECT bridge — which nothing does, and which the contract ("open a tracer for this pipeline run"; `graph_id` "typically the pipeline run id") does not anticipate. No internal Pipelex code reaches the bridge with a keyed trace_context.

## Why `lookup_key` is the right value (and `graph_id` is not)

The convenient counter-"fix" — switch back to `trace_context.graph_id` — is **wrong**: it re-breaks `close_tracer` for any keyed tracer (`close_tracer` needs the registration key, `lookup_key`). `lookup_key` and `graph_id` differ only for a divergent keyed tracer, which (per above) never reaches the bridge — so on every reachable path `lookup_key == graph_id` and `lookup_key` is correct for registration, close, event-emission, and assembly simultaneously.

## Decision: comment, not guard

An earlier round-4 attempt added a loud boundary guard that rejected a divergent `tracer_key` with `PipelexBridgeDispatchError`. It was **backed out** on review (this PR) as over-engineering: it defended a configuration no code path produces (only host misuse), it was only *partial* (it caught `tracer_key ≠ graph_id` but could not catch a host opening with `tracer_key=None, pipeline_run_id ≠ graph_id`, which the bridge cannot see from `graph_id` + `tracer_key` alone), and it sat on top of the round-3 `lookup_key` change that was itself defending the same unreachable case. The net of two rounds of churn over a non-occurring config was the smell.

Resolution: keep `lookup_key`, document the reachability + the unsupported keyed-tracer contract in the code comment at the derivation site, and refute the review thread with the reachability proof. No behavior change, no new code.

## Deferred: if keyed tracers ever need bridge support

The structural fix, only worth it once a real caller needs `tracer_key != graph_id` through the bridge: give `TraceContext` an explicit event-partition field (the value the host passed to `open_tracer(pipeline_run_id=...)`) so the bridge stops *inferring* it from `graph_id`/`tracer_key`. Then `JobMetadata.pipeline_run_id` (assembly/close key) and the event-partition can be carried independently end-to-end. This touches `TraceContext` across `graph/`, `temporal/`, and the in-process tracing path, so it is over-engineering for a configuration nothing currently produces — hence deferred, not done.
