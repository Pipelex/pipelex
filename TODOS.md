# PipeSearch has no Temporal activity — search pipes hang the runner API

**Status:** confirmed by code inspection, not yet fixed. No code changed.
**Severity:** high — any MTHDS bundle with a `PipeSearch` step, run through the Temporal path, hangs the caller forever instead of returning (or failing). On the happy path it is also unsound (non-deterministic on replay — see below).
**Discovered from:** `pipelex-api` running locally against a local `pipelex-worker` + `temporal server start-dev`, all three on the same local `pipelex` checkout. Repro bundle: `pipelex-demos/mthds-wip/fashion_moodboard` (has a search step). Control bundle that works: `pipelex-demos/mthds-wip/joke_judge` (LLM only).

## Where this brief lives vs. where the fix happens

This brief is written in `pipelex-api/wip/` because that's where the symptom surfaced, but **the entire fix is in the `pipelex` repo** (the open-source runtime). The next session is expected to run from a `pipelex` worktree.

**Path convention for the next session:** every `pipelex/...` path below is relative to the **pipelex repo root**. You are in a worktree, so that root is your worktree root — use the paths as-is. Do **not** reach into a sibling `../pipelex/` checkout; work entirely inside your worktree. (Per workspace `CLAUDE.md`, dirs starting with `_` are pipelex worktrees; treat the worktree as the root.)

Nothing in `pipelex-api` needs to change for this bug. The API just calls `runner.execute_pipeline(...)`; the runner dispatches to Temporal; the gap is entirely on the worker/workflow side in `pipelex`.

## Symptom

Running a bundle whose pipe includes a web-search step against the API (sync `POST /api/v1/pipeline/execute`, which goes through Temporal because `temporal.is_enabled = true` in the local config) **never returns**. The HTTP request hangs. The worker logs show the underlying error repeating, e.g.:

```
SearchJobFailureError: gateway inference failed for model 'linkup-standard →
SDK[gateway_search]•Backend[pipelex_gateway]•Model[linkup/standard]': Connection error.
```

The connection error itself is incidental (local Linkup creds/network). The bug is that **this error — or any search outcome — never crosses the Temporal boundary back to the submitter**, so all the error-handling work in `pipelex/wip/error-handling/` (RFC 7807 problem responses, `ErrorReport` parity, submitter-side report recovery) never gets a chance to run. The same call run with Temporal *disabled* would surface the error correctly as an RFC 7807 response (direct path: `SearchJobFailureError` → propagates → `PipelineExecutionError` → API global handler).

## Root cause

**`PipeSearch` is the only inference operator that does not route its leaf call through the swappable `ContentGenerator` abstraction, and there is no `act_search` Temporal activity.**

Every other inference operator calls `get_content_generator()` and invokes a `make_*` method on it:

| Operator dir | uses `get_content_generator()` | calls a `*WorkerFactory` directly |
|---|---|---|
| `llm` | yes | no |
| `img_gen` | yes | no |
| `extract` | yes | no |
| `compose` | yes | no |
| `structure` | yes | no |
| **`search`** | **no** | **yes** |

When `temporal.is_enabled`, `Pipelex.make()` sets the hub's content generator to `ContentGeneratorInWorkflow` (`pipelex/pipelex.py:373-385`). That class implements every `make_*` method as `await workflow.execute_activity(act_*)` (`pipelex/temporal/tprl_content_generation/content_generator_in_workflow.py`). So inside the workflow, an LLM/img/extract leaf automatically becomes an activity. The activity is wrapped with `@convert_pipelex_errors` (`pipelex/temporal/tprl/activity_error_boundary.py`), which converts any `PipelexError` into `TemporalError(ApplicationError)`.

`PipeSearch._live_run_operator_pipe` (`pipelex/pipe_operators/search/pipe_search.py:78-165`) does **none** of that. It builds a worker directly via `SearchWorkerFactory.make_search_worker(...)` and calls `worker.search_sourced_answer(...)` / `worker.search_structured(...)` **inline** (lines 122, 138, 141). There is no `make_search*` on the `ContentGenerator` protocol (`pipelex/cogt/content_generation/content_generator_protocol.py`), and `grep -rn act_search` across the repo returns nothing — **the activity was never created.** Search was added long after the other operators (per the repo owner) and this wiring step was missed.

Because `pipe.run_pipe(...)` executes *inside* the workflow (`pipelex/temporal/tprl_pipe/wf_pipe_router.py:139`), the search worker's real HTTP call runs **inside the workflow event loop** — which is only not-immediately-rejected because the worker is started with `--no-sandbox`.

## Exact mechanism of the hang

Temporal distinguishes two failure kinds raised from workflow code:

- **Workflow execution failure (terminal):** raised when the exception is an `ApplicationError`/`FailureError`, or a type listed in the worker's `workflow_failure_exception_types`. The workflow ends; the failure is returned to the submitter.
- **Workflow task failure (non-terminal):** any *other* exception. Temporal assumes it's a transient/code bug and **retries the workflow task indefinitely**. The workflow never ends; the submitter waits forever.

The pipelex worker registers `workflow_failure_exception_types=[WorkflowExecutionError]` (`pipelex/temporal/temporal_task_manager.py:148`). So:

- **LLM leaf (works):** activity raises `TemporalError(ApplicationError)`; on the workflow side `ContentGeneratorInWorkflow` / `WfPipeRouter`'s `except ActivityError` re-raises `TemporalError.from_app_error(...)` (an `ApplicationError`). `ApplicationError` always fails the workflow terminally → propagates to the API → RFC 7807. ✅
- **Search leaf (hangs):** raises a raw `SearchJobFailureError` (a `CogtError`/`PipelexError`, **not** an `ApplicationError`, **not** a `WorkflowExecutionError`). It is not caught by `WfPipeRouter`'s only handler (`except ActivityError`, `wf_pipe_router.py:146` — a `SearchJobFailureError` is not an `ActivityError`). It propagates out of the workflow as an unclassified exception → **workflow task failure → infinite workflow-task retry → submitter hangs.** The worker log line repeats once per retry. ❌

That is the full chain that produces "errors but they are not returned by the API, it all just hangs."

## The happy path is also unsound (not just the error path)

Even when the search call *succeeds*, running it inline in the workflow is the classic "side effect inside a workflow" anti-pattern:

- The result is **not recorded in workflow history** (no activity = no recorded result). On any replay — worker restart, a later workflow task, cache eviction — Temporal re-executes the workflow code and **re-runs the real search** (extra provider spend, different results) or trips a non-determinism check.
- Real network I/O on the deterministic workflow loop is unsupported in general; `--no-sandbox` only removes the import/static sandbox, not the determinism contract.

So "add the missing activity" is a correctness fix for search-on-Temporal as a whole; the hang is merely its most visible symptom.

## The fix (mirror the established LLM pattern)

The clean fix makes search a first-class, swappable content-generation operation exactly like LLM/img/extract. All paths in `pipelex`:

1. **Framework-agnostic activity core.** Add a `search_generate.py` under `pipelex/cogt/content_generation/` (sibling of `llm_generate.py`) with async functions that take a serializable assignment and call the search worker — e.g. `search_gen_sourced_answer(search_assignment)` and `search_gen_structured(search_assignment)`. Internally they do what `pipe_search.py:122-141` does today (resolve `inference_model` → `SearchWorkerFactory.make_search_worker` → `worker.search_*`).

2. **Serializable assignment model.** Add a `SearchAssignment` next to `LLMAssignment`/`ObjectAssignment` (`pipelex/cogt/content_generation/assignment_models.py`) carrying `job_metadata`, the rendered `query`, the resolved `SearchSetting`/model handle, and the `include_domains`/`exclude_domains`/`from_date`/`to_date` overrides. Confirm it round-trips through the Temporal payload codec (`SearchJob`, `SearchSetting` already look serializable — verify).

3. **Activity.** Add `pipelex/temporal/tprl_content_generation/act_search_generate.py` with `act_search_*` functions decorated `@activity.defn` + `@convert_pipelex_errors` (copy `act_llm_generate.py` verbatim as the template). This is what converts `SearchJobFailureError` → `TemporalError(ApplicationError)` so it fails the workflow terminally and surfaces.

4. **Register the activity.** Add the new activities to `Tasks.TASK_PACKS[PackName.CRAFTING].activity_list` (`pipelex/temporal/tasks.py:24-35`) and to the worker-scope `required_activities` / `crafting` pack in the config TOMLs (`pipelex/pipelex.toml` + `.pipelex/pipelex.toml` + `pipelex/kit/configs/pipelex.toml` — grep `act_llm_gen_text` to find every list that enumerates activities and add the search ones alongside).

5. **Protocol + all three implementations.** Add `make_search*` to `ContentGeneratorProtocol` (`content_generator_protocol.py`), then implement in:
   - `ContentGenerator` (direct, `content_generator.py`) — call the core inline.
   - `ContentGeneratorInWorkflow` (`content_generator_in_workflow.py`) — `await workflow.execute_activity(act_search_*, arg=search_assignment, **resolve_dispatch(...).to_execute_kwargs())`, with the same `except ActivityError → from_app_error` block as `make_llm_text` (lines 115-126). Use `worker_config.resolve_dispatch(activity_name=act_search_*.__name__, routing_key=<search handle>, ...)` for queue/timeout/retry.
   - `ContentGeneratorDry` (`content_generator_dry.py`) — return the dry-run mock currently built in `PipeSearch._dry_run_operator_pipe` (lines 167-204), so the dry-run mock moves behind the same seam.

6. **Rewrite `PipeSearch._live_run_operator_pipe`** to call `content_generator = get_content_generator()` then `await content_generator.make_search*(...)` instead of building the worker directly. Keep prompt rendering (step 1, lines 97-102) and model/setting resolution (steps 2-4, lines 104-119) where they are, *or* push them into the core — your call, but match how `PipeLLM` splits "resolve setting in the operator" vs "run leaf in the generator".

**Structured-search tip for crossing the boundary:** `search_structured` returns a `result_dict` that `PipeSearch` then `model_validate`s into the output structure class (`pipe_search.py:141-142`). Have the activity return the **raw dict** and do `output_structure_class.model_validate(result_dict)` on the submitter side *after* the activity returns (it's pure and deterministic). That sidesteps having to ship a dynamic output class across the Temporal boundary — simpler than the `ObjectAssignment`/library-crate machinery the object activities use. `search_sourced_answer` returns a `SearchResultContent` (a `StuffContent` `BaseModel`) which is directly serializable.

**Optional hardening:** add a loud guard so a search leaf can never again silently run inline in a workflow — e.g. in the search path, if `workflow.in_workflow()` is true and the call did not go through an activity, raise a clear `PipelexError`. Cheap insurance against the next operator that forgets this wiring.

## How to reproduce

Pipelex-native (no `pipelex-api` needed), from your worktree:
1. Ensure `temporal.is_enabled = true` and a local Temporal dev server is up (`temporal server start-dev`).
2. Start a worker against your worktree: `pipelex worker --no-sandbox` (the `crafting` + `pipe` packs).
3. Run any bundle with a `PipeSearch` step through the Temporal path (a search pipe; `fashion_moodboard` from `pipelex-demos/mthds-wip/` is the known one). Either force a search failure (bad/empty Linkup creds → "Connection error") **or** let it succeed and then kill+restart the worker mid-run to trigger replay.
4. Observe: the workflow never completes; the Temporal UI shows the workflow stuck with a repeating **workflow-task failure** (not a workflow execution failure), and the worker logs print the search error once per retry.

Original repro that found it (in `pipelex-api`, for reference only): `make bundle-run BUNDLE=/Users/lchoquel/repos/Pipelex/pipelex-demos/mthds-wip/fashion_moodboard` with the API + worker + temporal all running — the command hangs.

## How to verify the fix

- The same search-failure run now **returns** a classified error: the workflow fails terminally (workflow *execution* failure, visible in Temporal UI), and the submitter gets a `PipelineExecutionError` whose `to_error_report()` carries the search `error_category`/`model`/`provider` — same data as the identical run on the direct (non-Temporal) path. Through the API that becomes an RFC 7807 `application/problem+json` response instead of a hang.
- A *successful* search now shows an `act_search_*` activity in the workflow history (result recorded → replay-safe).
- Add a parity test mirroring the existing pair (`tests/integration/pipelex/temporal/test_workflow_error_report_full_chain.py` ↔ `tests/integration/pipelex/error_handling/test_error_report_local_full_chain.py`) but for a search pipe, asserting identical `ErrorReport` local vs Temporal.

## Reference file map (all relative to pipelex repo root / your worktree root)

- Bug site: `pipelex/pipe_operators/search/pipe_search.py` (`_live_run_operator_pipe` lines 78-165; dry-run lines 167-204)
- Pattern to copy — activity: `pipelex/temporal/tprl_content_generation/act_llm_generate.py`
- Pattern to copy — in-workflow dispatch: `pipelex/temporal/tprl_content_generation/content_generator_in_workflow.py:94-128` (`make_llm_text`)
- Protocol to extend: `pipelex/cogt/content_generation/content_generator_protocol.py`
- Direct impl: `pipelex/cogt/content_generation/content_generator.py`; dry impl: `content_generator_dry.py`
- Assignment models: `pipelex/cogt/content_generation/assignment_models.py`
- Activity error boundary: `pipelex/temporal/tprl/activity_error_boundary.py` (`convert_pipelex_errors`)
- Activity registration: `pipelex/temporal/tasks.py`
- Worker `workflow_failure_exception_types`: `pipelex/temporal/temporal_task_manager.py:148`
- Workflow that runs the pipe inline and only catches `ActivityError`: `pipelex/temporal/tprl_pipe/wf_pipe_router.py:139,146`
- Content-generator selection at make: `pipelex/pipelex.py:370-385`
- Retry/timeout config (bounded: `maximum_attempts = 3`, `workflow_execution_timeout = 1h`): `pipelex/pipelex.toml` (temporal section ~line 489) — confirms the hang is *workflow-task* retry (unbounded), not activity retry (bounded)
- Search worker/error types: `pipelex/cogt/search/search_worker_*.py`, `pipelex/plugins/{linkup,gateway}/*search*.py`, `SearchJobFailureError` in `pipelex/cogt/exceptions.py:376` (a `CogtError` → `PipelexError`)
- Background on the error-handling design this restores parity with: `pipelex/wip/error-handling/` (esp. `track-temporal-integration.md`, `track-retry-and-resilience.md`)
