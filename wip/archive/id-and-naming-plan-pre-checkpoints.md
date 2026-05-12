# Temporal IDs and Naming — Implementation Plan

## Status

Plan ready. Implements `id-and-naming-design.md` against the failing TDD gate in `tests/unit/pipelex/temporal/test_default_activity_id_collision_bug.py`. Aligned with the problem statement in `workflow-and-activity-ids.md` and the primitives reference in `temporal-id-primitives.md`.

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

The phase ordering is chosen so that the bug fix (Phase 2) lands as early as possible: foundations first, then the activity-layer rewrite that flips the TDD gate green, then the workflow-layer rewrite, then deployment & docs. Phases 3 and 4 can be reordered or parallelized if needed; Phases 1 and 2 must run in this order.

Each phase section answers the same four questions: **What lands**, **Files touched**, **Tests**, **Done when**. The change set in the design doc is the authoritative spec for every file change — this plan only sequences the work.

---

## Phase 1 — Foundations (additive only)

**What lands.** A new `observability.py` helper module, a renamed/simplified `make_top_workflow_id` on `TemporalManager`, and additive `search_attributes` / `static_summary` / `static_details` / `memo` parameters on `WorkflowExecutor.execute_workflow` / `start_workflow`. No call site uses the new infrastructure yet. No behavior changes for end users.

**Files touched.**

- `pipelex/temporal/tprl/observability.py` (new) — five pure-function helpers:
    - `build_search_attributes(pipe_job: PipeJob) -> Mapping[str, list[str]]`
    - `build_search_attributes_for_child(child_pipe_job: PipeJob, parent_search_attrs: Mapping[str, list[str]]) -> Mapping[str, list[str]]`
    - `build_static_summary(pipe: PipeBase) -> str`
    - `build_static_details(pipe_job: PipeJob, library_crate_id: str | None) -> str`
    - `build_activity_summary(method_label: str, job_metadata: JobMetadata, **extras: str) -> str`
- `pipelex/temporal/temporal_manager.py` — replace `make_top_workflow_id(base_id: str)` with `make_top_workflow_id(pipeline_run_id: str)`. The session-id and random-id truncations are deleted; `self.session_id` stays as an instance field so the search-attribute helper can read it.
- `pipelex/temporal/tprl/workflow_caller.py` — `WorkflowExecutor.execute_workflow` / `start_workflow` gain optional `search_attributes`, `static_summary`, `static_details`, `memo` parameters that pass through to the Temporal SDK. `make_workflow_id(base_id: str)` is renamed to `make_workflow_id(pipeline_run_id: str)`.

**Tests.**

- `tests/unit/pipelex/temporal/test_observability_helpers.py` (new) — unit tests for every helper, including 200-byte UTF-8 truncation behavior, `pipe.description` absent/present, child-attribute inheritance.
- Existing tests using the old `make_top_workflow_id(base_id=...)` signature update to the new parameter name. The only legitimate caller in production code is `WorkflowExecutor.make_workflow_id`, and that's the same change. Tests that asserted on the old `{session5}-{rand5}-{base_id}` shape are tagged for rewrite in Phase 3 — for now they continue to assert the (transitional) format the manager produces.

**Done when.**

- `make agent-check` clean.
- `make agent-test` green. The TDD gate test in `test_default_activity_id_collision_bug.py` is still red (expected — Phase 2 fixes it).
- The new helpers have unit-test coverage for the formats specified in the design doc.

### Checkpoint — end of Phase 1

To be filled in by the implementer at the phase boundary so the next session can pick up cleanly.

- **Status.** _(planned / in progress / merged)_
- **PR / branch.** _(URL)_
- **Code state.** _(any deviations from this plan, helper function signatures actually shipped, edge cases discovered)_
- **Open questions deferred.** _(any decisions that surfaced during implementation that we punted)_
- **Handoff notes for Phase 2.** _(anything Phase 2 needs to know: gotchas in helper APIs, conftest changes that affect downstream test layout, etc.)_

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
- `pipelex/cogt/content_generation/content_generator.py` (direct mode) — drop `wfid`.
- `pipelex/cogt/content_generation/content_generator_dry.py` (dry mode) — drop `wfid`.

**Tests.**

- `tests/unit/pipelex/temporal/test_default_activity_id_collision_bug.py` — flips green. The second test (`test_two_make_llm_text_calls_with_same_explicit_wfid_should_succeed`) cannot pass `wfid` anymore; it collapses into the first test and either is deleted or kept as a duplicate regression gate (recommend keeping one canonical gate test, deleting the other).
- `tests/unit/pipelex/temporal/test_content_generator_in_workflow.py`:
    - Delete `test_make_llm_text_threads_explicit_wfid`, `test_duplicate_wfid_raises_content_generation_error`, `test_default_wfids_for_image_methods_are_distinct`.
    - Add `test_make_llm_text_omits_activity_id_and_sets_summary` (and equivalents per method) — asserts `mock_execute.call_args.kwargs.get("activity_id") is None` and `summary` matches the formatted helper output.
- Any other test in `tests/unit/` / `tests/integration/` that passes `wfid=` to a `make_*` content-generator method is updated to remove the kwarg.

**Done when.**

- `make agent-check` clean.
- `make agent-test` green.
- `test_default_activity_id_collision_bug.py` is green.
- Grep confirms zero remaining references to `wfid` in `pipelex/cogt/` and `pipelex/temporal/tprl_content_generation/`.
- Manual smoke (optional, recommended): run a multi-step pipe via the `temporal-e2e-validate` skill and confirm in the Temporal dashboard's Event History that activity ids are now `"1"`, `"2"`, … with purple-text per-activity summaries.

### Checkpoint — end of Phase 2

To be filled in by the implementer at the phase boundary.

- **Status.** _(planned / in progress / merged)_
- **PR / branch.** _(URL)_
- **TDD gate.** _(confirmed green: yes/no, link to CI run)_
- **Code state.** _(LRU deletion confirmed, residual TODOs, anything surprising about the existing tests that touched wfid)_
- **Open questions deferred.** _(e.g. should we keep one or both of the test_default_activity_id_collision_bug cases as the canonical gate?)_
- **Handoff notes for Phase 3.** _(state of pipe_run/* protocols — still carrying wfid as no-op; state of temporal_pipe_run/router — still using old workflow_id shape and still threading wfid)_

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
    - Child branch: `child_workflow_id = f"{parent_workflow_id}/{pipe_job.pipe.code}-{str(workflow.uuid4())[:8]}"`. Pass `search_attributes` updated for the child via `build_search_attributes_for_child`.
- `pipelex/temporal/tprl_pipe/wf_pipe_run.py`:
    - Line 46: switch the separator from `-` to `/`: `id=f"{workflow.info().workflow_id}/pipe-router"`.
    - Pass `search_attributes=` (re-using the parent's, since the child is the same pipe) to the `execute_child_workflow` call.
- `pipelex/pipe_run/pipe_run.py` and `pipe_run_protocol.py` — drop `wfid` from `run(...)`.
- `pipelex/pipe_run/pipe_router.py`, `pipe_router_protocol.py`, `dry_pipe_router.py` — drop `wfid` from `run(...)` / `_run_pipe_job(...)`.
- Any remaining call sites of these protocols in tests update to not pass `wfid`.

**Tests.**

- `tests/unit/pipelex/temporal/test_workflow_id_construction.py` (new) — asserts:
    - Top-level: `{env_prefix}{pipeline_run_id}` for each `RunMode`.
    - Fixed-role child: `{parent}/pipe-router`.
    - Dynamic child: `{parent}/{pipe_code}-{8-hex-chars}`.
- `tests/unit/pipelex/temporal/test_search_attribute_dict_construction.py` (new) — asserts the five-keyed dict from a representative `pipe_job`, plus the child-attribute inheritance / override rule.
- Existing tests that asserted the old workflow_id shape (`{session5}-{rand5}-{ClassName}`) are rewritten to assert the new shape.
- Integration tests under `tests/integration/pipelex/temporal/` continue to pass without modification (they don't inspect the workflow_id shape); if any does, it's rewritten.
- Run the `temporal-e2e-validate` skill end-to-end as a final cross-check.

**Done when.**

- `make agent-check` clean.
- `make agent-test` green.
- Grep confirms zero remaining `wfid` references in `pipelex/`.
- A manual run in the Temporal dashboard shows: top-level workflow ID = the `pipeline_run_id` (with env prefix); child workflow IDs are slash-separated paths; the `PipeCode`, `PipelineRunId`, `SessionId`, `UserId`, `DomainCode` search attributes are populated on every workflow row; static summary shows `{pipe_code} — {description}`.

### Checkpoint — end of Phase 3

To be filled in by the implementer at the phase boundary.

- **Status.** _(planned / in progress / merged)_
- **PR / branch.** _(URL)_
- **Code state.** _(all wfid removed, workflow_id shape live, dashboard verified)_
- **Operational notes.** _(in test runs, did the soft-fail warning for unregistered search attributes fire? Anything in the integration test suite that needs adjusting for the new dashboard expectations?)_
- **Open questions deferred.** _(e.g. did we settle on whether to delete one of the two TDD gate tests, the dynamic-child uuid8 length, etc.)_
- **Handoff notes for Phase 4.** _(state of search attribute coverage; whether any namespace has been pre-registered with the five attributes; what the deployment runbook needs to cover)_

---

## Phase 4 — Deployment hooks, docs, CHANGELOG

**What lands.** A bootstrap soft-fail check that warns when required custom search attributes are missing on the namespace. A new docs section explaining the one-time registration step. A CHANGELOG entry covering every breaking change.

**Files touched.**

- `pipelex/temporal/temporal_task_manager.py` (or wherever the worker boot lives) — add a `DescribeNamespace` call on worker start; if any of the five attributes is missing, log a warning that includes the exact `temporal operator search-attribute create` command. Soft fail only — in-process test servers and dev environments without registration continue to run.
- `docs/temporal-deployment.md` (new) — section on required custom search attributes and how to register them. Cross-link from any existing Temporal-related docs.
- `CHANGELOG.md` — `[Unreleased]` entry covering:
    - Workflow ID shape change (`{env}{session5}-{rand5}-{ClassName}` → `{env_prefix}{pipeline_run_id}`).
    - Child workflow ID separator change (`-` → `/`).
    - Activity ID change (semantic labels → SDK-default integers).
    - `wfid` parameter removed from `PipeRunProtocol`, `PipeRouterProtocol`, `ContentGeneratorProtocol`, and every implementation.
    - New required custom search attributes on the Temporal namespace.

**Tests.**

- `tests/unit/pipelex/temporal/test_search_attribute_bootstrap_check.py` (new) — mocks `DescribeNamespace` to return (a) all attributes present (no warning), (b) some missing (warning logged with exact command).

**Done when.**

- `make agent-check` clean.
- `make agent-test` green.
- Docs preview renders the new section.
- CHANGELOG entry written in the project's voice (one line per breaking change is fine).
- `temporal-e2e-validate` skill run on a clean namespace (without the attributes registered) emits the warning; with attributes registered, runs cleanly.

---

## Cross-phase risks and mitigations

- **Integration tests that asserted on workflow_id shape.** Scan early (during Phase 1) for tests that match on workflow_id substrings. Catch them in the right phase rather than waiting for CI breakage.
- **`make_top_workflow_id` callers outside `WorkflowExecutor`.** A grep confirms there is exactly one production caller (`WorkflowExecutor.make_workflow_id`). If a stray caller is found, update it in Phase 1.
- **Namespace registration in CI.** CI's in-process Temporal server skips search-attribute registration. Confirm in Phase 4 that the soft-fail warning is downgraded (or suppressed entirely) for the in-process server mode — otherwise CI logs fill with the warning.
- **Replay-safety regression.** The deletion of the LRU + `is_replaying()` short-circuit is correct *because* the disambiguator stops coming from worker-singleton state. If a future change re-introduces worker-singleton state into the activity dispatch path, the determinism guarantee breaks. Phase 2's PR description calls this out so reviewers know to push back on any reintroduction.
- **`pipe_job.pipe.code` empty in pathological inputs.** The child workflow ID format depends on `pipe_job.pipe.code` being non-empty. Add a defensive fallback (`pipe_job.pipe.code or "pipe"`) in `temporal_pipe_router.py` if a unit test exercises an empty-code path; otherwise rely on existing invariants.

## Test plan (cumulative across phases)

By the end of Phase 4, the following must be green:

- All existing `make agent-test` tests.
- The TDD gate tests in `test_default_activity_id_collision_bug.py`.
- The new unit tests added in Phases 1, 3, 4 (observability helpers, workflow_id construction, search attribute dict, bootstrap check).
- The Temporal integration test suite (`tests/integration/pipelex/temporal/`) with `--temporal-server local` and `--temporal-server testing` profiles for the dev environments that have those configured.
- The `temporal-e2e-validate` skill against a real Temporal server with the five search attributes registered.

## Open questions deferred to implementation

Captured here so they are not lost between sessions. Each can be settled inside the relevant phase without re-opening the design.

- **Helper module location.** `pipelex/temporal/tprl/observability.py` is the proposed home. If existing structure in `pipelex/temporal/` suggests a different submodule (e.g. `pipelex/temporal/identity/`), the implementer picks; the design does not depend on the path.
- **One canonical gate test vs two.** The two failing tests in `test_default_activity_id_collision_bug.py` collapse into one after Phase 2 (`wfid` parameter gone, so they exercise the same code path). Keep one, delete the other.
- **`pipe_job.pipe.code or "pipe"` fallback.** Decide in Phase 3 whether a defensive fallback is warranted or whether the existing invariants make it dead code.
- **Static details "Input" line.** The design says "best-effort, omit when unavailable." The implementer picks the exact derivation (working_memory keys list, pipe inputs blueprint, etc.) — whatever is cheapest and least likely to grow over time.
- **Soft-fail warning in CI.** Whether to suppress the warning entirely for the in-process test server or just downgrade its level. Decide in Phase 4 based on actual CI log noise.

## Out of scope (per the design doc)

These do **not** ship in this plan. They are listed here so they don't accidentally creep in:

- `workflow.set_current_details(...)` for in-flight progress.
- Memo population beyond the optional `library_crate` fingerprint.
- Per-pipe Workflow Type registration.
- Search attribute schema versioning / migration tooling.
- An optional `display_label` parameter at the `PipeRun` entry point.
