# Bridge + keyed tracers (tracer_key ≠ graph_id) — guarded out, not supported

**Status:** ✅ RESOLVED for now (loud boundary guard). Bigger-hammer option recorded below for if keyed tracers ever need to flow through the bridge.

**Raised by:** PR #969 round-4 review — greptile-apps **P1** (`bridge.py:179`, "Separate tracer keys") + cubic-dev-ai **P2** (same line, confidence 6).

## The finding

`build_pipe_job_from_input` derives the run id, when no explicit `pipeline_run_id` is given, as `trace_context.lookup_key` (= `tracer_key or graph_id`). The reviewers observed: when a host's `tracer_key != graph_id`, trace events are emitted under the tracer's *event* `pipeline_run_id` (which falls back to `graph_id`), **not** under `tracer_key`. But `PipeRun.run` assembles tracing by `job_metadata.pipeline_run_id` (now = `tracer_key`). So assembly would read the `tracer_key` partition, find no events, and the run would silently return an empty graph + no cost data — even though events were emitted.

This is **correct analysis** of an abstract data-flow.

## Why it is not a reachable bug today

Verified against the code (`pipe_run.py`, `bridge.py`, `wf_pipe_router.py`, `trace_context.py`):

- The in-process `PipeRun.run` keys **both** `close_tracer` (pipe_run.py:60) **and** `assemble_tracing_on_output` (pipe_run.py:78) off the **single** `job_metadata.pipeline_run_id` (pipe_run.py:35). There is one key, not two, on this path — and events are emitted under `pipeline_run_id or graph_id`.
- The bridge **nulls `trace_context` for all non-DIRECT modes** (bridge.py:133), so only DIRECT runs ever receive one.
- The **only** place that opens a keyed tracer (`tracer_key != graph_id`) is the Temporal child path `wf_pipe_router` — and it **never calls the bridge** (`grep`-confirmed: no `build_pipe_job_from_input` / `run_pipe_via_bridge` under `pipelex/temporal/`). It uses its own activity-based assembly, not `PipeRun.run`.
- Every bridge-reachable caller opens its tracer the way `pipeline_run_setup` does — `graph_id == pipeline_run_id`, `tracer_key` unset — so `lookup_key == graph_id == event-partition` and all three keys coincide.

So the divergence requires a host to deliberately route a Temporal-style keyed tracer through the DIRECT bridge, which nothing does and the contract ("open a tracer for this pipeline run", `graph_id` "typically the pipeline run id") does not anticipate.

## Why `lookup_key` is the right value (and `graph_id` is not)

The convenient "fix" — switch back to `trace_context.graph_id` — is **wrong**: it re-breaks `close_tracer` for any keyed tracer (the round-3 leak this line was changed to fix). `close_tracer` needs the registration key (`lookup_key`); assembly needs the event-partition key (`graph_id`). They are the same value **only** when `tracer_key` is unset or equals `graph_id`. No single assignment satisfies a *divergent* keyed tracer, because the bridge builds a fresh `JobMetadata` and cannot recover the host's event-partition id from `graph_id` + `tracer_key` alone.

## Decision: loud guard, keep `lookup_key`

Rather than silently mis-assemble (the project's hard line: no silent failures), `build_pipe_job_from_input` now **rejects** a `trace_context` whose `tracer_key` diverges from its `graph_id` with `PipelexBridgeDispatchError`. Under that guard `lookup_key == graph_id`, so the existing `lookup_key` assignment is provably correct for close, registration, and assembly simultaneously. A `tracer_key` equal to `graph_id` is harmless and still allowed.

- Code: guard + tightened comment in `pipelex/runtime_bridge/bridge.py` (`build_pipe_job_from_input`).
- Tests: `tests/integration/pipelex/runtime_bridge/test_bridge_direct.py::TestBridgeDirect::test_divergent_tracer_key_in_trace_context_is_rejected` (rejects divergent, allows aligned) + the updated `test_run_id_derives_from_trace_context_when_pipeline_run_id_omitted`.

This is a boundary precondition on a "boundary" type (`extra="forbid"` DTOs), not speculative recovery logic — it converts a latent silent-data-loss into an explicit, documented unsupported-configuration error. ~10 lines, no cross-cutting change.

## Deferred: if keyed tracers ever need bridge support

The structural fix, only worth it once a real caller needs `tracer_key != graph_id` through the bridge: give `TraceContext` an explicit event-partition field (the value the host passed to `open_tracer(pipeline_run_id=...)`) so the bridge stops *inferring* it from `graph_id`/`tracer_key`. Then `JobMetadata.pipeline_run_id` (assembly/close key) and the event-partition can be carried independently end-to-end, and the guard relaxes. This touches `TraceContext` across `graph/`, `temporal/`, and the in-process tracing path, so it is over-engineering for a configuration nothing currently produces — hence deferred, not done.
