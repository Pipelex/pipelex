---
status: active
item: L-260922-75299c
---

# Deferred review findings — run-scoped telemetry identity

Findings from the round-1 `/rev` pass (profile 4, bar `open`) that were real but did not meet the bar, kept here so nothing is dropped without somewhere to chase it.

## One capture helper instead of the hand-rolled branches

Raised by cubic. **Unverified** — it sorted to deferral before the verifier ran, so it rests on cubic's reading alone.

The identified-versus-anonymous capture shape is written out by hand at several sites: `_capture_custom_event` and `_track_to_pipelex` in `pipelex/system/telemetry/telemetry_manager.py`, both branches of `handle_trace_start` in the same file, and `_capture_event` in `pipelex/system/telemetry/posthog_span_exporter.py`. Each one reads "if the identity has a `distinct_id`, capture with it and with `groups or None`; otherwise stamp `$process_person_profile = False`".

cubic's argument for folding them into one `capture_under_identity(client, event, properties, identity)` is that the two streams cannot then drift apart again, and that the anonymous-mode defect this round fixed would have been a one-line change. That argument held: the fix did have to be made once in `_resolve` and then checked at every one of those sites.

It was deferred because it is a structural refactor rather than a defect, and because `RunIdentityPolicy` now concentrates the part that was actually drifting — which of the two branches a stream takes — in one place. The remaining duplication is the mechanical capture call, which is the cheaper half to keep in step. Worth doing when that file is next opened for another reason.

## Stale docstrings in two test modules outside the diff

Raised by cubic, which flagged them itself as naming files the reviewed change does not touch. **Unverified.**

`tests/integration/pipelex/pipeline/test_pipeline_run_setup_analytics_groups.py` and `tests/integration/pipelex/pipeline/test_pipeline_run_setup_storage_scope_gate.py` carry docstrings describing an ordering that a later change moved: claims that no exporter reads the groups yet, and that the gate sits above `handle_trace_start`. If the ordering did move, a test whose docstring explains why it would fail if the gate were moved back no longer fails in that case, which makes the docstring worse than absent.

Deferred because the files are outside this branch's diff and the claim was not verified. Whoever next touches those modules should read the two docstrings against the current ordering.
