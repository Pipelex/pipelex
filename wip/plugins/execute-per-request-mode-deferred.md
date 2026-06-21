# Deferred / flagged items — `/execute` honors per-request `execution_mode`

Companion to `execute-per-request-execution-mode.md` (the plan). Captures findings surfaced while implementing **Phase E0** that were deliberately **not** acted on, plus pre-existing drift that the implementation absorbed. None block the feature.

## 1. DIRECT dispatch does a serialize→rehydrate round-trip (accepted tradeoff, not a bug)

`/execute` now dispatches every mode — including `direct` — through the `OrchestratorRegistry`. The orchestrator answers with the JSON-safe `PipelexPipeRunOutput` (the same shape that crosses the Temporal worker boundary, via `serialize_completed_output`), so the synchronous `/execute` path rehydrates it back into a rich `PipeOutput` (`_pipe_output_from_run_output` in `api/routes/pipelex/pipeline.py`). For `direct` this means the working memory is `dump_for_temporal()`'d and then `hydrate_working_memory()`'d **in-process** — one redundant re-serialization the old boot-slot path didn't pay.

**Why accepted:** it keeps `/execute` on the *same* per-call dispatch seam as `/start` and `/validate` (no per-mode branch), which is the whole point of the locked decision. The cost is bounded (one extra round-trip of a working memory that `/execute` already serializes once for the HTTP response).

**If it ever matters:** the clean fix is at the *contract* layer, not here — e.g. let `OrchestratorProtocol.run` optionally hand back the rich `PipeOutput` for the in-process arm so the DIRECT path skips the round-trip. That's a core (`pipelex`) change to a shared SPI, out of scope for this single-repo plan. Don't special-case DIRECT inside `pipelex-api` (that reintroduces the per-mode branch the seam removed).

## 2. `graph_spec` / `tokens_usages` reconstruction needs `strict=False` (correct, worth knowing)

`serialize_completed_output` dumps `graph_spec` / `tokens_usages` with `model_dump(mode="json")`, and those models are `strict=True` (e.g. `GraphSpec.created_at: datetime`). A strict re-validation of the JSON dump fails (str→datetime is rejected in strict mode — confirmed empirically). `_pipe_output_from_run_output` therefore validates with `strict=False`, which is the correct tool for reversing our *own* trusted JSON dump (a round-trip, not untrusted ingest). Nothing else in the tree rehydrates these dump fields today, so there was no prior precedent to copy — flagged here so a future reader doesn't "tighten" it back to strict.

## 3. Pre-existing `/start` DIRECT-path resource leak (flagged, NOT fixed — out of scope)

While mirroring `start`, noticed that `ApiRunner.start` calls `pipeline_run_setup(...)` then the orchestrator, with **no** teardown on the success path. `pipeline_run_setup` only tears the run library / pipeline-manager entry down on its *error* path; `PipeRun.run` closes the tracer but not the library or the pipeline-manager registration. The base `PipelexMTHDSProtocol.execute` does that teardown in its `finally`. So on the **DIRECT** `/start` success path (reachable on the agnostic base, where `start` runs in-process and blocks), the run library and its pipeline-manager entry appear to leak per request.

`/execute` does **not** have this problem: this change delegates to the base `execute`, inheriting its full teardown. The finding is purely about `/start`.

**Not fixed here** because it touches `/start` (a different surface) and the plan is scoped to `/execute`. Worth a small follow-up: give `ApiRunner.start` the same lifecycle guarantees (or factor the base `execute`'s setup+teardown into a shared context manager both `execute` and `start` use). Verify first that it is a genuine leak and not cleaned up elsewhere before changing `/start`.

## 4. Absorbed pre-existing drift from the `/validate` work (informational)

The committed `docs/openapi/pipelex-api.openapi.yaml` and `docs/configuration.md` at the validate tip (`72c0efc`) were **stale** w.r.t. the `/validate`-by-`execution_mode` work: the OpenAPI artifact lacked the `PipelexExecutionMode` component + the validate request's `execution_mode` field, and `configuration.md` still said `/validate` "always runs in-process and ignores this setting." Both are regenerated/corrected in this change (the OpenAPI artifact is generated, so it must match the current app exactly; the config doc was rewritten holistically for `/execute` + `/start` + `/validate`). Mentioned so the diff's validate-flavored hunks aren't mistaken for execute-scope creep — they are pre-existing drift this change necessarily resolves.

## 5. Reverse helper location — altitude (independent review, deferred)

`_pipe_output_from_run_output` is the exact inverse of `serialize_completed_output` (which lives in `pipelex/runtime_bridge/serialization.py`), but the reverse currently lives as a private function in the `pipelex-api` route module. If `PipelexPipeRunOutput` gains/renames a field, forward (pipelex) and reverse (pipelex-api) could drift independently. **Deferred:** single consumer; moving it crosses a repo boundary; and the reverse must run *inside* the still-open run-library scope (a precondition naturally satisfied at this call site). Confirmed no existing reverse helper is being reinvented (`rehydrate_pipe_output_with_crate` operates on a `PipeOutput.working_memory_raw`, not a `PipelexPipeRunOutput`; the new helper correctly reuses `hydrate_working_memory`). Promote to a `deserialize_completed_output` in `serialization.py` only if `pipelex-temporal`'s blocking path ever needs the same reverse.

## 6. OpenAPI request schema doesn't advertise the `execution_mode` body extra — pre-existing (independent review, flagged)

`/execute` and `/start` document the per-request `execution_mode` override in prose, but their generated OpenAPI request schemas (`RunRequest` / `PipelexApiStartRequest` `model_json_schema()`) don't list `execution_mode` — it's parsed from the raw kajson body as a `PipelineApiExtras` extra. Only `/validate` surfaces it (it uses a typed request model). A client generating from the spec can't discover the field on `/execute`/`/start`. **Deferred:** pre-existing (`/start` already had the gap; this change merely widens it to a third endpoint), `openapi-check` passes (the artifact is internally consistent), and reconciling it is a cross-endpoint decision about how extras are advertised — out of scope here. If reconciled, regenerate via `make openapi-export` (never hand-edit the yaml).

## 7. `is_completed` invariant the synchronous path relies on (independent review, rejected-as-fix)

`_pipe_output_from_run_output` unconditionally builds a completed `PipeOutput` without checking `run_output.is_completed`. **Rejected as a fix** (not a bug): `/execute` refuses fire-and-forget upfront with a 400, and every non-f&f orchestrator today (`DirectOrchestrator`, `TemporalBlockingOrchestrator`) returns `is_completed=True`, so a `False` here is unreachable — guarding it is a defensive check for an impossible-today scenario. Recorded only so a future orchestrator author knows the invariant the synchronous path assumes.

### Minor (independent review, no action)

- `_validate_extras` reports a malformed `execution_mode` value under `error_type=INVALID_CALLBACK_URLS` (still a correct 422 with the real pydantic detail in the message) — pre-existing label imprecision surfaced only because `execution_mode` joined that model; cosmetic.
- The base `execute`'s `if extra:` rejection is unreachable via the API `execute` override (the override omits `extra`; the route never passes it) — dead-but-harmless, identical to how `start()` already works.
