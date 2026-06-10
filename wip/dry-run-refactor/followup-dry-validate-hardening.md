# Follow-up: operational hardening of the dry-validate activity path

Deferred items from the post-implementation review of `feature/Dry-run-as-temporal-activity` (Part C, `act_dry_validate` + `wf_dry_validate` + `dispatch_dry_validate`). Each was verified against the code at review time; none blocks shipping — they are design tradeoffs or pre-existing shapes that deserve a deliberate pass, not a reflexive patch. Cheap fixes from the same review (teardown suppress-secondary, `workflow_execution_timeout=12min`, close-contract docs, tracer-open ordering, graph-arm parity, dropping `library_dirs`) were applied on the branch and are NOT listed here.

## 1. No heartbeat: a hung validation cannot be cancelled and outlives its timeout

`act_dry_validate` never calls `activity.heartbeat()` and `WfDryValidate` sets no `heartbeat_timeout`. In the Temporal Python SDK, cancellation is only delivered to an async activity through heartbeating — so when the 5-minute `start_to_close_timeout` fires, the *workflow* gives up but the worker coroutine keeps running to completion: the activity slot, the loaded library, and the `GraphTracerManager` entry are held until the run finishes on its own (or forever, if a pathological bundle spins), and the retry attempt starts a second copy of the same work on top. Validation input is user-authored pipe graphs; with recursive design in flight, whether a cyclic controller graph can spin indefinitely in DRY mode needs confirmation.

**Direction:** periodic `activity.heartbeat()` pulses (between the sweep and the graph arm, and inside `BundleValidator.validate_pipes`' per-pipe loop) + a `heartbeat_timeout` on the `execute_activity` call. Alternatively wrap the body in `asyncio.wait_for` matched to `start_to_close`.

## 2. CPU-bound activity body on the worker event loop

The activity body is almost entirely CPU work (TOML interpretation, pydantic construction, polyfactory mock minting, DRY sweep + graph trace) with essentially no real awaits — `validate_bundle` yields exactly once (`await asyncio.sleep(0)`). On a worker that co-hosts inference activities, a large bundle blocks the event loop for long stretches: co-resident activities' heartbeat/start-to-close timers keep ticking, risking spurious timeouts that re-run real, billed LLM calls.

**Direction:** run the validation core off the loop (`asyncio.to_thread`, or a sync `@activity.defn` using the worker's activity executor), or at minimum add a per-pipe `await asyncio.sleep(0)` in the sweep loop. Interacts with item 1 (heartbeats need the loop free to fire).

## 3. Validation verdict depends on worker-side config (drift surface)

`BundleValidator._aggregate` reads `dry_run_config.allowed_to_fail_pipes` and `dry_run_pipe_in_process` reads `pipeline_execution_config` / `graph_config.data_inclusion` from the process-local config. Direct mode resolves these from `pipelex-api-deploy`'s `.pipelex` toml; Temporal mode from `pipelex-worker`'s separately-pinned one. Config drift between the two deploy repos silently changes which pipes are allowed to fail (same bundle passes on one backend, 422s on the other) and how much data the returned `GraphSpec` carries.

**Direction:** either carry the decision-affecting knobs in `DryValidateArg` so the submitter's config is authoritative, or declare worker config the single source of truth for `/validate` and add a deploy-time drift check between the two repos' configs.

## 4. The main pipe is dry-run twice per /validate

The sweep dry-runs every sweepable pipe (untraced, `generate_graph=False`), then `dry_run_pipe_in_process` re-runs the main pipe's whole subtree to capture the `GraphSpec`. Inherited from the direct-mode shape (sweep and graph were always two runs), but now that both arms share one process and one library, a single traced run of the main pipe could feed both its `DryRunOutput` classification and the graph.

**Direction:** fold with the existing D-plan §7 endpoint-unification follow-up; exclude the main pipe from the untraced sweep loop and derive its classification from the traced run.

## 5. `LibraryManager._pipe_source_map` is process-global, keyed by bare `pipe_ref` (pre-existing)

One dict for all libraries: load overwrites entries, teardown pops by `pipe_ref` regardless of owner. Two concurrent `act_dry_validate` invocations whose bundles share a `pipe_ref` overwrite each other's entries, and the first teardown deletes the survivor's. Consumers are currently low-stakes (`get_pipe_source` → `which` CLI), but this feature makes concurrent multi-library validation the norm on workers.

**Direction:** scope the map per-library (key by `(library_id, pipe_ref)` or move it onto `Library`).

## 6. No selected-pipe validation field on the wire

`validate_bundle` supports `dry_run_pipe_codes` (used by `validate_pipe_in_bundle` for builder flows that validate one implemented pipe while siblings may fail); `DryValidateArg` doesn't carry it, so the Temporal path can't preserve that behavior if the API ever exposes pipe selection. Not needed today — the API validates whole bundles — but it's the first field to add when the builder flows move server-side.

## 7. Per-queue dispatch tuning doesn't reach `act_dry_validate`

`WfDryValidate` hardcodes `start_to_close_timeout=5min` / `maximum_attempts=2` in workflow code (per D-C5, precedented by `WfPipeRun`'s own hardcoded utility-activity bounds), so the v2 `resolve_dispatch` overlays (`queue_options`, per-handle options) cannot tune the validation activity. Fine while one bound fits all deployments; revisit if a deployment needs a larger validation budget (big bundles WILL hit the 5-minute cap — see item 1 for what happens then).

## 8. Payload-converter exceptions in workflow tasks hang the submitter (retry-forever), and aware datetimes were the live trigger

Root-caused 2026-06-10 (CI py3.11–3.14 hang on the three GraphSpec-crossing tests): an exception raised by the data converter while decoding an activity result fails the *workflow task*, which Temporal retries indefinitely — the submitter's `execute_workflow` never returns. The trigger was environmental (`ZoneInfoNotFoundError`: no IANA tzdata on the runner for py3.11+; fixed by making `tzdata` a direct dependency), but the failure *shape* is general: any deterministic decode bug (kajson registry miss, schema drift, future enum rename) will present as an infinite hang on every host, not a failed run. `dispatch_dry_validate`'s 12-minute `workflow_execution_timeout` bounds the API path; direct `execute_workflow` callers (tests, scripts) have no bound.

**Direction (design tradeoff, do not reflexively patch):** consider making deterministic conversion errors fail-fast — e.g. catch `KajsonDecoderError` in `BaseModelPayloadConverter.from_payload` and re-raise as a non-retryable shape, or document that every submitter must set `workflow_execution_timeout`. Temporal's retry-forever default exists so a code redeploy can heal a bad task; trading that away deserves a deliberate decision.
