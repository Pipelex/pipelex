# Identifier visibility vs. privacy — reflection kickoff

Status: open question, no code touched. This note exists to start a fresh-session reflection. Keep the options open.

## What triggered this

A pipeline run through the API (Temporal path) returned a cost report whose `tokens_usages[]` records carried, per LLM call:

```
job_metadata.pipe_code            = "analyze_cv_job_match"
job_metadata.otel_context.trace_name          = "analyze_cv_job_match_aced9b60"
job_metadata.otel_context.trace_name_redacted = "aced9b60"
job_metadata.trace_context.tracer_key     = "<run_id>/pipe-router"
job_metadata.trace_context.parent_node_id = "<run_id>:<run_id>/pipe-router:node_0"
```

The original question was narrow ("what is `/pipe-router`?"), but it opened a broader one: **which structural identifiers (pipe codes, run ids, user/session ids) are exposed on which surfaces, and is there a single policy that lets us hide them when we need to?**

## ID semantics (so the cold reader isn't guessing)

- **Temporal workflow id is a hierarchical path.** `WfPipeRun` (orchestrator) owns `{run_id}`; it spawns child `WfPipeRouter` with id `{run_id}/pipe-router` (hardcoded suffix, `wf_pipe_run.py:62`). When a controller dispatches a sub-pipe through `TemporalPipeRouter` *inside* a workflow, each sub-pipe becomes its own child workflow with id `{parent}/{pipe_code}-{uuid8}` (`temporal_pipe_router.py:69`).
  - `{pipe_code}` = the literal sub-pipe code. `-{uuid8}` = `str(workflow.uuid4())[:8]`, a replay-deterministic collision-breaker for same-code siblings (e.g. batch). Not ordered, not meaningful.
  - **Inconsistency:** the top pipe's workflow uses a generic `/pipe-router`; nested pipes use their pipe code. The top pipe also has a code that is currently thrown away here.
- **`node_N` is unrelated to pipe codes.** It's `TraceContext.node_sequence` — a monotonic counter minted per workflow tracer (`graph_tracer.py:198` → `{graph_id}:{workflow_id}:node_{seq}`; direct mode `{graph_id}:node_{seq}`, `trace_context.py:64`). The counter **resets per workflow**, so the `{workflow_id}` component is load-bearing: it's the namespace that keeps `node_0` of one workflow distinct from `node_0` of another.

## Core finding: the cost report is an ungoverned exposure surface

`tokens_usages[]` embeds the **entire `JobMetadata`** (`llm_report.py:65-67`, dumped wholesale at `llm_report.py:44`). Nothing redacts it before it leaves the API. The pipe code alone appears up to three ways in one record: `pipe_code`, `otel_context.trace_name`, and (if the workflow id were renamed) `tracer_key`/`parent_node_id`. `user_id` / `session_id` ride along too (`job_metadata.py:41-74`).

The irony: a **redacted twin already exists** — `OtelFactory.make_trace_names` (`otel_factory.py:131`) computes both `{pipe_code}_{hash}` and the pipe-code-free `{hash}`, and both are shipped side by side. The redaction concept the design intended is present and then ignored on this surface.

Consequence for the `/pipe-router` → `/{pipe_code}` rename idea: it improves OSS observability/consistency but **adds a 4th pipe-code leak to the one surface with no redaction control** — wrong direction for hosted privacy. The "uninformative" `/pipe-router` is actually the *safe* default; the informative naming is what should be opt-in.

## Existing knobs — and what each does NOT cover

Several independent subsystems, each scoped to a different sink:

| Subsystem | Config | Governs | Default | Covers cost-report output? |
|---|---|---|---|---|
| Telemetry export redaction | `[telemetry.custom_posthog.tracing.capture]` → `TelemetryRedactionConfig` (`telemetry_config.py:199`); `is_capture_pipe_codes_enabled()` (`telemetry_manager_abstract.py:44`) | pipe codes / content in PostHog/OTEL/Langfuse spans sent to external sinks | redact by default | No |
| Temporal search attributes | `[temporal.search_attributes].enabled` + allowlist (`config_temporal.py:41`) | what's queryable in the Temporal UI | subset | No |
| Temporal static summary/details | none (`observability.py:124-160`) | pipe code + description + user/session + inputs on every workflow | always on | No |
| Graph data inclusion | `graph_config.data_inclusion` (`graph_config.py:6`) | stuff payload content (json/text/html), stack traces, registry in graph events | per-config | governs payloads, not the ids/codes |
| Error disclosure | `disclosure_mode` STRICT/VERBOSE (`base_exceptions.py`) | error-message redaction in `ErrorReport` | — | separate |

**Two surfaces fall through all of them:**

1. The Temporal **workflow-id naming** (`/pipe-router` vs `/{pipe_code}-{uuid}`).
2. The **`JobMetadata` serialized into `tokens_usages`** (and the runner fallback path that derives `workflow_id`/`node_id` from the same context, `reporting_manager.py:263-264`).

## The tension to reconcile

- OSS / self-host users want pipe codes visible — in the report, logs, Temporal UI, for debugging and querying.
- Hosted runner needs the ability to hide structural detail for privacy.

Both are legitimate; the answer is config-driven, not one-size.

## Open decision (do not foreclose)

The system already has the right primitive — a "may pipe codes be shown" boolean — but it only governs telemetry export. A reflection should weigh making structural-identifier visibility a first-class policy that *also* governs (1) workflow-id naming and (2) `JobMetadata`/cost-report serialization, defaulting visible for OSS and redacted for the hosted runner.

Candidate homes for that policy — left open:

- **(a)** Extend/reuse the telemetry `capture.pipe_codes` flag so one switch covers telemetry *and* run output.
- **(b)** New knob alongside `data_inclusion` on `graph_config` / `tracing_config` (the cost report rides the same trace substrate).
- **(c)** Derive from the existing `data_inclusion` family.

Each has different blast radius and different "single source of truth" implications. Also unresolved: whether redaction should happen at serialization time (strip fields from `JobMetadata` before it reaches `tokens_usages`) or at id-construction time (never bake codes into workflow ids in the first place) — or both, since they protect different sinks.

## Anchor points for a cold start

- Workflow-id naming: `wf_pipe_run.py:62`, `temporal_pipe_router.py:69`
- Node id minting: `graph_tracer.py:198`, `trace_context.py:48,64`
- Cost-report exposure: `llm_report.py:44,65-67`, `job_metadata.py:41-74`
- Redacted-twin generator: `otel_factory.py:131`
- Telemetry redaction policy: `telemetry_config.py:199`, `telemetry_manager_abstract.py:44`
- Other sinks: `config_temporal.py:41` (search attrs), `observability.py:124-160` (static summary/details, ungated), `graph_config.py:6` (data inclusion)
