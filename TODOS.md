# TODOS — Queue options and worker-runtime profiles (Temporal v2)

> **What this is:** A living, self-contained execution plan for the next Temporal config iteration. Open this file in a fresh session and you should have everything you need to pick up at the lowest unchecked checkpoint.
>
> **Status:** Design ready for implementation. Phase 0 not yet started.

---

## Cold-start orientation

### What we're building

A two-axis expansion of the Temporal config surface, building on v1's per-activity queue routing (already shipped on `feature/Per-activity-queue`):

1. **Submitter-side per-queue options.** Activity `start_to_close_timeout`, `retry_policy`, and `heartbeat_timeout` become attached to the queue name (because the queue represents the backend), with rare per-handle overrides for special cases. Replaces today's "one set of values for every activity" pattern.
2. **Worker-side named runtime profiles.** Concurrency slots, pollers, and rate-limit knobs (currently hardcoded in `make_worker`) become named profiles selectable per worker process via `--profile`. Enables deployment manifests with N differently-shaped workers against different queues.

### Why

- Today every dispatch site uses `worker_config.workflow_execution_timeout` (a workflow-level concept) as the activity `start_to_close_timeout`. Result: 1h budget on a jinja2 render, same 1h on a slow PDF extract. One number, both wrong.
- Worker tuning (`max_concurrent_activities=1000`, rate limits, pollers) is hardcoded in `temporal_task_manager.py:120-138`. A deployment with a small GPU pool sitting next to a high-throughput Anthropic pool cannot be expressed.
- "Worker config" today mixes submitter-side defaults with one worker-side field — splitting these into orthogonal sections makes both usable.

### Where the full context lives

- **Design doc** (read this first if you have any architecture question): `wip/temporal-primitives/queue-options-and-worker-profiles.md`. The "Decisions taken" banner at the top is authoritative.
- **v1 predecessor design** (for the existing routing model this builds on): `wip/temporal-primitives/per-activity-queue-routing-v1.md`.
- **Current code:**
  - Config: `pipelex/temporal/config_temporal.py`, `pipelex/pipelex.toml`, `pipelex/.pipelex/pipelex.toml`
  - Hardcoded knobs to lift: `pipelex/temporal/temporal_task_manager.py:120-138`
  - Dispatch sites: `pipelex/temporal/tprl_content_generation/content_generator_in_workflow.py`
  - Dead code (delete in Phase 0): `pipelex/temporal/wrapper/activity.py`

### Decisions already taken (do NOT re-debate)

1. **Per-queue options layering** (Hybrid C from the analysis): queue is the primary unit for timeouts and retries. Per-handle overrides exist but are sparingly used.
2. **Worker tuning** moves to named `worker_runtime_profiles`. Submitter-side `worker_config` stays singular.
3. **Both rate-limit knobs ship**: `max_activities_per_second` (worker-local) on the profile; `max_task_queue_activities_per_second` (cluster-wide, server-enforced) on the queue's options.
4. **Heartbeat** field lives on `QueueOptions` only, not `HandleOptions`. Heartbeat *call sites* are out of scope for v2 — schema is ready but no current activity actually emits heartbeats yet. See the "Heartbeats — deferred" section in the design doc.
5. **`non_retryable_error_types`** composes **additively** across baseline → queue → handle. Per-queue/per-handle layers contribute `non_retryable_error_types_extra` lists.
6. **Startup validation:** WARN on routing entries that name unknown queues (lenient); FAIL when `pipelex worker --task-queue X` names a queue absent from routing/options/default (strict, with "did you mean?" suggestion).
7. **Resource-based tuning** is reserved as `WorkerTuningMode.RESOURCE_BASED` in the enum but rejected by a model_validator until a future iteration ships it.
8. **No per-worker `--server` flag.** Process-wide `selected_server` stays the only knob.
9. **Resolver tracing** behind a new `temporal_log_config.is_dispatch_resolution_traced` flag, off by default.
10. **`pipelex/temporal/wrapper/activity.py`** has zero callers — delete in Phase 0, do not migrate.

### Branch convention

`feature/Queue-options-and-worker-profiles` off `feature/Per-activity-queue` (or off `main` once v1 lands there). One PR per logical phase is fine; ship them in order.

### Universal gates

Every phase ends with:

- [ ] `make agent-check` green
- [ ] `make agent-test` green
- [ ] `make tb` green if TOML or `config_temporal.py` shape changed (boot smoke test)

If any of these fails, the phase is not done. No skipping.

---

## First actions (run these at the start of every session)

1. `git branch --show-current` — confirm the branch matches "Branch convention" above.
2. `grep -rn "start_tprl_activity\|inference_task_queue" pipelex/ tests/` — sanity check. `inference_task_queue` should return zero (v1 cleanup landed). `start_tprl_activity` should appear only in `wrapper/activity.py` until Phase 0 is done.
3. Scroll to the lowest `**Status:** ☐ not started` checkpoint in this file — that's where you're picking up.
4. If a previous session ended mid-phase, the "Notes" under the phase will say what's done and what's next.
5. Re-read the "Decisions already taken" list above before making any new judgment calls.

---

## Phase 0 — Cleanup

**Goal:** Remove dead code. Tiny.

### Tasks

- [ ] Confirm zero callers: `grep -rn "start_tprl_activity" pipelex/ tests/` returns only the definition site.
- [ ] Delete `pipelex/temporal/wrapper/activity.py`.
- [ ] Delete `pipelex/temporal/wrapper/__init__.py` if it has no other exports.
- [ ] Delete the `pipelex/temporal/wrapper/` directory if empty.
- [ ] Universal gates pass.

### Status

☐ not started

---

## Phase 1 — Schema scaffolding (no behavior change)

**Goal:** Land the new TOML shape and Pydantic models. Runtime behavior unchanged — dispatch sites still use `worker_config.workflow_execution_timeout` directly. Config-only diff so it's reviewable in isolation.

### Tasks — config models (`pipelex/temporal/config_temporal.py`)

- [ ] `WorkerTuningMode` (`StrEnum`): `EXPLICIT`, `RESOURCE_BASED`.
- [ ] `WorkerRuntimeProfile` model (all fields per design doc) with `@model_validator(mode="after")` that match-cases on `tuning_mode` and raises `TemporalConfigError` for `RESOURCE_BASED`.
- [ ] `WorkerRuntimeProfilesConfig` (`default_profile`, `profiles`) with validator that `default_profile in profiles`.
- [ ] `QueueOptions` (all timeouts + `retry_policy_config` + `max_task_queue_activities_per_second`).
- [ ] `HandleOptions` (only `start_to_close_timeout` + `retry_policy_config`).
- [ ] Extend `ActivityRouteConfig` with `handle_options: dict[str, HandleOptions]`.
- [ ] Extend `RetryPolicyConfig` with `non_retryable_error_types_extra: list[str]`. (Merge happens in Phase 2; just add the field here.)
- [ ] Modify `WorkerConfig`:
  - Rename `task_queue` → `default_task_queue`.
  - Add `default_activity_start_to_close_timeout`.
  - Add `default_activity_heartbeat_timeout` (Optional, default None).
- [ ] Add `is_dispatch_resolution_traced: bool` to `TemporalLogConfig`.
- [ ] Modify top-level `Temporal`: add `queue_options`, `worker_runtime_profiles`.

### Tasks — TOML defaults (`pipelex/pipelex.toml`)

- [ ] Rename `[temporal.worker_config].task_queue` → `default_task_queue`.
- [ ] Add `default_activity_start_to_close_timeout = "0:10:00"` baseline.
- [ ] Add `is_dispatch_resolution_traced = false` under `[temporal.temporal_config.temporal_log_config]`.
- [ ] Add `non_retryable_error_types_extra = []` to baseline `[temporal.worker_config.retry_policy_config]`.
- [ ] Add `[temporal.worker_runtime_profiles]` with `default_profile = "default"`.
- [ ] Add `[temporal.worker_runtime_profiles.profiles.default]` with values **lifted verbatim from `temporal_task_manager.py:120-138`**:
  - `tuning_mode = "explicit"`, `max_cached_workflows = 10000`, `max_concurrent_workflow_tasks = 1000`, `max_concurrent_activities = 1000`, `max_concurrent_local_activities = 1000`, `max_concurrent_workflow_task_polls = 100`, `max_concurrent_activity_task_polls = 100`, `max_activities_per_second = 1000`, `sticky_queue_schedule_to_start_timeout = "0:30:00"`, `max_heartbeat_throttle_interval = "1:00:00"`, `default_heartbeat_throttle_interval = "1:00:00"`, `graceful_shutdown_timeout = "0:30:00"`.
- [ ] Add empty `[temporal.queue_options]` section (workers fall back to baseline when no entry).

### Tasks — Client override examples (`pipelex/.pipelex/pipelex.toml`)

- [ ] Rename `task_queue` → `default_task_queue` (active settings and any commented examples).
- [ ] Add commented examples for `[temporal.queue_options.<name>]` and `[temporal.worker_runtime_profiles.profiles.<name>]` (Anthropic, OpenAI, image-gen-heavy, jinja2-burst, router). Leave commented — clients enable per deployment.

### Tasks — Migration

- [ ] Add `[migration.migration_maps.temporal]` entry renaming `task_queue` → `default_task_queue`.
- [ ] Verify by running `make tb` against a config that still uses the old key.

### Tasks — Existing tests to update

- [ ] `tests/unit/pipelex/temporal/test_worker_config_resolve_queue.py` — fixtures use `default_task_queue`.
- [ ] `tests/unit/pipelex/temporal/test_worker_config_toml_parsing.py` — fixtures updated; add coverage for `handle_options` parsing.
- [ ] `tests/unit/pipelex/temporal/test_content_generator_in_workflow.py` — fixtures updated.
- [ ] Sweep: `grep -rn "worker_config\.task_queue\b\|\"task_queue\"" pipelex/ tests/` and fix every hit.

### Universal gates

- [ ] Pass.

### 📍 CHECKPOINT 1 — Schema landed, runtime unchanged

**When you reach this:** Flip the Status line to `✅ done — YYYY-MM-DD — PR #NNNN`. Add a Notes subsection if anything deviated.

**Pickup brief for the next session:** Pydantic models parse the new TOML. Existing tests still pass because dispatch sites use the OLD field paths inside `content_generator_in_workflow.py`. Phase 2 begins by writing the resolver and switching dispatch sites over.

**Status:** ☐ not started

---

## Phase 2 — Submitter-side resolution chain

**Goal:** Build the per-queue / per-handle options resolver, switch every dispatch site over, fix the `workflow_execution_timeout`-as-activity-timeout bug along the way.

### Tasks — Resolver

- [ ] Define `DispatchOptions` (Pydantic model near `WorkerConfig`):
  - `task_queue: str`
  - `start_to_close_timeout: timedelta`
  - `schedule_to_close_timeout: timedelta | None`
  - `schedule_to_start_timeout: timedelta | None`
  - `heartbeat_timeout: timedelta | None`
  - `retry_policy: temporalio.common.RetryPolicy` (already built from merged config)
- [ ] Implement `WorkerConfig.resolve_dispatch(activity_name: str, routing_key: str | None) -> DispatchOptions`:
  1. Resolve queue (reuse existing `resolve_queue` logic).
  2. Start with worker-config baselines.
  3. Overlay `queue_options[resolved_queue]` if present (last-wins for scalars).
  4. Overlay `activity_queues[activity_name].handle_options[routing_key]` if present.
  5. `non_retryable_error_types` composes **additively**: union of baseline + queue's `_extra` + handle's `_extra`.
  6. Build the final `RetryPolicy` via an extended `RetryPolicyConfig.make_retry_policy(merged_non_retryable_list: list[str] | None = None)`.
- [ ] Add `DispatchOptions.to_execute_kwargs()` returning the kwargs dict to splat into `workflow.execute_activity`.
- [ ] Keep `resolve_queue` as a thin delegate to `resolve_dispatch(...).task_queue` (no external callers but keeps the diff tight).

### Tasks — Switch dispatch sites

- [ ] Every `workflow.execute_activity(...)` site in `content_generator_in_workflow.py` (~10 sites): replace the `task_queue=resolve_queue(...) + start_to_close_timeout=workflow_execution_timeout + retry_policy=retry_policy` trio with one `**worker_config.resolve_dispatch(activity_name, routing_key).to_execute_kwargs()`.
- [ ] Audit all other `workflow.execute_activity` sites: `grep -rn "workflow.execute_activity" pipelex/`. None should reach for raw `worker_config.workflow_execution_timeout` after this phase.
- [ ] Confirm `temporal_pipe_router.py` and `temporal_pipe_run.py` still use `workflow_execution_timeout` for the *workflow itself* (legitimate; no change).

### Tasks — Unit tests (new file `tests/unit/pipelex/temporal/test_resolve_dispatch.py`)

- [ ] `test_no_overrides_uses_baseline`.
- [ ] `test_queue_options_override_baseline`.
- [ ] `test_handle_options_override_queue`.
- [ ] `test_non_retryable_additive` — baseline ∪ queue extra ∪ handle extra (set equality).
- [ ] `test_queue_options_partial_overlay` — partial fields, others fall through.
- [ ] `test_resolve_queue_still_works` — delegation regression guard.

### Tasks — Integration regression

- [ ] Run `tests/integration/pipelex/temporal/tracing/test_split_worker_*.py` — should pass unchanged.
- [ ] Add one assertion to a tracing test confirming that when `queue_options[X].start_to_close_timeout` is set, the actual dispatch uses it.

### Universal gates

- [ ] Pass.

### 📍 CHECKPOINT 2 — Submitter fully on new chain; timeout bug fixed

**Pickup brief for the next session:** Every dispatch reads `queue_options` and `handle_options`. Per-queue timeout tuning works end-to-end on the submitter side. Worker side is still hardcoded — that's Phase 3.

**Status:** ☐ not started

---

## Phase 3 — Worker-runtime profiles

**Goal:** Lift hardcoded `make_worker` knobs into `WorkerRuntimeProfile`, add the `--profile` CLI flag, apply queue-level rate limit from `queue_options` at Worker construction.

### Tasks — Profile resolution

- [ ] Implement `TemporalTaskManager._resolve_runtime_profile_by_name(profile_name: str | None) -> WorkerRuntimeProfile` mirroring `_resolve_scope_by_name`.
- [ ] Add `WorkerProfileConfigError` (parallel to `WorkerScopeConfigError`).

### Tasks — Worker construction

- [ ] `TemporalTaskManager.make_worker` signature: accept `runtime_profile: WorkerRuntimeProfile` (required).
- [ ] Replace every hardcoded constant in the `Worker(...)` call with `runtime_profile.<field>`.
- [ ] Read `queue_options.get(task_queue)`; if it has `max_task_queue_activities_per_second`, pass it. Otherwise omit.
- [ ] `run_worker` signature: accept `profile_name: str | None`, plumb through.

### Tasks — CLI

- [ ] `pipelex/temporal/worker_cli.py`: add `--profile` option to the `configure` command. Plumb to `run_worker`.
- [ ] Update the module docstring with a `--profile` usage example.
- [ ] Worker startup log line: include profile, scope, queue in one line.

### Tasks — Unit tests

`tests/unit/pipelex/temporal/test_worker_runtime_profile.py`:
- [ ] `test_default_profile_resolves_when_none`.
- [ ] `test_named_profile_resolves`.
- [ ] `test_unknown_profile_raises` — message includes known profile names.
- [ ] `test_resource_based_tuning_mode_rejected` — clear error.

`tests/unit/pipelex/temporal/test_make_worker_uses_profile.py`:
- [ ] Mock `Worker(...)`; assert each profile field flows to the matching kwarg.
- [ ] Assert `max_task_queue_activities_per_second` is read from `queue_options[task_queue]` when present, omitted otherwise.

### Universal gates

- [ ] Pass.

### 📍 CHECKPOINT 3 — Worker fully on new profiles; whole pipeline driven by new schema

**Pickup brief for the next session:** Code-side machinery is complete. Phases 4 & 5 add safety nets and ergonomics. Phase 6 verifies via multi-worker e2e.

**Status:** ☐ not started

---

## Phase 4 — Startup validation + resolver tracing

**Goal:** Ship the warn / fail / trace UX. Smaller phase.

### Tasks — Lenient warn (config load time)

- [ ] In a `@model_validator(mode="after")` on `Temporal` (or a post-load hook), collect every queue name from `activity_queues.*.default` and `activity_queues.*.by_handle.*`.
- [ ] For each not in `queue_options` and not equal to `default_task_queue`, `log.warning(...)` with the routing entry that mentioned it.
- [ ] Unit test: typo'd queue name in fixture → warn captured.

### Tasks — Strict fail (worker CLI startup)

- [ ] In `worker_cli.configure` (or a helper), build known-queue set:
  - `{worker_config.default_task_queue}` ∪ every `default` and `by_handle.*` in `activity_queues` ∪ every key in `queue_options`.
- [ ] If `--task-queue` (or its default fallback) is not in the set, raise `WorkerTaskQueueUnknownError`.
- [ ] Levenshtein distance ≤ 2 against any known queue → include `"Did you mean '<name>'?"` in the message.
- [ ] List all known queues in the error.
- [ ] Unit test: `--task-queue anthrpic_q` → error message contains `"Did you mean 'anthropic_q'?"`.

### Tasks — Resolver tracing

- [ ] Inside `WorkerConfig.resolve_dispatch`, when `temporal_log_config.is_dispatch_resolution_traced` is true, emit one log line per call.
  - Format: `temporal.dispatch act={activity_name} handle={routing_key} → queue={queue} (from={layer}) timeout={s}s (from={layer}) retry_attempts={N} (from={layer})`
  - `{layer}` ∈ `"baseline"`, `"queue_options"`, `"handle_options"`.
- [ ] Track source layer during resolution (private sidecar — not part of `DispatchOptions` public surface).
- [ ] Unit test: flag on → trace line present with correct `from=` columns across scenarios.

### Universal gates

- [ ] Pass.

### Status

☐ not started

---

## Phase 5 — Specialized worker scopes

**Goal:** Add scopes so each runner only registers the activities it handles. Pure config + tests.

### Tasks

- [ ] In `pipelex/pipelex.toml` under `[temporal.worker_scopes]`, add:
  - `runner-llm` — only LLM activities (`act_llm_gen_text`, `act_llm_gen_object`, `act_llm_gen_object_list`).
  - `runner-img-gen` — only `act_img_gen_images` (+ `act_render_page_views`? see below).
  - `runner-extract` — only `act_extract_gen_extract_pages` (+ `act_render_page_views`? see below).
  - `runner-jinja2` — only `act_jinja2_gen_text`.
- [ ] Decide policy for `act_render_page_views` (shared between image and extract paths). Probably register on both; document the call in a TOML comment.
- [ ] Tests in `tests/unit/pipelex/temporal/test_worker_scopes_specialized.py`:
  - Each scope, resolved, registers exactly the expected activity set.
  - Union of all specialized scopes covers `runner`'s full registration (no orphan activities).

### Universal gates

- [ ] Pass.

### 📍 CHECKPOINT 4 — All code-side work done

**Pickup brief for the next session:** Everything is wired up *in theory*. The remaining work is e2e validation through `/temporal-e2e-validate`. Expect meaningful time on the test harness extension (multi-worker spawn coordination) before scenarios start running.

**Status:** ☐ not started

---

## Phase 6 — Multi-worker e2e via `/temporal-e2e-validate`

**Goal:** Verify the multi-worker deployment topology end-to-end.

### Tasks — Skill / harness extension

- [ ] Locate the `/temporal-e2e-validate` skill (`.claude/skills/temporal-e2e-validate/`). Map how it spawns the existing 3-process setup.
- [ ] Extend to spawn **N** worker subprocesses with arbitrary `--profile / --scope / --task-queue` triplets, given a manifest dict.
- [ ] Coordinate startup: wait for each worker to register with Temporal before dispatching work.
- [ ] Teardown: signal each worker for graceful shutdown; verify no zombie subprocesses (memory: prior sessions have hit temporal zombies).

### Tasks — Scenarios

- [ ] **Scenario A — Multi-class routing.** 1 router + 1 LLM runner + 1 img-gen runner + 1 extract runner + submitter. Submit work firing at least one activity of each class. Verify each landed on the correct queue.
- [ ] **Scenario B — Per-queue timeout applied.** `queue_options[slow_q].start_to_close_timeout = "0:05:00"`, baseline `"0:00:30"`. Slow-mocked activity routed to `slow_q` completes (would fail at baseline).
- [ ] **Scenario C — Per-handle override wins over per-queue.** Same as B with `handle_options["specific_model"].start_to_close_timeout`. Handle value observed.
- [ ] **Scenario D — Queue-level rate limit observed.** `queue_options[capped_q].max_task_queue_activities_per_second = 2`. Burst of 10 activities. Assert `schedule_to_start` latency on tail activities is non-zero (read workflow history). Assert *ordering* and *non-zero schedule_to_start*, not exact timing.
- [ ] **Scenario E — Missing-worker negative.** Route to `orphan_q` but spawn no worker. Workflow reports `schedule_to_start` timeout (clear error, not a hang) within bounded time.
- [ ] **Scenario F — CLI startup typo.** `--task-queue typo_q` not in known set. Process exits non-zero with "Did you mean?" suggestion.

### Tasks — Skill documentation

- [ ] Update `/temporal-e2e-validate` skill description / README to mention the new multi-worker scenarios.
- [ ] Document how to invoke each scenario individually for local debugging.

### Universal gates

- [ ] Pass.
- [ ] `/temporal-e2e-validate` (full suite) green.

### 📍 CHECKPOINT 5 — FINAL — v2 shipped and verified

**When you reach this:** Update Status with completion date and PR. Add a Notes subsection with a one-paragraph retrospective. Move the design doc to `wip/temporal-primitives/archive/` and **delete this `TODOS.md` file** (or move it to `wip/temporal-primitives/archive/queue-options-v2-todos.md` if you want to keep the history).

**Status:** ☐ not started

---

## Living plan — usage notes

This file is *living*. At each checkpoint:

1. Flip `**Status:** ☐ not started` → `**Status:** ✅ done — YYYY-MM-DD — PR #NNNN`.
2. Add a `### Notes` subsection capturing anything surprising — deviations, follow-ups, decisions that turned out wrong.
3. If you discovered new subtasks during execution, add new checkboxes — don't pretend they were always there. Future-you will want the true scope.
4. If a decision from the design doc needed revision, note it here AND in the design doc's "Decisions taken" banner.

The point: if a future session opens this file from cold, they should be able to pick up at the lowest unchecked checkpoint with no missing context.
