# Temporal IDs and Naming — Implementation Plan

## Status

**All four phases implemented on `feature/Temporal-config` (uncommitted).** TDD gate green, `make agent-check` clean across the lot, unit suite passes (4501 tests). Phase-by-phase checkpoints below capture handoff state for review and follow-on work.

Original plan: implements `id-and-naming-design.md` against the failing TDD gate in `tests/unit/pipelex/temporal/test_default_activity_id_collision_bug.py`. Aligned with the problem statement in `workflow-and-activity-ids.md` and the primitives reference in `temporal-id-primitives.md`.

## Cold-start orientation

A fresh session picking this up should read in this order:

1. `wip/temporal-primitives/workflow-and-activity-ids.md` — the problem statement and the failing TDD gate that frames this work.
2. `wip/temporal-primitives/temporal-id-primitives.md` — what Temporal's identifier and observability surface actually offers.
3. `wip/temporal-primitives/id-and-naming-design.md` — the authoritative spec. If anything in this plan conflicts with the design doc, the design doc wins.
4. This file — the sequencing of work and the per-phase done-when criteria.

### Key code anchors

The redesign rotates around these load-bearing locations. Open them before touching anything:

- `pipelex/temporal/temporal_manager.py:95-110` — current top-level workflow_id construction; Phase 1 replaces it.
- `pipelex/temporal/tprl/workflow_caller.py:84-87` — `make_workflow_id` delegator; Phase 1 simplifies it.
- `pipelex/temporal/tprl_content_generation/content_generator_in_workflow.py:48-109` — the LRU + `_record_activity_id` machinery deleted in Phase 2.
- `pipelex/temporal/tprl_content_generation/content_generator_in_workflow.py:111-528` — every `make_*` method whose `wfid` parameter and `activity_id=` argument are rewritten in Phase 2.
- `pipelex/cogt/content_generation/content_generator_protocol.py` — `wfid` on every method; dropped in Phase 2.
- `pipelex/temporal/tprl_pipe/wf_pipe_run.py:46` — hardcoded `f"{workflow_id}-pipe-router"` child id; separator flips to `/` in Phase 3.
- `pipelex/temporal/tprl_pipe/temporal_pipe_router.py:55-87` — child + top dispatch branches rewritten in Phase 3.
- `pipelex/temporal/tprl_pipe/temporal_pipe_run.py:43-65, 73-101` — top-level dispatch rewritten in Phase 3.
- `pipelex/pipe_run/pipe_run_protocol.py`, `pipe_router_protocol.py` — non-Temporal protocols still carrying `wfid`; dropped in Phase 3.
- `pipelex/pipelex.py:347` — worker-singleton instantiation of `ContentGeneratorInWorkflow`. Why this matters: the LRU exists *because* the disambiguator lived on this singleton; once the SDK assigns activity_ids, the singleton becomes plain stateless code and the LRU goes away.
- `pipelex/pipeline/pipeline_factory.py:17` — `make_pipeline_run_id` (UUID, unchanged; we just stop ignoring its output).
- `pipelex/pipeline/job_metadata.py:43` — `JobMetadata.pipeline_run_id` (the canonical identity, unchanged).
- `tests/unit/pipelex/temporal/test_default_activity_id_collision_bug.py` — the TDD gate. Run it on entry to confirm it is red; it must be green after Phase 2.

### The fact that unblocks the protocol cleanup

A grep at design time confirmed: **no production code passes a non-`None` `wfid`**. Every `wfid=` call site is in `tests/`. That is the empirical reason it is safe to drop the parameter from `PipeRunProtocol`, `PipeRouterProtocol`, and `ContentGeneratorProtocol` without a deprecation cycle. Re-run the grep if time has passed:

```bash
grep -rn "wfid=" pipelex/ | grep -v "wfid=None" | grep -v "wfid: str"
```

If this returns anything, stop and reassess before touching protocols.

### Verification commands

The "Done when" criteria in each phase reference these checks:

```bash
# Run the failing TDD gate (red on entry; green after Phase 2)
.venv/bin/pytest -v tests/unit/pipelex/temporal/test_default_activity_id_collision_bug.py

# Phase 2 done: no wfid in the activity layer
grep -rn "wfid" pipelex/cogt/ pipelex/temporal/tprl_content_generation/

# Phase 3 done: no wfid anywhere in pipelex/
grep -rn "wfid" pipelex/

# Quality gates (every phase)
make agent-check
make agent-test
```

### Tooling

- `make agent-check` — runs ruff (fix-unused-imports, lint, format), pyright, mypy, plxt. Silent on success, full output on failure.
- `make agent-test` — runs the test suite the same way. Use this, not `make test`.
- `/temporal-e2e-validate` — slash-command skill (declared in the agent's skill list) that validates Temporal distributed execution against a real server. Use it once Phase 3 lands to confirm the new identity model end-to-end.
- Integration tests support `--temporal-server local|testing|<profile>` — see CLAUDE.md "Temporal Integration Test Options."

## How to use this plan

Four phases, each independently mergeable. Every phase ends with `make agent-check` and `make agent-test` green. Checkpoints between phases are explicit handoff points: the next session can pick up cold by reading this doc + the checkpoint notes filled in by the previous session.

The phase ordering is chosen so that the bug fix (Phase 2) lands as early as possible: foundations first, then the activity-layer rewrite that flips the TDD gate green, then the workflow-layer rewrite, then deployment & docs.

**Parallelism.** Phase 1 must land first (helpers + extended `WorkflowExecutor` surface). Phases 2 and 3 are formally independent — Phase 2 touches `tprl_content_generation/*` and `cogt/content_generation/*` exclusively; Phase 3 touches `tprl_pipe/*` and `pipe_run/*` exclusively. They can run in parallel branches after Phase 1 merges. Phase 4 waits for both so the CHANGELOG is final. **Lane structure: Phase 1 → (Phase 2 ∥ Phase 3) → Phase 4.**

Each phase section answers the same four questions: **What lands**, **Files touched**, **Tests**, **Done when**. The change set in the design doc is the authoritative spec for every file change — this plan only sequences the work.

---

## Phase 1 — Foundations (additive only)

**What lands.** A new `observability.py` helper module, a renamed/simplified `make_top_workflow_id` on `TemporalManager`, and additive `search_attributes` / `static_summary` / `static_details` / `memo` parameters on every `WorkflowExecutor` workflow-start method (top-level **and** child). No call site uses the new infrastructure yet. No behavior changes for end users.

**Files touched.**

- `pipelex/temporal/tprl/observability.py` (new) — five pure-function helpers:
    - `build_search_attributes(pipe_job: PipeJob) -> Mapping[str, list[str]]`
    - `build_search_attributes_for_child(child_pipe_job: PipeJob, parent_search_attrs: Mapping[str, list[str]]) -> Mapping[str, list[str]]`
    - `build_static_summary(pipe: PipeBase) -> str` — `pipe.description` is required-but-can-be-empty (Pydantic field, not Optional). The "omit when missing" rule is interpreted as "omit the dash-and-tail when `pipe.description == ""`".
    - `build_static_details(pipe_job: PipeJob, library_crate_id: str | None) -> str`
    - `build_activity_summary(method_label: str, job_metadata: JobMetadata, **extras: str) -> str`
- `pipelex/temporal/temporal_manager.py` — replace `make_top_workflow_id(base_id: str)` with `make_top_workflow_id(pipeline_run_id: str)`. The session-id and random-id truncations are deleted; `self.session_id` stays as an instance field so the search-attribute helper can read it.
- `pipelex/temporal/tprl/workflow_caller.py` — extend the wrapper's full surface:
    - `WorkflowExecutor.execute_workflow` and `start_workflow` gain optional `search_attributes`, `static_summary`, `static_details`, `memo` parameters that pass through to `client.execute_workflow` / `client.start_workflow`.
    - **`WorkflowExecutor.execute_child_workflow` and `start_child_workflow` gain the same four parameters**, passed through to `workflow.execute_child_workflow` / `workflow.start_child_workflow`. The SDK supports them on both top-level and child variants; Phase 3 needs them on the child path.
    - `make_workflow_id(base_id: str)` is renamed to `make_workflow_id(pipeline_run_id: str)`.

**Tests.**

- `tests/unit/pipelex/temporal/test_observability_helpers.py` (new) — unit tests for every helper, including 200-byte UTF-8 truncation behavior, empty-string `pipe.description`, child-attribute inheritance with PipeCode/DomainCode overridden and the other three inherited.
- `tests/unit/pipelex/temporal/test_workflow_caller_passthrough.py` (new) — assert that `search_attributes`, `static_summary`, `static_details`, `memo` reach the SDK call. Mock the temporal client / `workflow.execute_child_workflow` and assert `call_args.kwargs.get("search_attributes")` (and the other three) match what `WorkflowExecutor` was given. Covers all four entry points (`execute_workflow`, `start_workflow`, `execute_child_workflow`, `start_child_workflow`).
- A grep at design time confirmed **no existing test asserts on the old `{session5}-{rand5}-{base_id}` workflow-id shape**. No transitional handling is needed; the only legitimate production caller of `make_top_workflow_id` is `WorkflowExecutor.make_workflow_id`, and that's the renamed-arg change.

**Done when.**

- `make agent-check` clean.
- `make agent-test` green. The TDD gate test in `test_default_activity_id_collision_bug.py` is still red (expected — Phase 2 fixes it).
- The new helpers have unit-test coverage for the formats specified in the design doc.

### Checkpoint — end of Phase 1

- **Status.** Implemented on branch `feature/Temporal-config` (uncommitted).
- **Code state.**
    - `pipelex/temporal/tprl/observability.py` added with the five helpers exactly as planned. Signatures: `build_search_attributes(pipe_job)`, `build_search_attributes_for_child(child_pipe_job, parent_search_attrs)`, `build_static_summary(pipe)`, `build_static_details(pipe_job, library_crate_id)`, `build_activity_summary(method_label, job_metadata, **extras)`. UTF-8 200-byte truncation appends a `…` and decodes with `errors="ignore"` to drop partial multi-byte sequences at the cut.
    - `TemporalManager.make_top_workflow_id` renamed to take `pipeline_run_id: str` and now returns `f"{prefix}{pipeline_run_id}"` — the session/random parts are gone. `self.session_id` still on the instance for the search-attribute helper.
    - `WorkflowExecutor.make_workflow_id(pipeline_run_id: str)` renamed accordingly.
    - `WorkflowExecutor.execute_workflow` / `start_workflow` / `execute_child_workflow` / `start_child_workflow` all gained additive `search_attributes`, `static_summary`, `static_details`, `memo` kwargs, passed through to the underlying SDK call.
    - The two existing call sites in `tprl_pipe/temporal_pipe_run.py` and `tprl_pipe/temporal_pipe_router.py` were updated to use the new `pipeline_run_id=` kwarg name. They still pass `wfid or self.class_name` (a degraded value), which is intentional — Phase 3 threads the real `pipeline_run_id` through.
- **Transitional state to flag for Phase 3.** Because `make_top_workflow_id` now does `{env_prefix}{pipeline_run_id}` with no session/random suffix, and callers still pass `"TemporalPipeRun"` / `"TemporalPipeRouter"` until Phase 3, top-level workflow IDs are currently the degraded shape `ut-TemporalPipeRun` / `ut-TemporalPipeRouter`. Two pipe runs in a row chain under `ALLOW_DUPLICATE` instead of producing distinct IDs. This is a known-broken intermediate state; Phase 3 fixes it by threading `pipe_job.job_metadata.pipeline_run_id` through.
- **Tests added.** `tests/unit/pipelex/temporal/test_observability_helpers.py` (11 tests covering all five helpers, UTF-8 truncation at multi-byte boundaries, child-attr inheritance, empty-description path). `tests/unit/pipelex/temporal/test_workflow_caller_passthrough.py` (4 tests — one per executor entry point, asserting all four kwargs reach the SDK).
- **Quality gates.** `make agent-check` clean (pyright + mypy + ruff + plxt). Full `tests/unit/pipelex/temporal/` targeted run: 192 passed, 2 failed (the expected TDD gate in `test_default_activity_id_collision_bug.py` — still red, fixed by Phase 2).
- **Handoff notes for Phase 2.** No conftest changes; helpers are pure functions. The TDD gate test asserts `len(set(observed_activity_ids)) == 2` — once Phase 2 stops passing `activity_id=`, both calls produce `kwargs.get("activity_id") is None` and the assertion as written would fail with `set([None, None])`. Phase 2 must rewrite the kept gate test per the plan (rename + assert `kwargs.get("activity_id") is None` and inspect the per-call `summary`).

---

## Phase 2 — Activity-layer rewrite (TDD gate green)

**What lands.** The bug fix. `ContentGeneratorInWorkflow` stops customizing `activity_id`, the worker-singleton LRU is deleted, the `wfid` parameter is dropped from `ContentGeneratorProtocol` and every implementation, and every `workflow.execute_activity(...)` call carries a `summary=` derived from the helpers. The TDD gate in `test_default_activity_id_collision_bug.py` flips green naturally.

**Files touched.**

- `pipelex/temporal/tprl_content_generation/content_generator_in_workflow.py`:
    - Delete `_seen_activity_ids`, `_MAX_SEEN_RUNS`, `_record_activity_id`, and every call site of `_record_activity_id`.
    - Drop the `wfid` parameter from every `make_*` method.
    - Drop the `activity_id = wfid or "…"` line and the `activity_id=...` argument from every `workflow.execute_activity(...)` call.
    - Add `summary=build_activity_summary(...)` per the format table in the design doc.
- `pipelex/cogt/content_generation/content_generator_protocol.py` — drop `wfid` from every `make_*` method signature.
- `pipelex/cogt/content_generation/content_generator.py` (direct mode) — drop `wfid` (currently a dead pass-through; direct mode never reads it).
- `pipelex/cogt/content_generation/content_generator_dry.py` (dry mode) — drop `wfid` (currently a dead pass-through).

**Tests.**

- `tests/unit/pipelex/temporal/test_default_activity_id_collision_bug.py`:
    - **Delete** `test_two_make_llm_text_calls_with_same_explicit_wfid_should_succeed` — its premise (`wfid` as the disambiguator) literally no longer exists after the parameter is dropped; it exercises the same code path as the first case anyway.
    - **Keep and rename** `test_two_make_llm_text_calls_without_wfid_should_succeed` → `test_two_default_activity_calls_in_one_workflow_produce_distinct_activity_ids`. The new name reflects the invariant being guarded (per-call uniqueness via SDK default), not the historic bug.
- `tests/unit/pipelex/temporal/test_seen_activity_ids_lru.py` — **delete the entire file (101 lines).** The file is wholly about the LRU machinery; once `_seen_activity_ids` / `_MAX_SEEN_RUNS` / `_record_activity_id` are removed, every test in it fails on `AttributeError`. Nothing to salvage.
- `tests/unit/pipelex/temporal/test_content_generator_in_workflow.py` — every test in this file that asserts on a specific `activity_id` string must be rewritten. Full enumeration (verified by grep at design time):
    - Delete: `test_make_llm_text_threads_explicit_wfid` (line 121), `test_duplicate_wfid_raises_content_generation_error` (line 250), `test_default_wfids_for_image_methods_are_distinct` (line 409), `test_duplicate_check_is_skipped_during_replay` (line 277), `test_activity_id_cache_is_scoped_by_run_id` (line 308) — last two are tests for the deleted LRU short-circuit and cache scoping respectively.
    - Rewrite (replace `activity_id`-string asserts with `kwargs.get("activity_id") is None` and `summary` content asserts):
        - `test_every_dispatch_omits_task_queue_with_empty_routing` (line 100) — drops `activity_id == "craft-text"` assert (line 119).
        - `test_non_llm_text_methods_omit_task_queue_with_empty_routing` (line 146) — drops `activity_id == method_default_id` assert (line 167) plus the parametrized default-id list.
        - `test_make_extract_pages_dispatches_extract_only_when_no_page_views` (line 169) — drops `activity_id == "extract-pages"` assert (line 187).
        - `test_make_extract_pages_image_uri_with_page_views_skips_render_activity` (line 189) — drops `activity_id == "extract-pages"` assert (line 210).
        - `test_make_extract_pages_document_uri_with_page_views_dispatches_two_activities` (line 212) — drops `observed_activity_ids == ["extract-pages", "extract-render-page-views"]` assert (line 244) and the in-loop dispatch-routing-by-activity_id helper (lines 220-225).
    - Add: `test_make_llm_text_omits_activity_id_and_sets_summary` (and one per method) — asserts `mock_execute.call_args.kwargs.get("activity_id") is None` and `kwargs.get("summary")` matches the formatted helper output for that method.
- Any other test in `tests/unit/` / `tests/integration/` that passes `wfid=` to a `make_*` content-generator method is updated to remove the kwarg.

**Done when.**

- `make agent-check` clean.
- `make agent-test` green.
- `test_default_activity_id_collision_bug.py` is green (renamed canonical-gate test exercises the SDK-default integer assertion).
- `tests/unit/pipelex/temporal/test_seen_activity_ids_lru.py` is **deleted from disk** (not commented out).
- Grep confirms zero remaining references to `wfid` in `pipelex/cogt/` and `pipelex/temporal/tprl_content_generation/`.
- Grep confirms zero remaining references to `_seen_activity_ids`, `_MAX_SEEN_RUNS`, or `_record_activity_id` anywhere in `pipelex/` or `tests/`.
- Manual smoke (optional, recommended): run a multi-step pipe via the `temporal-e2e-validate` skill and confirm in the Temporal dashboard's Event History that activity ids are now `"1"`, `"2"`, … with purple-text per-activity summaries.

### Checkpoint — end of Phase 2

- **Status.** Implemented on branch `feature/Temporal-config` (uncommitted).
- **TDD gate.** Green. Renamed canonical-gate test: `tests/unit/pipelex/temporal/test_default_activity_id_collision_bug.py::TestDefaultActivityIdCollisionBug::test_two_default_activity_calls_in_one_workflow_produce_distinct_activity_ids`. Asserts `kwargs.get("activity_id") is None` on every call — Pipelex never customizes `activity_id`, the SDK assigns deterministic integers per workflow run. Targeted run (`tests/unit/pipelex/temporal/ tests/unit/pipelex/cogt/`): 692 passed.
- **Code state.**
    - `ContentGeneratorInWorkflow` rewritten: `_seen_activity_ids`, `_MAX_SEEN_RUNS`, `_record_activity_id` deleted; `wfid` parameter dropped from every `make_*` method; every `workflow.execute_activity(...)` call no longer passes `activity_id=` and now carries `summary=build_activity_summary(...)`. The per-method summary formats are: `LLM text · pipe={code} · model={handle}`, `LLM object · pipe={code} · class={class_name}`, `LLM object list · pipe={code} · class={class_name}`, `Img gen 1× · pipe={code} · model={handle}`, `Img gen N× · pipe={code} · model={handle} · n={count}`, `Templated text · pipe={code}`, `Render page views · pipe={code}`, `Extract pages · pipe={code} · handle={extract_handle}`, `Render page views (extract) · pipe={code}` for the render step inside `make_extract_pages`. The `extract_activity_id` / `render_activity_id` / `base_id` locals were also removed.
    - `wfid` dropped from `ContentGeneratorProtocol` and both other implementations (`pipelex/cogt/content_generation/content_generator.py`, `pipelex/cogt/content_generation/content_generator_dry.py`).
    - Grep confirms zero remaining `wfid` references in `pipelex/cogt/` and `pipelex/temporal/tprl_content_generation/`. Zero references to `_seen_activity_ids` / `_MAX_SEEN_RUNS` / `_record_activity_id` anywhere in `pipelex/` or `tests/`.
- **Tests.**
    - **Deleted from disk:** `tests/unit/pipelex/temporal/test_seen_activity_ids_lru.py` (entire 101-line file).
    - **Rewritten:** `tests/unit/pipelex/temporal/test_default_activity_id_collision_bug.py` reduced to the single canonical-gate test (two parallel tests collapsed; renamed; assertion flipped from "set of two distinct strings" to "every call has `activity_id is None`").
    - **Rewritten:** `tests/unit/pipelex/temporal/test_content_generator_in_workflow.py` — five tests deleted (LRU short-circuit, run-id cache scoping, `threads_explicit_wfid`, `duplicate_wfid_raises`, `default_wfids_for_image_methods_are_distinct`); remaining `activity_id`-string asserts swapped for `activity_id is None` + per-method `summary` strings checked against the formatter output.
    - **Updated integration test:** `tests/integration/pipelex/temporal/tracing/test_split_worker_extract_pages.py::test_two_activity_branch_dispatches_with_distinct_activity_ids` — no longer pins `"extract-pages"` / `"extract-render-page-views"`; now asserts (a) the two activities are scheduled in order and (b) their SDK-assigned activity_ids are distinct.
- **Quality gates.** `make agent-check` clean (pyright + mypy + ruff + plxt).
- **Replay-safety note for future reviewers.** The LRU + `is_replaying()` short-circuit was deleted *because* the disambiguator is no longer worker-singleton state. Any future change that reintroduces worker-singleton state into the activity-dispatch path breaks the determinism guarantee — push back on it in review.
- **Handoff notes for Phase 3.**
    - The `pipe_run/*` and `pipe_router/*` protocols still carry `wfid` as a dead pass-through (the activity layer no longer reads it). Phase 3 drops them.
    - `temporal_pipe_run.py` and `temporal_pipe_router.py` still pass `wfid or self.class_name` to `make_workflow_id(pipeline_run_id=...)` — i.e. workflow IDs are currently shaped `ut-TemporalPipeRun` (degraded). Phase 3 threads the real `pipe_job.job_metadata.pipeline_run_id` through.
    - `wf_pipe_run.py:46` still uses the `{workflow_id}-pipe-router` separator. Phase 3 flips this to `/` (slash). Note that `wf_pipe_run.py` uses **raw** `workflow.execute_child_workflow(...)` directly — not the `WorkflowExecutor.execute_child_workflow` wrapper — so adding `search_attributes=` there is a separate touch from `temporal_pipe_router.py`.

---

## Phase 3 — Workflow-layer rewrite + protocol cleanup

**What lands.** Workflow IDs switch to `{env_prefix}{pipeline_run_id}`. Child workflow IDs switch to slash-separated paths. Search attributes and static summary land on every workflow start. `wfid` is dropped from `PipeRunProtocol`, `PipeRouterProtocol`, and the remaining implementations. Tests assert the new identity model.

**Files touched.**

- `pipelex/temporal/tprl_pipe/temporal_pipe_run.py`:
    - Drop the `wfid` parameter from `run(...)` and `start(...)`.
    - `workflow_id` is built from `pipe_job.job_metadata.pipeline_run_id` via the renamed manager method.
    - Pass `search_attributes`, `static_summary`, `static_details` to `executor.execute_workflow` / `start_workflow` using the helpers.
- `pipelex/temporal/tprl_pipe/temporal_pipe_router.py`:
    - Drop the `wfid` parameter from `_run_pipe_job(...)`.
    - Top-level branch mirrors `temporal_pipe_run.py`.
    - Child branch (inside a workflow): `child_workflow_id = f"{parent_workflow_id}/{pipe_job.pipe.code}-{str(workflow.uuid4())[:8]}"`. Pass `search_attributes` updated for the child via `build_search_attributes_for_child`. Routes through `executor.execute_child_workflow(...)` (the `WorkflowExecutor` wrapper extended in Phase 1).
    - **No defensive `pipe_job.pipe.code or "pipe"` fallback.** `PipeAbstract.code: str` is a required Pydantic field with non-empty syntax validation (`validate_pipe_code_syntax`); the fallback is dead code. If invariants ever change, silently swallowing the violation is worse than crashing loudly.
- `pipelex/temporal/tprl_pipe/wf_pipe_run.py`:
    - Line 46: switch the separator from `-` to `/`: `id=f"{workflow.info().workflow_id}/pipe-router"`.
    - **NOTE — uses raw `workflow.execute_child_workflow(...)`, not the `WorkflowExecutor` wrapper.** Two child-spawn code paths exist in the codebase: this file's raw API call and `temporal_pipe_router.py`'s wrapper call. Both need the search-attribute kwarg added in this phase; the implementer should not assume a single centralization point. (Unifying the two paths is captured in **Out of scope**.)
    - Pass `search_attributes=` directly to the raw call. Re-use the parent's attributes via `workflow.info().typed_search_attributes` (or read the parent's mapping plumbed via workflow input if simpler) — `PipeCode` and `DomainCode` do not change between `wf_pipe_run` and its `wf_pipe_router` child because the router is just executing the same pipe.
- `pipelex/pipe_run/pipe_run.py` and `pipe_run_protocol.py` — drop `wfid` from `run(...)` (dead pass-through today).
- `pipelex/pipe_run/pipe_router.py`, `pipe_router_protocol.py`, `dry_pipe_router.py` — drop `wfid` from `run(...)` / `_run_pipe_job(...)` (dead pass-throughs today; only `TemporalPipeRouter` ever consumed the value).
- Any remaining call sites of these protocols in tests update to not pass `wfid`.

**Static details "Input" line — settled.** `build_static_details` derives the Input row from `pipe_job.pipe.inputs.specs` keys (already a structured `InputStuffSpecs` on `PipeAbstract`). It is declared once per pipe, stable across runs, and does not grow at runtime. If `pipe.inputs.specs` is empty, the Input row is omitted entirely. Working-memory keys are rejected as a source: they expand mid-run depending on which sub-pipe sets them, and would make the Input row racy and noisy.

**Tests.**

- `tests/unit/pipelex/temporal/test_workflow_id_construction.py` (new) — asserts:
    - Top-level: `{env_prefix}{pipeline_run_id}` for each `RunMode`.
    - Fixed-role child: `{parent}/pipe-router`.
    - Dynamic child: `{parent}/{pipe_code}-{8-hex-chars}`.
    - **Replay determinism:** mock `workflow.uuid4` to return a fixed UUID; assert the dynamic child id is fully determined by `(parent_workflow_id, pipe_job.pipe.code, workflow.uuid4 output)`. This forces the implementer to use `workflow.uuid4()`, not stdlib `uuid.uuid4()` (which Temporal's workflow sandbox forbids).
- `tests/unit/pipelex/temporal/test_search_attribute_dict_construction.py` (new) — asserts the five-keyed dict from a representative `pipe_job`, plus the child-attribute inheritance / override rule (PipeCode + DomainCode replaced for the child's pipe; PipelineRunId + SessionId + UserId inherited unchanged).
- A grep at design time confirmed **no existing test asserts on the old `{session5}-{rand5}-{ClassName}` workflow-id shape**; the cross-phase risk listed below for this is already vacated. If a stray assertion is found during implementation, rewrite it.
- Integration tests under `tests/integration/pipelex/temporal/` continue to pass without modification (they don't inspect the workflow_id shape); if any does, it's rewritten.
- Run the `temporal-e2e-validate` skill end-to-end as a final cross-check.

**Done when.**

- `make agent-check` clean.
- `make agent-test` green.
- Grep confirms zero remaining `wfid` references in `pipelex/`.
- A manual run in the Temporal dashboard shows: top-level workflow ID = the `pipeline_run_id` (with env prefix); child workflow IDs are slash-separated paths; the `PipeCode`, `PipelineRunId`, `SessionId`, `UserId`, `DomainCode` search attributes are populated on every workflow row; static summary shows `{pipe_code} — {description}`.

### Checkpoint — end of Phase 3

- **Status.** Implemented on branch `feature/Temporal-config` (uncommitted).
- **Code state.**
    - `wfid` parameter is removed from every protocol and implementation: `PipeRunProtocol`, `PipeRouterProtocol`, `PipeRun`, `PipeRouter`, `DryPipeRouter`, `TemporalPipeRun`, `TemporalPipeRouter`. Final `grep -rn "wfid" pipelex/ tests/` returns empty.
    - `TemporalPipeRun.run` / `start` now thread `pipe_job.job_metadata.pipeline_run_id` into `make_workflow_id(pipeline_run_id=...)` and pass `search_attributes` / `static_summary` / `static_details` via the helpers on every workflow start.
    - `TemporalPipeRouter._run_pipe_job` rewritten: child-branch id is `f"{parent_workflow_id}/{pipe_job.pipe.code}-{str(workflow.uuid4())[:8]}"`; the slash separator is in place; child search attributes are built via `build_search_attributes_for_child` from a parent-attribute dict reconstructed from `pipe_job.job_metadata` + `TemporalManager`. No defensive `pipe.code or "pipe"` fallback — relies on `PipeAbstract.code` being a required non-empty Pydantic field.
    - `wf_pipe_run.py`: line 46 separator flipped from `-` to `/` (`f"{workflow.info().workflow_id}/pipe-router"`). `search_attributes=` now passed to the raw `workflow.execute_child_workflow` call. The parent's attributes are rebuilt locally from `pipe_job` since PipeCode + DomainCode do not change for the fixed-role child (same pipe). `get_temporal_manager` was added to the `workflow.unsafe.imports_passed_through()` block so the sandbox lets it through.
    - `WorkflowExecutor.make_workflow_id` parameter rename from Phase 1 is now wired up to a real `pipeline_run_id` source (was previously receiving the degraded `class_name`).
- **Tests.**
    - New: `tests/unit/pipelex/temporal/test_workflow_id_construction.py` — top-level shape per `RunMode` (parametrized for all five modes), absence-of-session-id assertion, fixed-role child slash suffix, dynamic-child format with mocked `workflow.uuid4()` proving replay determinism (re-running the construction returns the same id).
    - New: `tests/unit/pipelex/temporal/test_search_attribute_dict_construction.py` — five-keyed dict shape + child inheritance rule (PipeCode + DomainCode override; PipelineRunId + SessionId + UserId inherit).
- **Quality gates.** `make agent-check` clean. Targeted run (`tests/unit/pipelex/`): 4497 passed, 1 skipped, 1 xfailed (skip + xfail are pre-existing, unrelated).
- **Operational notes (deferred to Phase 4).** Phase 4 will add the namespace-bootstrap warning. Integration tests under `tests/integration/pipelex/temporal/` will only get a chance to fire that warning when run against a real Temporal server with `--temporal-server <profile>` — they are not run as part of the regular CI agent-test sweep.
- **Handoff notes for Phase 4.**
    - Search-attribute keys to register: `PipeCode`, `PipelineRunId`, `SessionId`, `UserId`, `DomainCode` (all `Keyword`).
    - Bootstrap check belongs in `pipelex/temporal/temporal_task_manager.py` near `TemporalManager.setup(...)` (line ~59). Soft-fail catch is `temporalio.service.RPCError` only; everything else propagates.
    - CHANGELOG should call out the pipeline_run_id → Workflow ID chain semantics shift: callers that pass a stable `pipeline_run_id` to `PipelineFactory.make_pipeline(...)` and re-run now land on the same Temporal Workflow Execution Chain (with `ALLOW_DUPLICATE` reuse policy), where previously the random/session id suffix made every run unique.
    - `wf_pipe_run.py` still uses raw `workflow.execute_child_workflow(...)`, not the wrapper. Unifying the two child-spawn paths is captured in the design's **Out of scope** list — not a Phase 4 deliverable. *(Update: a Phase 5 follow-up briefly unified them through `WorkflowExecutor.execute_child_workflow`; the Phase 6 follow-up reverted that for replay-determinism reasons — see "Phase 5 follow-up — Child-spawn path unification (reverted)" below.)*

---

## Phase 4 — Deployment hooks, docs, CHANGELOG

**What lands.** A bootstrap soft-fail check that warns when required custom search attributes are missing on the namespace. A new docs section explaining the one-time registration step. A CHANGELOG entry covering every breaking change.

**Files touched.**

- `pipelex/temporal/temporal_task_manager.py` (worker boot lives here — `TemporalManager.setup(session_id=...)` runs at line 59 today) — add a `DescribeNamespace` call on worker start. Failure-mode spec:
    - **Catch only `temporalio.service.RPCError`** (the specific cluster-metadata RPC failure). Log a warning naming the unreachable namespace; continue worker boot. Any other exception propagates — it is a real bug, not a degraded-dashboard concern.
    - **Required attributes present:** no warning. Continue boot silently.
    - **Required attributes missing:** log a warning naming exactly which attributes are missing, including the exact `temporal operator search-attribute create` command to register them. Continue boot.
    - Runs **once per worker process** (at boot, not per workflow). The result is not cached across processes — every worker boot does its own check.
- `docs/under-the-hood/temporal-deployment.md` (new) — section on required custom search attributes and how to register them. Cross-link from any existing Temporal-related docs.
- `CHANGELOG.md` — `[Unreleased]` entry covering:
    - Workflow ID shape change (`{env}{session5}-{rand5}-{ClassName}` → `{env_prefix}{pipeline_run_id}`).
    - **Pipeline run chain semantics.** Because the Workflow ID is now derived from `pipeline_run_id`, callers that pass a stable `pipeline_run_id` to `PipelineFactory.make_pipeline(pipeline_run_id=...)` and re-execute will land on the same Temporal Workflow Execution Chain (with a fresh `run_id` per execution and `WorkflowIDReusePolicy` at SDK default `ALLOW_DUPLICATE`). Old behavior produced a fresh workflow_id per execution by accident, via the session-id and random-id components. This is documented behavior now — not a bug, but a real semantic shift for any caller that supplied stable IDs.
    - Child workflow ID separator change (`-` → `/`).
    - Activity ID change (semantic labels → SDK-default integers).
    - `wfid` parameter removed from `PipeRunProtocol`, `PipeRouterProtocol`, `ContentGeneratorProtocol`, and every implementation.
    - New required custom search attributes on the Temporal namespace.

**Tests.**

- `tests/unit/pipelex/temporal/test_search_attribute_bootstrap_check.py` (new) — mocks `DescribeNamespace` to return:
    - (a) all attributes present — no warning logged.
    - (b) some attributes missing — warning logged with the exact registration command, missing names enumerated.
    - (c) `DescribeNamespace` raises `temporalio.service.RPCError` — worker boot continues, soft-fail warning logged, the check returns cleanly. Any other exception type propagates and crashes the worker (assert with `pytest.raises`).

**Done when.**

- `make agent-check` clean.
- `make agent-test` green.
- Docs preview renders the new section.
- CHANGELOG entry written in the project's voice (one line per breaking change is fine; the pipeline-run-chain semantics line spells out the behavioral change explicitly).
- `temporal-e2e-validate` skill run on a clean namespace (without the attributes registered) emits the warning; with attributes registered, runs cleanly.

---

## Phase 5 — Migrate to `TypedSearchAttributes` (deprecation cleanup)

**What lands.** Replace the dict-based `search_attributes` arg (currently `Mapping[str, list[str]]`) with `temporalio.common.TypedSearchAttributes` everywhere Pipelex sets them. The dict form still works on temporalio 1.23.0 but emits `DeprecationWarning: Dictionary-based search attributes are deprecated` on every workflow start; the SDK has announced removal in a future version.

**Code anchors.**

- `pipelex/temporal/tprl/observability.py` — `build_search_attributes` and `build_search_attributes_for_child` return `Mapping[str, list[str]]` today. They should return `TypedSearchAttributes`. Define five module-level constants: `PIPE_CODE_KEY = SearchAttributeKey.for_keyword("PipeCode")`, etc.
- `pipelex/temporal/tprl/workflow_caller.py` — the four entry points (`execute_workflow`, `start_workflow`, `execute_child_workflow`, `start_child_workflow`) declare `search_attributes: Mapping[str, list[str]] | None`. Switch the type annotation to `TypedSearchAttributes | None`. The pass-through to the SDK is unchanged at the call site.
- `pipelex/temporal/tprl_pipe/temporal_pipe_run.py`, `temporal_pipe_router.py` — call sites currently do `search_attributes=dict(build_search_attributes(pipe_job))`. Drop the `dict(...)` wrap; pass the `TypedSearchAttributes` directly.
- `pipelex/temporal/tprl_pipe/wf_pipe_run.py` — currently builds a local `child_search_attributes` dict. Rebuild as `TypedSearchAttributes` (or call `build_search_attributes(workflow_arg.pipe_job)` directly — fine inside the `imports_passed_through` block).
- `build_search_attributes_for_child` is currently a dict merge. `TypedSearchAttributes` is immutable; use `parent_attrs.updated(SearchAttributePair(PIPE_CODE_KEY, child_code), SearchAttributePair(DOMAIN_CODE_KEY, child_domain))`.

**Tests.**

- `tests/unit/pipelex/temporal/test_observability_helpers.py` and `test_search_attribute_dict_construction.py` currently assert dict equality (`attrs == {"PipeCode": ["..."], ...}`). Rewrite to assert membership in a `TypedSearchAttributes` instance — iterate `.search_attributes` and check each `SearchAttributePair`'s key + value, or use the public `for_keyword(...)` lookup.
- `test_workflow_caller_passthrough.py` reads `call_args.kwargs.get("search_attributes")` — that value is now a `TypedSearchAttributes` instance; assert against the typed form.
- `tests/integration/pipelex/temporal/conftest.py` and `test_payload_codec_pipeline.py` already call `ensure_required_search_attributes_registered` — no test changes needed there; the registration helper uses the bridge-level `AddSearchAttributesRequest`, not the workflow client API.

**Done when.**

- `make agent-check` clean.
- `make agent-test` green.
- Running `tests/integration/pipelex/temporal/` produces **zero** `DeprecationWarning: Dictionary-based search attributes are deprecated` lines.
- `grep -rn "Mapping\[str, list\[str\]\]" pipelex/temporal/` returns no results in the search-attribute pass-through code.

**Open questions (decide during implementation).**

- Where to put the five `SearchAttributeKey` constants — top of `observability.py` (current preference) or a dedicated `search_attribute_keys.py` if any other module ever needs them. Default: keep them in `observability.py` for now.
- Whether the `build_static_summary` helper should also accept a `TypedSearchAttributes` for callers that already have one. Probably no — `static_summary` is a separate concept (Markdown string, not Keyword).

### Checkpoint — end of Phase 5

- **Status.** Implemented on branch `feature/Temporal-ids` (uncommitted).
- **Code state.**
    - `pipelex/temporal/tprl/observability.py` now defines five module-level `SearchAttributeKey[str]` constants (`PIPE_CODE_KEY`, `PIPELINE_RUN_ID_KEY`, `SESSION_ID_KEY`, `USER_ID_KEY`, `DOMAIN_CODE_KEY`) and `build_search_attributes` returns `TypedSearchAttributes` instead of `Mapping[str, list[str]]`. The five `SearchAttributePair` instances replace the old dict literal one-for-one. No `build_search_attributes_for_child` exists today — earlier phases collapsed child-attribute construction to just calling `build_search_attributes(child_pipe_job)`, since the child's `pipe_job` already carries inherited identity. Phase 5 did not need to touch that simplification.
    - `pipelex/temporal/tprl/workflow_caller.py` — all four executor entry points (`execute_workflow`, `start_workflow`, `execute_child_workflow`, `start_child_workflow`) now declare `search_attributes: TypedSearchAttributes | None`. The SDK pass-through is unchanged; only the type annotation flipped.
    - `pipelex/temporal/tprl_pipe/temporal_pipe_run.py`, `temporal_pipe_router.py`, `wf_pipe_run.py` — the four `search_attributes=dict(build_search_attributes(pipe_job))` call sites are now `search_attributes=build_search_attributes(pipe_job)` (dict wrap dropped). No other changes at these call sites.
- **Tests.**
    - `tests/unit/pipelex/temporal/test_observability_helpers.py` — imports the five `*_KEY` constants and rewrote `test_build_search_attributes_returns_five_keyed_dict` → `test_build_search_attributes_returns_five_typed_keys`, asserting against the typed form (`attrs[KEY] == "..."` plus `len(attrs) == 5`) instead of dict equality.
    - `tests/unit/pipelex/temporal/test_search_attribute_dict_construction.py` — same conversion: imports the five `*_KEY` constants; asserts via `attrs[KEY]` instead of dict access by string. Renamed the top-level test to `test_top_level_attrs_have_five_keys_with_correct_value_sources`.
    - `tests/unit/pipelex/temporal/test_workflow_caller_passthrough.py` — `_SEARCH_ATTRS` constant changed from a `dict` to a `TypedSearchAttributes([SearchAttributePair(SearchAttributeKey.for_keyword("PipeCode"), "translate_doc"), ...])`. The four pass-through assertions (`kwargs.get("search_attributes") == _SEARCH_ATTRS`) still work — `TypedSearchAttributes` supports value equality.
- **Quality gates.** `make agent-check` clean (pyright 0/0/0, mypy success). Targeted unit run (`tests/unit/pipelex/temporal/`): 201 passed. Integration run (`tests/integration/pipelex/temporal/` with default `--temporal-server none`): 117 passed, 2 xpassed. `grep -rn "Mapping\[str, list\[str\]\]" pipelex/temporal/` returns empty. Running the integration suite with `-W "always::DeprecationWarning"` produces zero "Dictionary-based search attributes are deprecated" lines.
- **API note.** Each typed key holds a single `str` value, not a list. The old dict form used `list[str]` because Temporal's dashboard filtering API on Keyword attributes is multi-valued; with `SearchAttributeKey.for_keyword(...)` the value type is `str` (single-valued). The SDK serializes both forms to the same wire shape, so the cluster-side behavior is identical.
- **Handoff notes for Phase 6.**
    - No unrelated dict-based search-attribute call sites surfaced. The only remaining places that touch search attributes are `namespace_check.py` (`AddSearchAttributesRequest` and `ListSearchAttributesRequest` — bridge-level, not SDK workflow API) and the conftest auto-registration. Both are untouched and correct.
    - Phase 6 is the soft-fail → hard-fail flip in `namespace_check.py:check_required_search_attributes`. The five attribute keys are already centralized as the module-level `REQUIRED_SEARCH_ATTRIBUTES` tuple there; no further refactor needed before flipping the failure mode.
    - Tests that mock `build_search_attributes` no longer need to manufacture dicts; they can use `TypedSearchAttributes([])` or call the helper directly with a stubbed `pipe_job`.

### Phase 5 follow-up — Child-spawn path unification (reverted)

- **What was attempted.** `wf_pipe_run.py` was briefly routed through `WorkflowExecutor.execute_child_workflow(...)` via `WorkflowExecutorFactory[PipeJob, PipeOutput]().create_executor(task_queue=None)` — the same pattern `TemporalPipeRouter._run_pipe_job` then used on its child branch. The stated goal was consistency across both child-spawn code paths.
- **Why it was reverted (Phase 6 follow-up, commit `ac8e2335`).** `WorkflowExecutorFactory.create_executor` reads `get_config().temporal.worker_config` to seed `execution_timeout`, `retry_policy`, `run_timeout`, `task_timeout`, `start_delay`, `rpc_timeout` for the executor instance. Inside a workflow, those values would then be baked into the recorded `StartChildWorkflowExecution` command. After any config edit on the worker process, replay would re-derive different values, and Temporal would reject the replay with a non-determinism mismatch. The wrapper is safe at the **submitter boundary** (top-level dispatch) where the executor is constructed once per call from current config; it is NOT safe inside a workflow.
- **Current state (both child-spawn paths).** `wf_pipe_run.py` (fixed-role `pipe-router` child) and `temporal_pipe_router.py` (dynamic sub-pipe child) both call `workflow.execute_child_workflow(...)` directly. They wrap `ChildWorkflowError` as `WorkflowExecutionError` in-place to preserve the `workflow_failure_exception_types` contract registered on the Worker — see `pipelex/temporal/temporal_task_manager.py:make_worker`.
- **Related session-id determinism fix (same `ac8e2335` commit).** `build_search_attributes` and `build_static_details` previously read `get_temporal_manager().session_id` at workflow run time. That field is per-worker-process and would differ across replays after a worker restart. Replaced with a new `stamp_submitter_session_id(pipe_job)` helper called at every top-level Temporal dispatch boundary; `JobMetadata.session_id` carries the stamped value through every child workflow input, and both helpers now read it off `pipe_job` so they stay pure functions of the workflow input.
- **What the `WorkflowExecutor.execute_child_workflow` / `start_child_workflow` wrapper methods are good for.** Production code does not call them. They remain on `WorkflowExecutor` for completeness of the four-entry-point surface, with docstring warnings about the in-workflow replay-determinism trap. If a future caller is OK with config-baked options (e.g. a one-shot script that doesn't care about replay), they're available.
- **Quality gates.** `make agent-check` clean. `make agent-test` green.

### Phase 5 follow-up — Pre-Phase-6 cleanup

- **What landed.**
    - **Tightened exception handling in `pipelex/temporal/tprl/workflow_caller.py`.** Replaced catch-all `except Exception` on all four entry points with named SDK exceptions: `(WorkflowAlreadyStartedError, RPCError, WorkflowFailureError)` for `execute_workflow`; `(WorkflowAlreadyStartedError, RPCError)` for `start_workflow`; trailing `except Exception` blocks dropped from `execute_child_workflow` and `start_child_workflow` (the existing `except ChildWorkflowError` is the only thing those paths can raise). Resolves the `# TODO: wip - do not catch all exceptions` self-comment. Per CLAUDE.md, anything outside these named exceptions is a real bug and must propagate.
    - **Failure-path test for `WfPipeRun`.** Added `tests/integration/pipelex/temporal/test_wf_pipe_run_failure_path.py`. Pins the invariant: when the child `WfPipeRouter` raises `ApplicationError`, the wrapper converts it to `WorkflowExecutionError`, `WfPipeRun` catches it, `act_deliver` fires exactly once with `status=DeliveryStatus.FAILED` and `pipe_output=None`, and the workflow re-raises the original execution error. Stubs the failing router via a `WfPipeRouterFailingStub` workflow registered with `@workflow.defn(name="wf_pipe_router")` (replaces the real router by name on the test worker). Stubs `act_deliver` via a closure-capturing activity.
    - **Latent production bug fix: `workflow_failure_exception_types` registration.** While writing the failure-path test, discovered that `WfPipeRun` re-raising `WorkflowExecutionError` triggers indefinite workflow-task retry instead of a terminal workflow failure — because `WorkflowExecutionError` is a `PipelexError(Exception)`, not a `temporalio.exceptions.FailureError` subclass. Temporal SDK only treats `FailureError` subclasses as workflow failures by default; everything else is treated as a programmer bug and the activation is retried forever. Pre-Phase-5 code raised `ChildWorkflowError` directly (a `FailureError`), so this was masked. Fixed by adding `workflow_failure_exception_types=[WorkflowExecutionError]` to `pipelex/temporal/temporal_task_manager.py:make_worker` (production) and the equivalent option on the test Worker. With this registered, any workflow that propagates `WorkflowExecutionError` now ends terminally and the failure surfaces to the client as `WorkflowFailureError`.
    - **TODOS.md doc-path fix.** Phase 4 "Files touched" section now points at `docs/under-the-hood/temporal-deployment.md` (Phase 6's "Code anchors" already had the correct path).
- **Quality gates.** `make agent-check` clean. `make agent-test` green (full suite).

---

## Phase 6 — Hard-fail worker boot + configurable attributes + CLI registration

### Cold-start orientation for Phase 6

A fresh session picking this up should read in this order:

1. The top of this file (`## Status`, `## Cold-start orientation`, `## How to use this plan`) — gives global framing and confirms Phases 1–5 are merged on `feature/Temporal-ids`.
2. `wip/temporal-primitives/id-and-naming-design.md` — authoritative spec for the five search attributes (`PipeCode`, `PipelineRunId`, `SessionId`, `UserId`, `DomainCode`) and what they're for. The design doc framed missing attributes as a degraded-dashboard concern; **this phase overrides that framing** for reachable real namespaces, because real clusters reject every workflow start that references an unregistered attribute (not just degrade filtering).
3. This Phase 6 section in full.
4. The Phase 5 checkpoint just above — confirms the typed-attribute surface (`TypedSearchAttributes`, `SearchAttributeKey.for_keyword`) that Phase 6 builds on.

**Verification before touching anything:**

```bash
# Targeted unit suite must be green on entry — that's the Phase 5 final state.
.venv/bin/pytest tests/unit/pipelex/temporal/ -q

# The existing unit test for the bootstrap check exercises today's soft-fail
# behavior. Read it before rewriting — the rewrite changes the contract.
.venv/bin/pytest tests/unit/pipelex/temporal/test_search_attribute_bootstrap_check.py -v
```

**Key code anchors (line numbers verified at plan time; re-check if drift suspected):**

- `pipelex/temporal/tprl/namespace_check.py:32` — `REQUIRED_SEARCH_ATTRIBUTES` tuple (rename + relocate target). The full module is ~120 lines and covers both the soft-fail check and the auto-register helper used by tests.
- `pipelex/temporal/tprl/namespace_check.py:54` — `check_required_search_attributes` (the soft-fail audit; today logs `log.warning(...)` and returns — must hard-fail for the configured subset on reachable namespaces).
- `pipelex/temporal/tprl/namespace_check.py:93` — `ensure_required_search_attributes_registered` (auto-register helper; gains `configured_attributes` parameter + permission-denied fallback).
- `pipelex/temporal/temporal_task_manager.py:32` — top-level import of `check_required_search_attributes`.
- `pipelex/temporal/temporal_task_manager.py:195` — call site inside `run_worker`. Gate on `enabled` flag from new config.
- `pipelex/temporal/config_temporal.py:577-586` — `class Temporal(ConfigModel)`. Add `search_attributes: SearchAttributesConfig` field here. New `SearchAttributesConfig` model goes earlier in the module (alongside `WorkerScopesConfig` at line 84). New `BUILTIN_SEARCH_ATTRIBUTES` tuple also lives here (the `TYPE_CHECKING`-only `temporalio` import guarantees the module is safe to load without the temporal extra).
- `pipelex/temporal/exceptions.py:20` — `TemporalConfigError`. New `SearchAttributeRegistrationError` subclasses this.
- `pipelex/temporal/tprl/observability.py:53-69` — `build_search_attributes`. Add the early-return-when-disabled branch + filter-by-configured-subset logic before the five `SearchAttributePair` constructors.
- `pipelex/temporal/tprl/observability.py:29-33` — the five `*_KEY` module constants. Filter logic walks these by name.
- `pipelex/pipelex.toml:445-449` — `[temporal]` block (currently just `is_enabled` + `payload_codec_config`). New `[temporal.search_attributes]` block inserts after line 449 (before `[temporal.worker_config]`).
- `pipelex/cli/_cli.py:20` — `from pipelex.cli.commands.worker_cmd import worker_cmd` — the precedent for module-level CLI command import; the new `setup_temporal_namespace_cmd` slots in next to it on line 21.
- `pipelex/cli/_cli.py:33` — `list_commands` order (`["login", "init", "doctor", ..., "worker"]`). Append `"setup-temporal-namespace"` (or chosen name) at the end.
- `pipelex/cli/_cli.py:209` — `app.command(name="worker", ...)` registration; new command registers next to it.
- `pipelex/cli/commands/worker_cmd.py:45` — example of deferred `pipelex.temporal.*` import with `# noqa: PLC0415`. **Copy this pattern verbatim** in the new command so the temporal extra stays optional.
- `pipelex/cli/cli_factory.py` — `make_pipelex_for_cli(...)` accepts `temporal_enabled=True`. The new command calls this the same way `worker_cmd` does at line 43.
- `pipelex/temporal/temporal_connect.py` — `connect_to_temporal_selected_server(selected_server_config=...)` is the entry the new CLI command uses to honor `--server <profile>`. Already used by the integration conftest at line 145.
- `tests/integration/pipelex/temporal/conftest.py:16,120,126` — three existing call sites of `ensure_required_search_attributes_registered`. After the helper grows a `configured_attributes` parameter, these must pass `BUILTIN_SEARCH_ATTRIBUTES` explicitly. **Don't forget the third call site** at line 126 (time-skipping server branch).
- `tests/integration/pipelex/temporal/test_payload_codec_pipeline.py:25,123` — second test file calling the helper; same signature update.
- `tests/unit/pipelex/temporal/test_search_attribute_bootstrap_check.py:20,42,46,58,80,90` — the existing four tests against the soft-fail contract. Phase 6 rewrites them per the Tests section below; the `REQUIRED_SEARCH_ATTRIBUTES` import becomes `BUILTIN_SEARCH_ATTRIBUTES`.

**Three call sites of `build_search_attributes(pipe_job)` that will inherit the filter automatically** (no Phase 6 work here, but flag them if a test surfaces the wrong behavior):

- `pipelex/temporal/tprl_pipe/temporal_pipe_run.py:69, 106`
- `pipelex/temporal/tprl_pipe/temporal_pipe_router.py:72, 93`
- `pipelex/temporal/tprl_pipe/wf_pipe_run.py:55`

Since they all delegate to `build_search_attributes`, the `enabled = false` early-return propagates through five workflow-start paths with one change.

**External tooling worth knowing about:**

- `/temporal-e2e-validate` skill (Claude Code) — validates Temporal distributed execution against a real server end-to-end. Use after Phase 6 lands with `[temporal.search_attributes] enabled = true` AND `enabled = false` to confirm both paths.
- Integration tests support `--temporal-server local|testing|<profile>` for running against a real cluster. See CLAUDE.md "Temporal Integration Test Options."
- For Temporal Cloud verification: cluster admin registers via `tcld namespace search-attributes add` or the Cloud UI's "Namespace → Custom Search Attributes" page. Worker API keys typically lack `OperatorService` permissions — the `pipelex setup-temporal-namespace --dry-run` path is the operator-facing fallback for that case.

**What lands.** Three intertwined deliverables:

1. **Configurable search-attribute surface.** A new `[temporal.search_attributes]` config block with a master `enabled` toggle and an `attributes` subset selector (opt-in/opt-out of the fixed five — names and value sources stay built-in; custom attributes are out of scope).
2. **Hard-fail worker boot when attributes are missing on a reachable namespace.** Flip the current soft-fail framing (warn-and-continue) into a hard fail. The current behavior is dishonest: workers boot fine when the configured custom attributes are missing, but every workflow dispatch then fails with `RPCError: Namespace ... has no mapping defined for search attribute PipeCode`. Better to fast-fail at worker boot with the exact registration command than to keep failing on every dispatch with a less actionable error.
3. **`pipelex setup-temporal-namespace` CLI command.** Wraps the existing `ensure_required_search_attributes_registered` helper so operators don't need a separate `temporal` / `tcld` install for the common case. Reads the same `[temporal.temporal_config]` block the worker uses, so the namespace/host can never drift between "what got registered" and "what the worker will dispatch to". `--dry-run` prints the equivalent `temporal operator search-attribute create` command instead of executing.

**Why this isn't a no-op.** The Phase 4 design doc framed the missing-attributes case as "degraded dashboard, workflows still run". That premise is false against a real Temporal server — the cluster rejects every workflow start that references an unregistered attribute. The CHANGELOG and `docs/under-the-hood/temporal-deployment.md` need to be updated to match the new strict behavior. The in-process / test path keeps auto-registering via `ensure_required_search_attributes_registered` (already in place in `tests/integration/pipelex/temporal/conftest.py`).

### Deliverable 1 — Configurable `[temporal.search_attributes]`

**Config schema.** Add a `SearchAttributesConfig` model to `pipelex/temporal/config_temporal.py`, wired onto `TemporalConfig`:

```toml
[temporal.search_attributes]
# Master toggle. When false: workflow starts don't attach any custom search
# attributes, the worker-boot check is skipped, and the dashboard view falls
# back to WorkflowType / WorkflowId / StartTime only.
enabled = true

# Subset of the five built-in attributes to populate. Names not in this list
# are skipped at workflow-start time AND not required at worker boot.
# Pipelex only knows how to populate these five; arbitrary custom names are
# out of scope (they would require code to know the value source).
attributes = ["PipeCode", "PipelineRunId", "SessionId", "UserId", "DomainCode"]
```

**Pydantic model.**

```python
class SearchAttributesConfig(ConfigModel):
    enabled: bool
    attributes: list[str]

    @model_validator(mode="after")
    def validate_attribute_names(self) -> Self:
        # The five built-ins live in namespace_check.BUILTIN_SEARCH_ATTRIBUTES.
        # Reject any unknown name with a helpful message — protects against
        # typos like "PipelineRunID" silently producing no attribute.
        ...
```

**Behavior changes in three call sites.**

- `pipelex/temporal/tprl/observability.py:build_search_attributes` — early-return `TypedSearchAttributes([])` when `enabled = false`. Otherwise, filter the five `SearchAttributePair`s by membership in `config.attributes`. Pull config via `get_config().temporal.search_attributes` (the helper is already called from sandbox-safe code paths; `get_temporal_manager()` is the existing precedent for sandbox imports in this module).
- `pipelex/temporal/tprl/namespace_check.py:check_required_search_attributes` — accept the configured subset (`list[str]`) as a parameter instead of reading `REQUIRED_SEARCH_ATTRIBUTES`. The hard-coded tuple stays in the module as `BUILTIN_SEARCH_ATTRIBUTES` (the union of all five Pipelex can populate) for validator + CLI use; the *runtime check* uses only the configured subset.
- `pipelex/temporal/temporal_task_manager.py:run_worker` — read `enabled` and `attributes` from config; skip the boot check entirely when `enabled = false`.

**Renaming.** `REQUIRED_SEARCH_ATTRIBUTES` → `BUILTIN_SEARCH_ATTRIBUTES` to reflect that "required" is now a function of config, not a constant.

### Deliverable 2 — Hard-fail worker boot on missing attributes

**Code anchors.**

- `pipelex/temporal/tprl/namespace_check.py:check_required_search_attributes` — today logs `log.warning(...)` and returns. Switch to raising a new exception (`SearchAttributeRegistrationError`, subclass of `TemporalConfigError`) when any *configured* attribute is missing AND the `ListSearchAttributes` call succeeds (i.e. it's a real namespace, not an unreachable one). The exact registration command — both the `pipelex setup-temporal-namespace` invocation **and** the equivalent `temporal operator search-attribute create` fallback — goes in the exception message.
- `RPCError` on the call itself stays a soft fail — the namespace was unreachable, not misconfigured. Keep the warning, don't raise. (In-process / time-skipping test servers don't trigger this path because the conftest pre-registers.)
- `pipelex/temporal/temporal_task_manager.py:run_worker` — the call site is already in place; only the failure mode changes. The exception propagates and crashes worker boot, which is the desired behavior. When `enabled = false`, the call is skipped entirely.
- The error message format must be copy-paste-ready: both the Pipelex CLI invocation and the raw `temporal` CLI command, on separate lines, so operators on either side of the fence can fix the gap.

### Deliverable 3 — `pipelex setup-temporal-namespace` CLI command

**Why a flat command, not a `pipelex temporal` group.** There is no `pipelex temporal` Typer sub-app today (just the single `pipelex worker` command). Adding a sub-app is a separate refactor; flat command keeps the diff focused on the search-attribute problem.

**Optional-dependency handling.** The `temporal` extra (`temporalio==1.23.0`, `aiohttp`) is optional — `pipelex` works without it for non-Temporal users. The new command follows the existing `worker_cmd` pattern:

- Module file `pipelex/cli/commands/setup_temporal_namespace_cmd.py` has **no** `pipelex.temporal.*` imports at module level — only `typer` and standard pipelex. This way `pipelex/cli/_cli.py` can import it unconditionally and `pipelex --help` works without the extra installed (verified by the same flow today for `pipelex worker`).
- All `pipelex.temporal.*` imports go inside the function body with `# noqa: PLC0415` — `temporal_connect`, `namespace_check`, anything else.
- Wrap the deferred import in `try/except ImportError` with a friendly `Install with: pip install pipelex[temporal]` message. (Strictly nicer than `worker_cmd` today, which lets the raw Python `ImportError` bubble. Optionally retrofit `worker_cmd` with the same handler — small bonus.)

**`BUILTIN_SEARCH_ATTRIBUTES` location.** The tuple of attribute names is referenced by the config validator in `SearchAttributesConfig`. If it lives in `pipelex/temporal/tprl/namespace_check.py` (current `REQUIRED_SEARCH_ATTRIBUTES`), the validator can't reference it without importing temporal at config-load time — defeating the optional-dep contract. **Move the tuple to `pipelex/temporal/config_temporal.py`** (which already only imports `temporalio` under `if TYPE_CHECKING:`, so it's safe to load without the extra). `namespace_check.py` imports it from there. The validator reads it locally.

**Command surface.**

```bash
# Default: read [temporal.temporal_config] from pipelex.toml, connect, register
# any missing configured attributes. Idempotent.
pipelex setup-temporal-namespace

# Print the equivalent `temporal operator search-attribute create` invocation
# without executing — useful for ops folks who need the namespace admin to
# register on their behalf.
pipelex setup-temporal-namespace --dry-run

# Target a non-default server profile.
pipelex setup-temporal-namespace --server testing
```

**Files touched.**

- `pipelex/cli/commands/setup_temporal_namespace_cmd.py` (new) — Typer command. Calls `make_pipelex_for_cli(temporal_enabled=True)`, connects via `connect_to_temporal_selected_server`, calls `ensure_required_search_attributes_registered`. On `RPCError(PermissionDenied)`, prints the fallback runbook (raw `temporal` CLI command, `tcld` for Cloud, Cloud UI link).
- `pipelex/cli/_cli.py` — register the new command alongside `worker_cmd`.
- `pipelex/temporal/tprl/namespace_check.py:ensure_required_search_attributes_registered` — accept a `configured_attributes: list[str]` parameter so the CLI registers only what config says is enabled. Test conftest call site keeps default = all five (passes `BUILTIN_SEARCH_ATTRIBUTES`).

**Permission-denied fallback.** Helper catches `RPCError` where `status == PERMISSION_DENIED` and returns a structured `RegistrationFailure` instead of raising — the CLI command formats it into the fallback runbook. Other RPC errors (`UNAVAILABLE`, `NOT_FOUND`) re-raise.

### Files touched (consolidated)

- `pipelex/temporal/config_temporal.py` — new `SearchAttributesConfig`, wired to `TemporalConfig`.
- `pipelex/pipelex.toml` — new `[temporal.search_attributes]` block with documented defaults.
- `.pipelex/pipelex.toml` (project template) — same block commented out as an override invitation, per project convention.
- `pipelex/temporal/tprl/observability.py:build_search_attributes` — filter by configured subset; early-return when disabled.
- `pipelex/temporal/tprl/namespace_check.py` — rename `REQUIRED_SEARCH_ATTRIBUTES` → `BUILTIN_SEARCH_ATTRIBUTES`; accept `configured_attributes` parameter; hard-fail instead of warning; permission-denied fallback in `ensure_required_search_attributes_registered`; new `SearchAttributeRegistrationError` exception.
- `pipelex/temporal/temporal_task_manager.py:run_worker` — gate the check on `enabled`; pass configured subset.
- `pipelex/cli/commands/setup_temporal_namespace_cmd.py` (new) — CLI command.
- `pipelex/cli/_cli.py` — wire the new command.
- `tests/integration/pipelex/temporal/conftest.py` — pass `BUILTIN_SEARCH_ATTRIBUTES` to the helper (no behavior change for tests, just makes the signature change explicit).
- `docs/under-the-hood/temporal-deployment.md` — full rewrite of the "soft fail" framing → "strict prerequisite + configurable + here's the easy registration command".
- `CHANGELOG.md` — replace the soft-fail line with the strict-prerequisite framing; add config block; add CLI command.

### Tests

- `tests/unit/pipelex/temporal/test_search_attribute_bootstrap_check.py` — rewrite:
    - "all present" → still no exception, no warning.
    - "some missing" → now `pytest.raises(SearchAttributeRegistrationError)` with both the `pipelex setup-temporal-namespace` invocation AND the raw `temporal operator search-attribute create` command in the message.
    - "`RPCError(UNAVAILABLE)`" → still soft-fails (warns, returns).
    - "non-`RPCError`" → propagates unchanged.
    - **New:** "configured subset" — only the subset is checked; missing built-ins outside the subset don't trigger the error.
    - **New:** "disabled" — `enabled = false` skips the check entirely (verify the operator service is never called).
- `tests/unit/pipelex/temporal/test_observability_helpers.py` — extend:
    - **New:** `enabled = false` → `build_search_attributes` returns empty `TypedSearchAttributes`.
    - **New:** `attributes = ["PipeCode", "DomainCode"]` → only those two pairs in the returned set.
- `tests/unit/pipelex/temporal/test_setup_temporal_namespace_cmd.py` (new) — exercise the CLI command with a mocked temporal client: happy path registers missing, dry-run prints without registering, permission-denied path prints the fallback runbook.
- `tests/unit/pipelex/temporal/test_search_attributes_config.py` (new) — config validator rejects unknown attribute names with a helpful error; default config matches the historic five.
- No integration test changes; the test path auto-registers before any workflow runs (Phase 4 fix).

### Done when

- `make agent-check` clean.
- `make agent-test` green.
- The full integration suite (`tests/integration/pipelex/temporal/`) still passes — the auto-registration in the test conftest keeps everything green there.
- A manual run against a real Temporal server with **no** attributes registered fails clean at worker boot with both registration commands in the error message. Running `pipelex setup-temporal-namespace` once, the worker then boots and dispatches succeed.
- Setting `[temporal.search_attributes] enabled = false` lets a worker boot against a namespace with zero custom attributes registered; workflows dispatch successfully (verified by the same `temporal-e2e-validate` flow with the toggle flipped).
- `pipelex setup-temporal-namespace --dry-run` prints the exact `temporal operator search-attribute create` command, including the configured subset.
- `docs/under-the-hood/temporal-deployment.md` documents: the configurable surface, the two registration paths (Pipelex CLI vs Temporal CLI), and the Cloud-specific runbook (`tcld` + UI), plus the permission model for self-managed workers on Temporal Cloud.
- `CHANGELOG.md` updated.

### Open questions (cold-start may need to decide)

- For Temporal Cloud customers running self-managed Pipelex workers, what permission level does the customer's API key need to call `OperatorService.AddSearchAttributes`? (Probably "Namespace Admin" — confirm against Cloud docs at implementation time and document in `temporal-deployment.md`.)
- Is there a sane fallback for `--temporal-server <profile>` integration test runs that point at a real cluster the developer doesn't have admin on? Likely: call `ensure_required_search_attributes_registered` in the conftest's real-server branch too, and tolerate `RPCError(PermissionDenied)` (warn and continue — the cluster admin will have done it). Decide when this case actually surfaces.
- Should the `enabled = false` mode also short-circuit the static summary / static details (which are independent of search attributes today)? Probably no — those are orthogonal observability features and may be useful even when filtering is disabled. Leave them on; only search attributes are gated by this toggle.

### Checkpoint — end of Phase 6

- **Status.** Implementation complete on `feature/Temporal-ids`. `make agent-check` clean, `make agent-test` green, 561 targeted unit tests pass in `tests/unit/pipelex/temporal/` + `tests/unit/pipelex/cli/` + `tests/unit/pipelex/system/`.

- **Behavior change confirmed.** Worker boot now hard-fails on a reachable namespace when a configured custom search attribute is missing (raises `SearchAttributeRegistrationError` with both the `pipelex setup-temporal-namespace` invocation and the equivalent raw `temporal operator search-attribute create` command in the message). `RPCError` from the operator service stays a soft fail. `[temporal.search_attributes].enabled = false` skips both the check and the per-workflow attachment. In-process / time-skipping test servers continue to auto-register via the conftest, now passing `BUILTIN_SEARCH_ATTRIBUTES` through the helper's new `configured_attributes` parameter. The new `pipelex setup-temporal-namespace` CLI command was smoke-tested with `--dry-run` and prints the exact `temporal operator search-attribute create` invocation for the resolved namespace + the Cloud `tcld` fallback.

- **What landed.**
    - `pipelex/temporal/config_temporal.py` — new `SearchAttributesConfig` model + `BUILTIN_SEARCH_ATTRIBUTES` tuple. The constant lives here (not in `namespace_check.py`) so the validator can reference it without pulling `temporalio` into the config-load path. `Temporal` gains a `search_attributes: SearchAttributesConfig` field.
    - `pipelex/pipelex.toml` — new `[temporal.search_attributes]` block (enabled = true, all five attributes). `.pipelex/pipelex.toml` template ships the same block commented out as an override invitation.
    - `pipelex/temporal/tprl/namespace_check.py` — `REQUIRED_SEARCH_ATTRIBUTES` removed; helpers now take `configured_attributes: Sequence[str]`. `check_required_search_attributes` raises `SearchAttributeRegistrationError` instead of warning when configured attributes are missing on a reachable namespace. `ensure_required_search_attributes_registered` returns a structured `RegistrationFailure` dataclass on `RPCError(PERMISSION_DENIED)` instead of raising, so the CLI command can format the fallback runbook. Other `RPCError` codes propagate. Empty `configured_attributes` short-circuits both helpers.
    - `pipelex/temporal/exceptions.py` — new `SearchAttributeRegistrationError(TemporalConfigError)`.
    - `pipelex/temporal/tprl/observability.py` — `build_search_attributes` early-returns `TypedSearchAttributes([])` when `enabled = false`, otherwise filters the five `SearchAttributePair`s by `config.attributes`. The five workflow-start call sites in `tprl_pipe/` inherit the filter automatically.
    - `pipelex/temporal/temporal_task_manager.py` — `run_worker` gates the bootstrap check on `enabled` and passes the configured subset.
    - `pipelex/cli/commands/setup_temporal_namespace_cmd.py` (new) — Typer command. `--dry-run` prints the equivalent raw `temporal` CLI command + the Cloud `tcld` runbook. `--server <profile>` targets a non-default profile. Permission-denied path prints the actionable fallback and exits with code 1. Module-level imports stay pure-pipelex; all `pipelex.temporal.*` imports are deferred inside the function body (carrying `# noqa: PLC0415`) and wrapped in a `try/except ImportError` so `pipelex --help` works without the `temporal` extra.
    - `pipelex/cli/_cli.py` — registers the new command next to `pipelex worker`, appended to `list_commands` order.
    - `tests/integration/pipelex/temporal/conftest.py` + `test_payload_codec_pipeline.py` — three integration call sites of the helper now pass `BUILTIN_SEARCH_ATTRIBUTES` explicitly.
    - `tests/unit/pipelex/temporal/test_search_attribute_bootstrap_check.py` — rewritten for the hard-fail contract (six cases: all-present silent, some-missing raises with both commands, RPC soft-fail, non-RPC propagation, configured-subset, disabled).
    - `tests/unit/pipelex/temporal/test_observability_helpers.py` + `test_search_attribute_dict_construction.py` — extended with `enabled = false` and partial-subset cases; existing tests patch `get_config` via a new module-local fixture.
    - `tests/unit/pipelex/temporal/test_search_attributes_config.py` (new) — config validator rejects unknown attribute names; default config matches the historic five.
    - `tests/unit/pipelex/cli/test_setup_temporal_namespace_cmd.py` (new) — CLI command unit tests: dry-run, happy-path, permission-denied fallback, disabled short-circuit, unknown-server-profile.
    - `tests/unit/pipelex/temporal/test_temporal_config_warnings.py` — `_make_temporal_config` helper passes the new `search_attributes=SearchAttributesConfig(...)` arg.

- **Docs + CHANGELOG synced.** `docs/under-the-hood/temporal-deployment.md` was fully rewritten away from the "soft fail" framing into "strict prerequisite + configurable surface + two registration paths + permission model for Temporal Cloud self-managed workers". `CHANGELOG.md` replaces the soft-fail line under [Unreleased] with the strict-prerequisite framing and adds two new entries for the config block and the CLI command.

- **Promotion.** `namespace_check._format_registration_command` → `format_temporal_cli_command` (public) because the CLI command now also calls it. Implementation unchanged.

- **Open questions resolved during implementation.**
    - **Temporal Cloud permission model.** Documented in `temporal-deployment.md` as "the customer's namespace admin owns `OperatorService.AddSearchAttributes`; the worker API key typically doesn't have it." `pipelex setup-temporal-namespace` handles `RPCError(PERMISSION_DENIED)` by printing the exact `temporal` / `tcld` / Cloud UI commands the admin needs to run.
    - **Static summary / static details independence.** Confirmed orthogonal to the search-attribute toggle. `build_static_summary` / `build_static_details` are not gated by `[temporal.search_attributes].enabled`.
    - **Custom attribute names beyond the five built-ins.** Out of scope (per the design). The config validator rejects them with a helpful message listing the five known names.

- **Known follow-ups (deferred).**
    - Verifying the hard-fail path against a real Temporal cluster with `--temporal-server <profile>` (using `/temporal-e2e-validate`) was not run as part of this checkpoint — the unit suite covers the hard-fail contract via mocked clients, and the integration test path keeps the in-process server registered by the conftest. Run the e2e slash command once a real-cluster credential is available.
    - The `enabled = false` end-to-end path was not run on a real cluster either. The unit tests verify the bootstrap check is skipped and `build_search_attributes` returns empty; the workflow-start call sites all delegate to `build_search_attributes`, so the propagation is by construction.

---

## Cross-phase risks and mitigations

- **~~Integration tests that asserted on workflow_id shape.~~** **VACATED.** A grep at design time confirmed zero existing tests assert on the `{session5}-{rand5}-{ClassName}` shape. No transitional handling needed in Phase 1; no test rewrites needed in Phase 3 beyond the new files.
- **~~`make_top_workflow_id` callers outside `WorkflowExecutor`.~~** **VACATED.** A grep confirms exactly one production caller (`WorkflowExecutor.make_workflow_id` at `workflow_caller.py:85`). Phase 1's rename covers it.
- **Namespace registration in CI.** CI's in-process Temporal server skips search-attribute registration. Phase 4's bootstrap check still calls `DescribeNamespace` on every worker boot, including in-process test workers — verify whether the in-process server raises `RPCError` (covered by Phase 4's soft-fail path) or returns an empty/synthetic namespace description. If the latter, decide in Phase 4 whether the warning level should be downgraded for in-process mode specifically (detect via `temporal_server_config` or absence of a real namespace) to keep CI logs clean.
- **Replay-safety regression.** The deletion of the LRU + `is_replaying()` short-circuit is correct *because* the disambiguator stops coming from worker-singleton state. If a future change re-introduces worker-singleton state into the activity dispatch path, the determinism guarantee breaks. Phase 2's PR description calls this out so reviewers know to push back on any reintroduction.
- **~~`pipe_job.pipe.code` empty in pathological inputs.~~** **VACATED.** `PipeAbstract.code: str` is a required Pydantic field with `validate_pipe_code_syntax` non-empty validation. No fallback in Phase 3; trust the invariant. If invariants ever change, the resulting crash points cleanly at the bug instead of hiding it behind a silently-degraded workflow id.

## Test plan (cumulative across phases)

By the end of Phase 4, the following must be green:

- All existing `make agent-test` tests.
- The renamed TDD gate test in `test_default_activity_id_collision_bug.py` (`test_two_default_activity_calls_in_one_workflow_produce_distinct_activity_ids`).
- New unit tests added in Phase 1: `test_observability_helpers.py` (helper formats + truncation + child-attr inheritance) and `test_workflow_caller_passthrough.py` (the four kwargs reach the SDK on all four entry points: `execute_workflow` / `start_workflow` / `execute_child_workflow` / `start_child_workflow`).
- Rewritten / deleted tests in Phase 2 — see the explicit per-test enumeration in Phase 2 above. The deletions include the entire `test_seen_activity_ids_lru.py` file.
- New unit tests added in Phase 3: `test_workflow_id_construction.py` (top-level shape per RunMode + fixed-role child + dynamic child + **replay-determinism with mocked `workflow.uuid4`**) and `test_search_attribute_dict_construction.py` (five keys + child inheritance rules).
- New unit test added in Phase 4: `test_search_attribute_bootstrap_check.py` (three cases: all present, some missing, `DescribeNamespace` raises `RPCError`).
- The Temporal integration test suite (`tests/integration/pipelex/temporal/`) with `--temporal-server local` and `--temporal-server testing` profiles for the dev environments that have those configured.
- The `temporal-e2e-validate` skill against a real Temporal server with the five search attributes registered.

## Decisions settled inline (formerly "open questions")

These were deferred during the design phase; review settled them so the implementer does not re-open them. Captured here as a paper trail.

- **Helper module location.** `pipelex/temporal/tprl/observability.py`. No reason to bikeshed.
- **One canonical gate test vs two.** **Keep one, delete the other** (Phase 2 above). The kept test is renamed to `test_two_default_activity_calls_in_one_workflow_produce_distinct_activity_ids` so its name reflects the invariant being guarded, not the historic bug.
- **`pipe_job.pipe.code or "pipe"` fallback.** **No fallback** (Phase 3 above). `code: str` is required-non-empty by Pydantic + `validate_pipe_code_syntax`; the fallback is dead code; silently swallowing an invariant violation is worse than crashing.
- **Static details "Input" line.** **Use `pipe_job.pipe.inputs.specs` keys** (Phase 3 above). Working-memory keys rejected because they grow at runtime and are sub-pipe-dependent.
- **Soft-fail warning in CI for in-process server.** **Decide in Phase 4** based on whether the in-process server returns `RPCError`, an empty namespace, or a synthetic one. Two acceptable answers — suppress the warning entirely in in-process mode, or downgrade its level. Either is fine; CI log cleanliness is the deciding criterion.

## Out of scope (per the design doc + this review)

These do **not** ship in this plan. They are listed here so they don't accidentally creep in:

- `workflow.set_current_details(...)` for in-flight progress.
- Memo population beyond the optional `library_crate` fingerprint.
- Per-pipe Workflow Type registration.
- Search attribute schema versioning / migration tooling.
- An optional `display_label` parameter at the `PipeRun` entry point.
- **Unifying the two child-spawn paths.** Out of scope (correctly). A Phase 5 follow-up briefly routed both `wf_pipe_run.py` and `temporal_pipe_router.py` through `WorkflowExecutor.execute_child_workflow(...)`; the Phase 6 follow-up reverted it because `WorkflowExecutorFactory.create_executor` reads config to seed `execution_timeout` / `retry_policy` / etc., which would bake config-derived values into the recorded `StartChildWorkflowExecution` command and break replay determinism after any config change. Both call sites now use `workflow.execute_child_workflow(...)` directly and wrap `ChildWorkflowError` as `WorkflowExecutionError` in-place. See "Phase 5 follow-up — Child-spawn path unification (reverted)" above for the full rationale.
- **`WorkflowIDReusePolicy` choice.** Stays at SDK default `ALLOW_DUPLICATE`. A separate decision (later) is whether `REJECT_DUPLICATE` would catch double-execution bugs at the Temporal layer once workflow IDs are deterministic from `pipeline_run_id`.
