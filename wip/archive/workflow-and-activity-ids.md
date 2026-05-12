# Workflow and Activity IDs in Temporal: Correctness + Observability

## Status

Problem statement + failing test gate in place. No solution designed yet — the next session must explore Temporal's primitives (`workflow.uuid4()`, `workflow.info()`, search attributes, activity summaries, workflow-local counters, child-workflow id derivation, etc.) and design the right model. The gate test (see below) must turn green as the result of that work, without weakening the assertions.

## The trigger: activity-id collision in `ContentGeneratorInWorkflow`

File: `pipelex/temporal/tprl_content_generation/content_generator_in_workflow.py`

Every method that dispatches an activity computes `activity_id` like this:

```python
activity_id = wfid or "craft-text"
self._record_activity_id(activity_id, "make_llm_text")
```

The defaults are operation-type labels: `"craft-text"`, `"craft-object-direct"`, `"craft-object-list-direct"`, `"craft-image-single"`, `"craft-image-list"`, `"jinja2-text"`, `"render-page-views"`, `"extract-pages"`, `"extract-render-page-views"`.

### The bug

Temporal requires `activity_id` to be unique within a single workflow execution (i.e. per `(workflow_id, run_id)`). The defaults above are constants. A workflow that calls `make_llm_text` twice in a row uses `activity_id="craft-text"` both times and crashes — at the second call — with a duplicate-id error. Two calls to the same generator method inside one workflow is a perfectly ordinary pattern; the current design treats it as an error.

### What the LRU / `_record_activity_id` actually does

The `_seen_activity_ids: OrderedDict[tuple[str, str], set[str]]` machinery in lines 48-109 is **not** a fix. It's a polite-failure wrapper: it lets the collision raise as a clean `ContentGenerationError` ("Duplicate activity_id … pass a distinct `wfid` at the call site") instead of an opaque Temporal SDK error. All the surrounding complexity (LRU bound, `(workflow_id, run_id)` keying, `is_replaying()` short-circuit) exists only because the set lives on a long-lived **worker-singleton** instance (`ContentGeneratorInWorkflow` is instantiated once in `pipelex.py:347` and reused across every workflow run on that worker).

The LRU is solving the wrong problem. The structural bug is upstream: the default `activity_id` is a constant string in a context that requires a per-call unique value.

### Why `wfid` doesn't actually save us

`wfid` is **the workflow-id parameter**, not an activity-id parameter. Everywhere else in the codebase it's used as the base for a workflow id:

- `temporal_pipe_run.py:63, 95` — `workflow_id=self.make_workflow_id(base_id=wfid or self.class_name)`
- `temporal_pipe_router.py:84` — same
- `temporal_pipe_router.py:60` — `child_unique_id = wfid or str(workflow.uuid4())`
- threaded through `pipe_run.py`, `pipe_run_protocol.py`, `pipe_router_protocol.py`

In `content_generator_in_workflow.py`, the same parameter is being co-opted as an `activity_id`. This is a legacy artifact: in an earlier prototype the content generator **spawned workflows** for each operation, so a single `wfid` per call made sense. We later changed it to spawn **activities** instead, but the parameter — and the assumption that one id per call is enough — was carried over unchanged. A single `wfid` value cannot disambiguate ten `make_llm_text` calls inside one workflow.

## TDD entry point — DONE

The failing test is in place at `tests/unit/pipelex/temporal/test_default_activity_id_collision_bug.py` (class `TestDefaultActivityIdCollisionBug`). It pins both scenarios:

- `test_two_make_llm_text_calls_without_wfid_should_succeed` — two `make_llm_text` calls in the same workflow with no `wfid` passed. Today both default to `activity_id="craft-text"` and the second call raises `ContentGenerationError("Duplicate activity_id 'craft-text' for method 'make_llm_text' ...")` from `_record_activity_id`. The test asserts the desired behavior (two distinct activity_ids, both calls succeed) and therefore fails today.
- `test_two_make_llm_text_calls_with_same_explicit_wfid_should_succeed` — two `make_llm_text` calls with the same explicit `wfid="same-string"`. Today this raises the same way, proving `wfid` cannot serve as the per-call disambiguator. The test asserts the desired behavior (the redesign decouples per-call `activity_id` from the `wfid` parameter) and fails today for the same reason.

### Why unit, not integration

The original sketch suggested `tests/integration/pipelex/temporal/` "so it runs against a real-ish workflow context where `workflow.execute_activity` is callable." On inspection the unit-test layer already mocks `workflow.info()`, `workflow.unsafe.is_replaying()`, and `workflow.execute_activity()` cleanly (see the pattern in `tests/unit/pipelex/temporal/test_content_generator_in_workflow.py`), and the bug fires synchronously in `_record_activity_id` *before* `execute_activity` is awaited. A unit test pins the wrapper-layer bug exactly where it lives — no LLM, no worker, no Temporal server — and runs in well under a second. An integration test could be added later if the redesign introduces workflow-primitive behavior (e.g. `workflow.uuid4()` determinism across replay) that is worth exercising end-to-end, but it is not required to gate the design.

### Gate semantics

The two tests assert the **desired** behavior (both calls succeed and produce distinct activity_ids). They are red today. Any redesign must turn them green without re-introducing the duplicate-collision via some other path. Do not delete or weaken these tests as part of the fix — flip the implementation, not the assertions.

## Step back: this is bigger than one bug

The activity-id bug is the local symptom. The deeper issue is that **we do not have a designed naming system for the Temporal primitives we run** — neither for workflows nor for activities. What we have today are two legacy schemes glued together:

### Legacy artifact 1: `wfid`

`wfid` was introduced when content generation was implemented as **spawned workflows**. One workflow per `make_*` call → one `wfid` per call → fine. When we switched content generation to **activities** inside the current workflow, the `wfid` parameter survived but its purpose became muddled. It is now simultaneously:

- The base for parent/child **workflow** ids (in `tprl_pipe/*`).
- The **activity_id** itself (in `tprl_content_generation/content_generator_in_workflow.py`).

These are two different Temporal primitives with different uniqueness scopes. Conflating them under one parameter name is the root cause of the collision bug.

### Legacy artifact 2: workflow-id construction

`temporal_manager.py:95-110` builds top-level workflow ids as:

```python
return f"{prefix}{session_part}-{random_part}-{base_id}"
```

where `base_id` defaults to `self.class_name` of the caller (`TemporalPipeRun`, `TemporalPipeRouter`, …). Example seen in the dashboard:

```
EdgdJ-HR5fd-TemporalPipeRun-pipe-router
```

Decomposed:

- `EdgdJ` — 5 chars of session id
- `HR5fd` — 5 chars of shortuuid
- `TemporalPipeRun-pipe-router` — the calling class name + a hardcoded literal

This tells an operator nothing about **what was actually executed**. The Temporal dashboard also shows the **workflow type/name**, which is the registered class — things like `wf_pipe_router`. So a typical row reads:

| Workflow ID | Workflow Type |
|---|---|
| `EdgdJ-HR5fd-TemporalPipeRun-pipe-router` | `wf_pipe_router` |
| `EdgdJ-HR5fd-TemporalPipeRun-pipe-router` (child) | `wf_pipe_router` |
| `EdgdJ-HR5fd-TemporalPipeRun-pipe-router` (child) | `wf_pipe_router` |

Three "router" workflows ran. Which pipes? Which concepts? Which inputs? Invisible.

### The real requirements

We need a coherent design covering all of the following — currently none of them are designed, only accreted:

1. **Top-level workflow id.** What identifies a single user-initiated pipeline run? Must be unique, traceable back to the user / session / pipe code, and ideally readable.

2. **Child-workflow id.** When a parent pipe spawns children (sub-pipes, parallel branches), how are their ids derived from the parent's? Today: same shape, fresh `shortuuid`, no parent link visible in the id.

3. **Workflow type/name (the registered class).** Today fixed at the class level (`wf_pipe_router`, …). Could we register more semantically meaningful workflow types per pipe, or carry the pipe code in a search attribute / memo so it's filterable in the dashboard?

4. **Activity id.** Must be unique per `(workflow_id, run_id)`. Today: constant strings → collision on repeated calls. Needs a per-call disambiguator that is **deterministic across replay** (so `workflow.uuid4()` or a workflow-local counter — not `uuid.uuid4()` from stdlib).

5. **Activity type/name.** The Python function name (`act_llm_gen_text`, …). Probably fine, but worth re-checking against the observability story.

6. **Human-readable summaries.** Temporal supports per-activity / per-workflow `summary` and `details` metadata (and search attributes / memos) that can be surfaced in the dashboard without affecting ids. We are not using these.

7. **Display in our own webapps and reporting.** The same ids and names need to be useful in our UIs, not just the Temporal dashboard. Today they are opaque.

### Constraints any solution must respect

- **Determinism.** Whatever generates the per-call piece of an `activity_id` (and any workflow id chosen from inside workflow code) must be replay-safe. Reach for `workflow.uuid4()`, `workflow.info()`, or workflow-local counters — never `uuid.uuid4()`, `time.time()`, `random.*`, or any worker-singleton state mutated from workflow code.
- **No worker-singleton state.** The current LRU is on `ContentGeneratorInWorkflow`, a worker-wide singleton. Solutions that lean on the singleton inherit the same replay-safety hazard (`is_replaying()` short-circuits, LRU eviction races) that makes the current code ugly. Whatever we do should keep per-execution state inside the workflow execution.
- **Backwards compatibility is not required.** Per `CLAUDE.md`: no transition period. Rename `wfid` to whatever it should be, change defaults, break callers. The cost is in the changelog, not in deprecation.

## What this session should NOT do

- Don't pick a numbering scheme.
- Don't decide between `workflow.uuid4()` suffix, counter, omitted `activity_id`, search attributes, or workflow-summary metadata.
- Don't rename `wfid` yet.

All of the above belong in a fresh session that starts by **reading the Temporal references** (especially `references/python/observability.md`, `references/python/advanced-features.md`, and the determinism/replay parts of `references/core/determinism.md` and `references/python/determinism.md`) and then designs the id+naming model from scratch.

## Working starting points for next session

- `tests/unit/pipelex/temporal/test_default_activity_id_collision_bug.py` — the failing test gate. Run `.venv/bin/pytest -v tests/unit/pipelex/temporal/test_default_activity_id_collision_bug.py` to see the current red state (both tests fail with `ContentGenerationError: Duplicate activity_id ...`).
- `pipelex/temporal/tprl_content_generation/content_generator_in_workflow.py:48-109` — the LRU machinery that becomes deletable once the activity-id design is fixed.
- `pipelex/temporal/temporal_manager.py:95-110` — top-level workflow id construction.
- `pipelex/temporal/tprl/workflow_caller.py:84-87` — `make_workflow_id` delegator.
- `pipelex/temporal/tprl_pipe/temporal_pipe_run.py`, `temporal_pipe_router.py` — call sites that pass `wfid` as a workflow-id base.
- `pipelex/cogt/content_generation/content_generator_protocol.py` — protocol that defines `wfid` on every `make_*` method; will need updating once the per-call activity-id concern is removed from this layer.
- Worker singleton wiring in `pipelex/pipelex.py:347` — explains why the LRU has to be (workflow_id, run_id)-keyed today.
