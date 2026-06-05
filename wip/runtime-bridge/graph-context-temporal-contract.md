# `graph_context` threaded into Temporal modes despite a DIRECT-only contract

**Status:** ✅ **RESOLVED — Option A applied.** (was: confirmed contract/docstring mismatch, deferred pending decision)
**Source:** PR #959 review — greptile-apps (P2, `bridge.py:111-128`, "Temporal modes inherit tracing").
**Severity:** real but **latent** — only mattered when a host passed a non-None `graph_context` *and* selected a Temporal mode.

## Resolution (Option A)

`run_pipe_via_bridge` now computes `is_direct = input_payload.execution_mode is PipelexExecutionMode.DIRECT` and passes `graph_context=graph_context if is_direct else None` to `build_pipe_job_from_input`, so a host `graph_context` is honored for DIRECT and **nulled for the Temporal modes** — honoring the documented contract and removing the cross-contamination foot-gun (`WfPipeRouter`'s `graph_context is not None` guard makes the None a clean no-op). The now-inaccurate "would be ignored anyway" docstring clause was rewritten to state the nulling plainly. Regression test: `tests/unit/pipelex/runtime_bridge/test_graph_context_contract.py` (DIRECT forwards the host context; TEMPORAL_BLOCKING nulls it). `make agent-check` + `make agent-test` green.

The original triage below is retained as the record of why Option A over B/C.

---

## The finding

> The docstring says `graph_context` is only honored for `DIRECT`, but this code builds the `PipeJob` with that context before dispatching every mode. For `TEMPORAL_BLOCKING` and `TEMPORAL_FIRE_AND_FORGET`, `WfPipeRouter` consumes the non-null context and opens a workflow tracer under the caller's graph id and parent node. A host activity that passes its own graph context can therefore merge or duplicate Pipelex Temporal trace events into the host activity graph, even though the bridge contract says Temporal modes ignore that context.

## Verified behavior (code trace)

**The documented contract (`pipelex/runtime_bridge/bridge.py:100-103`):**

> The optional `graph_context` is only honored for `DIRECT` execution mode — TEMPORAL modes already have their own event-log infrastructure via `pipeline_run_setup` and a passed-in context **would be ignored anyway**.

**What the code does** — `graph_context` is baked into the `PipeJob` *before* the mode `match`, so it flows into every branch:

- `pipelex/runtime_bridge/bridge.py:112-116` — `build_pipe_job_from_input(..., graph_context=graph_context)` is called unconditionally, then `:118` `match input_payload.execution_mode:` dispatches DIRECT / TEMPORAL_BLOCKING / TEMPORAL_FIRE_AND_FORGET / MISTRAL_NATIVE.
- `pipelex/runtime_bridge/bridge.py:161-165` — `graph_context` is stored into `JobMetadata`.

**`WfPipeRouter` *does* consume it** (so "would be ignored anyway" is false):

- `pipelex/temporal/tprl_pipe/wf_pipe_router.py:49` — `graph_context = workflow_arg.job_metadata.graph_context`
- `:80` — `if tracing_config.is_enabled and graph_context is not None:`
- `:87-94` — `open_tracer(graph_id=graph_context.graph_id, data_inclusion=graph_context.data_inclusion, ...)`
- `:95-100` — preserves `graph_context.parent_node_id` so "CONTAINS edges link back to the parent workflow's controller node."

So if a host passes its own `graph_context` with a Temporal mode, Pipelex's Temporal workflow opens its tracer under the **host's** `graph_id` and links edges to the **host's** `parent_node_id` — i.e. Pipelex Temporal trace events get merged into the host's graph. That is exactly the cross-contamination the docstring's contract was trying to forbid.

Note the asymmetry that makes this a *contract* bug rather than a feature: for DIRECT the host's graph_context is intended (per-step events flow into the host's tracer — `bridge.py:97-99, 142-146`); for Temporal the bridge bypasses Pipelex's own `pipeline_run_setup` graph_context creation and instead forwards the host's, which `WfPipeRouter` then treats as if it were Pipelex's own.

## The fork

**Option A — Honor the contract (recommended).** Pass `graph_context` only for DIRECT; pass `None` for the Temporal modes. E.g. compute it per-mode:

```python
is_direct = input_payload.execution_mode is PipelexExecutionMode.DIRECT
pipe_job = build_pipe_job_from_input(
    input_payload=input_payload,
    library_crate=library_crate,
    graph_context=graph_context if is_direct else None,
)
```

- Pros: makes the code match the documented intent; stops a host's graph_context from contaminating Pipelex's Temporal trace graph; tiny, low-risk; the `None` guard at `wf_pipe_router.py:80` already makes a None context a clean no-op. Aligns with the docstring author's clear intent.
- Cons: if someone *wanted* host→Pipelex Temporal trace linking, this removes the only path to it. (No evidence anyone does, and `pipeline_run_setup` is the documented Temporal tracing path.)
- Tidy-up if chosen: drop the now-inaccurate "would be ignored anyway" clause and state plainly that Temporal modes deliberately do not forward a host `graph_context`.

**Option B — Fix the docstring, keep threading it.** Treat the current behavior as intended and document that Temporal modes consume `graph_context` (parent-linking via CONTAINS edges).
- Pros: no behavior change; preserves any future host→Pipelex Temporal trace stitching.
- Cons: keeps the cross-contamination foot-gun (a host that opens its own tracer and picks a Temporal mode silently merges Pipelex's Temporal events into its graph); the "their own event-log infrastructure via `pipeline_run_setup`" rationale is then misleading, since the bridge's Temporal path doesn't go through `pipeline_run_setup` for graph_context.

**Option C — Defer.** This doc is the record; revisit when Temporal ships and the host-tracing story for Temporal modes is actually designed.

## Recommendation

Option A. It is the smaller change, removes a latent foot-gun, and makes the code obey its own stated contract. Revisit only if a concrete need for host→Pipelex Temporal trace stitching appears — at which point it should be designed explicitly (own graph id / explicit opt-in), not inherited by accident.

## Test ideas (when fixed)

- Bridge unit: call `run_pipe_via_bridge(input_payload=<TEMPORAL_*>, graph_context=<non-None>)` and assert the resulting `PipeJob.job_metadata.graph_context is None`; for `DIRECT` assert it is preserved. (Can test `build_pipe_job_from_input` selection logic without a live Temporal server.)

## Related

- `direct-mode-nested-router-leak.md` — sibling bridge issue (#1); both are about the bridge's contract for DIRECT vs Temporal dispatch.
- `wf_pipe_router.py:80-103` is shared Temporal machinery — changing *it* would affect normal Pipelex Temporal runs; Option A keeps the change confined to the bridge boundary, which is correct.
