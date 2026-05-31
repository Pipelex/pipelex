# Runtime code fixes

Concrete fixes verified against the code, not yet done. Each is independent.

## `request_id` on delivery failure messages

Append the already-in-scope `request_id_suffix` to the `StorageDeliveryError` failure message and to both `WebhookDeliveryError` branches in `pipelex/pipe_run/delivery_executor.py`, mirroring the success paths; add unit assertions that the messages carry `request_id=`. Full analysis — exact sites, the case for/against, and a sketch commit — is in [`error-handling/track-delivery-error-path-request-id.md`](error-handling/track-delivery-error-path-request-id.md).

## Cross-worker cost report assembly wiring

The single genuine functional gap from the tracing work: wire `UsageAggregator.aggregate(events)` → `ReportingManager.inject_tokens_usages(...)` → `generate_report` into the post-run readback, parallel to the existing graph readback, for both direct mode (`pipe_run/pipe_run.py` / `graph_assembly.py`) and Temporal (`act_assemble_graph` / post-workflow), with a cross-worker test. Tracked as P1 in [the distributed-execution plan](distributed-execution/README.md); the as-built context and the open T2/T3 gaps are in [`distributed-execution/tracing-cost-reporting.md`](distributed-execution/tracing-cost-reporting.md).

## Deferred / out of scope

Surfaced alongside the two fixes but out of scope for them:

- GraphSpec causal ordering for parent/child topologies (observability-only).
- kajson class-registry race under pytest-xdist (test-hygiene; needs runtime repro).
- `get_config()` replay-determinism — the cheap parts (a `docs/distributed-execution` note on the config-edit-while-in-flight constraint, plus a Replayer regression test) are file-able; the full fix is Worker Versioning.
