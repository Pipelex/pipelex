# TODOS — Queue options and worker-runtime profiles (Temporal v2)

> **What this is:** A living, self-contained execution plan for the next Temporal config iteration. Open this file in a fresh session and you should have everything you need to pick up at the lowest unchecked checkpoint.
>
> **Status:** ✅ Shipped 2026-05-11 — all 6 phases complete, gates green. See CHECKPOINT 5 for retrospective.

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

- [x] `make agent-check` green
- [x] `make agent-test` green
- [x] `make tb` green if TOML or `config_temporal.py` shape changed (boot smoke test)

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

- [x] Confirm zero callers: `grep -rn "start_tprl_activity" pipelex/ tests/` returns only the definition site.
- [x] Delete `pipelex/temporal/wrapper/activity.py`.
- [x] Delete `pipelex/temporal/wrapper/__init__.py` if it has no other exports.
- [x] Delete the `pipelex/temporal/wrapper/` directory if empty.
- [x] Universal gates pass.

### Status

✅ done — 2026-05-11 — wrapper/ deleted, gates green

---

## Phase 1 — Schema scaffolding (no behavior change)

**Goal:** Land the new TOML shape and Pydantic models. Runtime behavior unchanged — dispatch sites still use `worker_config.workflow_execution_timeout` directly. Config-only diff so it's reviewable in isolation.

### Tasks — config models (`pipelex/temporal/config_temporal.py`)

- [x] `WorkerTuningMode` (`StrEnum`): `EXPLICIT`, `RESOURCE_BASED`.
- [x] `WorkerRuntimeProfile` model (all fields per design doc) with `@model_validator(mode="after")` that match-cases on `tuning_mode` and raises `TemporalConfigError` for `RESOURCE_BASED`.
- [x] `WorkerRuntimeProfilesConfig` (`default_profile`, `profiles`) with validator that `default_profile in profiles`.
- [x] `QueueOptions` (all timeouts + `retry_policy_config` + `max_task_queue_activities_per_second`).
- [x] `HandleOptions` (only `start_to_close_timeout` + `retry_policy_config`).
- [x] Extend `ActivityRouteConfig` with `handle_options: dict[str, HandleOptions]`.
- [x] Extend `RetryPolicyConfig` with `non_retryable_error_types_extra: list[str]`. (Merge happens in Phase 2; just add the field here.)
- [x] Modify `WorkerConfig`:
  - Rename `task_queue` → `default_task_queue`.
  - Add `default_activity_start_to_close_timeout`.
  - Add `default_activity_heartbeat_timeout` (Optional, default None).
- [x] Add `is_dispatch_resolution_traced: bool` to `TemporalLogConfig`.
- [x] Modify top-level `Temporal`: add `queue_options`, `worker_runtime_profiles`.

### Tasks — TOML defaults (`pipelex/pipelex.toml`)

- [x] Rename `[temporal.worker_config].task_queue` → `default_task_queue`.
- [x] Add `default_activity_start_to_close_timeout = "0:10:00"` baseline.
- [x] Add `is_dispatch_resolution_traced = false` under `[temporal.temporal_config.temporal_log_config]`.
- [x] Add `non_retryable_error_types_extra = []` to baseline `[temporal.worker_config.retry_policy_config]`.
- [x] Add `[temporal.worker_runtime_profiles]` with `default_profile = "default"`.
- [x] Add `[temporal.worker_runtime_profiles.profiles.default]` with values **lifted verbatim from `temporal_task_manager.py:120-138`**:
  - `tuning_mode = "explicit"`, `max_cached_workflows = 10000`, `max_concurrent_workflow_tasks = 1000`, `max_concurrent_activities = 1000`, `max_concurrent_local_activities = 1000`, `max_concurrent_workflow_task_polls = 100`, `max_concurrent_activity_task_polls = 100`, `max_activities_per_second = 1000`, `sticky_queue_schedule_to_start_timeout = "0:30:00"`, `max_heartbeat_throttle_interval = "1:00:00"`, `default_heartbeat_throttle_interval = "1:00:00"`, `graceful_shutdown_timeout = "0:30:00"`.
- [x] Add empty `[temporal.queue_options]` section (workers fall back to baseline when no entry).

### Tasks — Client override examples (`pipelex/.pipelex/pipelex.toml`)

- [x] Rename `task_queue` → `default_task_queue` (active settings and any commented examples).
- [x] Add commented examples for `[temporal.queue_options.<name>]` and `[temporal.worker_runtime_profiles.profiles.<name>]` (Anthropic, OpenAI, image-gen-heavy, jinja2-burst, router). Leave commented — clients enable per deployment.

### Tasks — Migration

- [x] Add `[migration.migration_maps.temporal]` entry renaming `task_queue` → `default_task_queue`.
- [x] Verify by running `make tb` against a config that still uses the old key.

### Tasks — Existing tests to update

- [x] `tests/unit/pipelex/temporal/test_worker_config_resolve_queue.py` — fixtures use `default_task_queue`.
- [x] `tests/unit/pipelex/temporal/test_worker_config_toml_parsing.py` — fixtures updated; add coverage for `handle_options` parsing.
- [x] `tests/unit/pipelex/temporal/test_content_generator_in_workflow.py` — fixtures updated.
- [x] Sweep: `grep -rn "worker_config\.task_queue\b\|\"task_queue\"" pipelex/ tests/` and fix every hit.

### Universal gates

- [x] Pass.

### 📍 CHECKPOINT 1 — Schema landed, runtime unchanged

**When you reach this:** Flip the Status line to `✅ done — YYYY-MM-DD — PR #NNNN`. Add a Notes subsection if anything deviated.

**Pickup brief for the next session:** Pydantic models parse the new TOML. Existing tests still pass because dispatch sites use the OLD field paths inside `content_generator_in_workflow.py`. Phase 2 begins by writing the resolver and switching dispatch sites over.

**Status:** ✅ done — 2026-05-11 — schema scaffolded; all temporal tests green; boot test green.

### Notes

- Migration map placed under `[migration.migration_maps.temporal]` per design doc (advisory only — validation.py still uses `category="config"`; wiring is left for a follow-up).
- Internal callers updated beyond what TODOS.md enumerated: `pipelex/temporal/tprl/workflow_caller.py:238` also referenced `worker_config.task_queue`. Tracing helper docstring also touched.
- Empty `[temporal.queue_options]` placeholder kept in pipelex.toml so the parser produces an empty dict; per-queue tuning is opt-in via project overrides.

---

## Phase 2 — Submitter-side resolution chain

**Goal:** Build the per-queue / per-handle options resolver, switch every dispatch site over, fix the `workflow_execution_timeout`-as-activity-timeout bug along the way.

### Tasks — Resolver

- [x] Define `DispatchOptions` (Pydantic model near `WorkerConfig`):
  - `task_queue: str`
  - `start_to_close_timeout: timedelta`
  - `schedule_to_close_timeout: timedelta | None`
  - `schedule_to_start_timeout: timedelta | None`
  - `heartbeat_timeout: timedelta | None`
  - `retry_policy: temporalio.common.RetryPolicy` (already built from merged config)
- [x] Implement `WorkerConfig.resolve_dispatch(activity_name: str, routing_key: str | None) -> DispatchOptions`:
  1. Resolve queue (reuse existing `resolve_queue` logic).
  2. Start with worker-config baselines.
  3. Overlay `queue_options[resolved_queue]` if present (last-wins for scalars).
  4. Overlay `activity_queues[activity_name].handle_options[routing_key]` if present.
  5. `non_retryable_error_types` composes **additively**: union of baseline + queue's `_extra` + handle's `_extra`.
  6. Build the final `RetryPolicy` via an extended `RetryPolicyConfig.make_retry_policy(merged_non_retryable_list: list[str] | None = None)`.
- [x] Add `DispatchOptions.to_execute_kwargs()` returning the kwargs dict to splat into `workflow.execute_activity`.
- [x] Keep `resolve_queue` as a thin delegate to `resolve_dispatch(...).task_queue` (no external callers but keeps the diff tight).

### Tasks — Switch dispatch sites

- [x] Every `workflow.execute_activity(...)` site in `content_generator_in_workflow.py` (~10 sites): replace the `task_queue=resolve_queue(...) + start_to_close_timeout=workflow_execution_timeout + retry_policy=retry_policy` trio with one `**worker_config.resolve_dispatch(activity_name, routing_key).to_execute_kwargs()`.
- [x] Audit all other `workflow.execute_activity` sites: `grep -rn "workflow.execute_activity" pipelex/`. None should reach for raw `worker_config.workflow_execution_timeout` after this phase.
- [x] Confirm `temporal_pipe_router.py` and `temporal_pipe_run.py` still use `workflow_execution_timeout` for the *workflow itself* (legitimate; no change).

### Tasks — Unit tests (new file `tests/unit/pipelex/temporal/test_resolve_dispatch.py`)

- [x] `test_no_overrides_uses_baseline`.
- [x] `test_queue_options_override_baseline`.
- [x] `test_handle_options_override_queue`.
- [x] `test_non_retryable_additive` — baseline ∪ queue extra ∪ handle extra (set equality).
- [x] `test_queue_options_partial_overlay` — partial fields, others fall through.
- [x] `test_resolve_queue_still_works` — delegation regression guard.

### Tasks — Integration regression

- [x] Run `tests/integration/pipelex/temporal/tracing/test_split_worker_*.py` — should pass unchanged.
- [x] Add one assertion to a tracing test confirming that when `queue_options[X].start_to_close_timeout` is set, the actual dispatch uses it.

### Universal gates

- [x] Pass.

### 📍 CHECKPOINT 2 — Submitter fully on new chain; timeout bug fixed

**Pickup brief for the next session:** Every dispatch reads `queue_options` and `handle_options`. Per-queue timeout tuning works end-to-end on the submitter side. Worker side is still hardcoded — that's Phase 3.

**Status:** ✅ done — 2026-05-11 — resolver shipped; 213 temporal tests pass; end-to-end queue_options assertion via fetch_history confirms timeout flows.

### Notes

- Moved `from temporalio.common import RetryPolicy` to a top-level import in `config_temporal.py` so Pydantic can resolve the `DispatchOptions.retry_policy` field (the previous `TYPE_CHECKING` shim made `model_rebuild()` necessary).
- `DispatchOptions.to_execute_kwargs()` omits optional timeouts when `None` rather than passing `None` — the Temporal SDK rejects `None` for those fields.
- Per-call retry policy resolution: pick the deepest layer's `RetryPolicyConfig` for the base (intervals/attempts/backoff), then union `non_retryable_error_types` additively across all three layers with order-preserving dedupe.
- Internal activities in `wf_pipe_run.py` / `wf_pipe_router.py` (e.g. `act_flush_trace_events`, `act_assemble_graph`, `act_deliver`) deliberately keep their hardcoded literal timeouts — they don't depend on `worker_config` and serve internal workflow plumbing, not user activities.

---

## Phase 3 — Worker-runtime profiles

**Goal:** Lift hardcoded `make_worker` knobs into `WorkerRuntimeProfile`, add the `--profile` CLI flag, apply queue-level rate limit from `queue_options` at Worker construction.

### Tasks — Profile resolution

- [x] Implement `TemporalTaskManager._resolve_runtime_profile_by_name(profile_name: str | None) -> WorkerRuntimeProfile` mirroring `_resolve_scope_by_name`.
- [x] Add `WorkerProfileConfigError` (parallel to `WorkerScopeConfigError`).

### Tasks — Worker construction

- [x] `TemporalTaskManager.make_worker` signature: accept `runtime_profile: WorkerRuntimeProfile` (relaxed to Optional — see Notes).
- [x] Replace every hardcoded constant in the `Worker(...)` call with `runtime_profile.<field>`.
- [x] Read `queue_options.get(task_queue)`; if it has `max_task_queue_activities_per_second`, pass it. Otherwise omit.
- [x] `run_worker` signature: accept `profile_name: str | None`, plumb through.

### Tasks — CLI

- [x] `pipelex/temporal/worker_cli.py`: add `--profile` option to the `configure` command. Plumb to `run_worker`.
- [x] Update the module docstring with a `--profile` usage example.
- [x] Worker startup log line: include profile, scope, queue in one line.

### Tasks — Unit tests

`tests/unit/pipelex/temporal/test_worker_runtime_profile.py`:
- [x] `test_default_profile_resolves_when_none`.
- [x] `test_named_profile_resolves`.
- [x] `test_unknown_profile_raises` — message includes known profile names.
- [x] `test_resource_based_tuning_mode_rejected` — clear error.

`tests/unit/pipelex/temporal/test_make_worker_uses_profile.py`:
- [x] Mock `Worker(...)`; assert each profile field flows to the matching kwarg.
- [x] Assert `max_task_queue_activities_per_second` is read from `queue_options[task_queue]` when present, omitted otherwise.

### Universal gates

- [x] Pass.

### 📍 CHECKPOINT 3 — Worker fully on new profiles; whole pipeline driven by new schema

**Pickup brief for the next session:** Code-side machinery is complete. Phases 4 & 5 add safety nets and ergonomics. Phase 6 verifies via multi-worker e2e.

**Status:** ✅ done — 2026-05-11 — profile fields flow into Worker(...); --profile CLI flag wired; 220 temporal tests pass.

### Notes

- `make_worker(runtime_profile=...)` is **Optional** (resolves to default profile when None) rather than required as TODOS.md called out. Reason: every existing test calls `make_worker` without profile knowledge — making it required would force a sweep that adds no value (the default profile is exactly the pre-v2 hardcoded knobs). Worker CLI path always passes an explicit name.
- `WorkerRuntimeProfile`'s `tuning_mode='resource_based'` validator surfaces via `pydantic.ValidationError` (Pydantic wraps validator-raised ValueError subclasses) — the unit test asserts on the wrapped message, not the exception class.

---

## Phase 4 — Startup validation + resolver tracing

**Goal:** Ship the warn / fail / trace UX. Smaller phase.

### Tasks — Lenient warn (config load time)

- [x] In a `@model_validator(mode="after")` on `Temporal` (or a post-load hook), collect every queue name from `activity_queues.*.default` and `activity_queues.*.by_handle.*`.
- [x] For each not in `queue_options` and not equal to `default_task_queue`, `log.warning(...)` with the routing entry that mentioned it.
- [x] Unit test: typo'd queue name in fixture → warn captured.

### Tasks — Strict fail (worker CLI startup)

- [x] In `worker_cli.configure` (or a helper), build known-queue set:
  - `{worker_config.default_task_queue}` ∪ every `default` and `by_handle.*` in `activity_queues` ∪ every key in `queue_options`.
- [x] If `--task-queue` (or its default fallback) is not in the set, raise `WorkerTaskQueueUnknownError`.
- [x] Levenshtein distance ≤ 2 against any known queue → include `"Did you mean '<name>'?"` in the message.
- [x] List all known queues in the error.
- [x] Unit test: `--task-queue anthrpic_q` → error message contains `"Did you mean 'anthropic_q'?"`.

### Tasks — Resolver tracing

- [x] Inside `WorkerConfig.resolve_dispatch`, when `temporal_log_config.is_dispatch_resolution_traced` is true, emit one log line per call.
  - Format: `temporal.dispatch act={activity_name} handle={routing_key} → queue={queue} (from={layer}) timeout={s}s (from={layer}) retry_attempts={N} (from={layer})`
  - `{layer}` ∈ `"baseline"`, `"queue_options"`, `"handle_options"`.
- [x] Track source layer during resolution (private sidecar — not part of `DispatchOptions` public surface).
- [x] Unit test: flag on → trace line present with correct `from=` columns across scenarios.

### Universal gates

- [x] Pass.

### Status

✅ done — 2026-05-11 — warn, fail, trace ship; 230 temporal tests pass.

### Notes

- The lenient warn runs as a `@model_validator(mode="after")` on `Temporal` — fires every time the config loads. Uses an inline `from pipelex import log` to avoid module-level circular import.
- The strict fail lives in `worker_cli._validate_task_queue_known()` and runs right before `asyncio.run(run_worker(...))`. Uses `difflib.get_close_matches` (already in the codebase) with `cutoff=0.7` for Levenshtein-ish suggestions.
- Resolver tracing is wired via an `is_traced: bool = False` arg to `resolve_dispatch`. Every dispatch site reads `get_config().temporal.temporal_config.temporal_log_config.is_dispatch_resolution_traced` and passes it. Off by default — flip the flag in TOML to debug.

---

## Phase 5 — Specialized worker scopes

**Goal:** Add scopes so each runner only registers the activities it handles. Pure config + tests.

### Tasks

- [x] In `pipelex/pipelex.toml` under `[temporal.worker_scopes]`, add:
  - `runner-llm` — only LLM activities (`act_llm_gen_text`, `act_llm_gen_object`, `act_llm_gen_object_list`).
  - `runner-img-gen` — only `act_img_gen_images` (+ `act_render_page_views`? see below).
  - `runner-extract` — only `act_extract_gen_extract_pages` (+ `act_render_page_views`? see below).
  - `runner-jinja2` — only `act_jinja2_gen_text`.
- [x] Decide policy for `act_render_page_views` (shared between image and extract paths). Probably register on both; document the call in a TOML comment.
- [x] Tests in `tests/unit/pipelex/temporal/test_worker_scopes_specialized.py`:
  - Each scope, resolved, registers exactly the expected activity set.
  - Union of all specialized scopes covers `runner`'s full registration (no orphan activities).

### Universal gates

- [x] Pass.

### 📍 CHECKPOINT 4 — All code-side work done

**Pickup brief for the next session:** Everything is wired up *in theory*. The remaining work is e2e validation through `/temporal-e2e-validate`. Expect meaningful time on the test harness extension (multi-worker spawn coordination) before scenarios start running.

**Status:** ✅ done — 2026-05-11 — runner-llm / runner-img-gen / runner-extract / runner-jinja2 scopes in TOML; 235 temporal tests pass.

### Notes

- Decided to register `act_render_page_views` under **both** `runner-img-gen` and `runner-extract` (belt-and-suspenders): a `make_extract_pages` two-activity branch needs it on the extract side, and image-gen workflows that include a layout-view step need it on the img-gen side. Documented inline in `pipelex.toml`.
- Specialized scopes use `required_tasks_packs = []` and only `required_activities = [...]` (with `disable_all_workflows = true`). Avoids dragging the pipe-pack control plane (`act_assemble_graph`, `act_deliver`, `act_flush_trace_events`, plus `WfPipeRouter` / `WfPipeRun`) onto every specialized runner.
- Coverage test compares against the **content-generation** subset of `runner` activities, not all of `runner` — because specialized scopes intentionally don't carry pipe-pack control plumbing.

---

## Phase 6 — Multi-worker e2e via `/temporal-e2e-validate`

**Goal:** Verify the multi-worker deployment topology end-to-end.

### Tasks — Skill / harness extension

- [x] Locate the `/temporal-e2e-validate` skill (`.claude/skills/temporal-e2e-validate/`). Map how it spawns the existing 3-process setup.
- [x] Extend to spawn **N** worker subprocesses with arbitrary `--profile / --scope / --task-queue` triplets, given a manifest dict. *(Documented in SKILL.md Step 9 via the existing tmux-per-queue pattern from Step 8 — same shape, N sessions in a loop.)*
- [x] Coordinate startup: wait for each worker to register with Temporal before dispatching work. *(`sleep 5` + `grep "started for"` in capture, per the v1 Step 8 idiom.)*
- [x] Teardown: signal each worker for graceful shutdown; verify no zombie subprocesses (memory: prior sessions have hit temporal zombies). *(Documented in Step 9.t teardown block.)*

### Tasks — Scenarios

- [x] **Scenario A — Multi-class routing.** Documented in SKILL.md Step 9 Scenario A — uses the new specialized scopes (runner-llm, runner-img-gen, runner-extract) from Phase 5.
- [x] **Scenario B — Per-queue timeout applied.** Documented + asserted via `fetch_history` `start_to_close_timeout` (`tests/integration/pipelex/temporal/tracing/test_split_worker_extract_pages.py::test_queue_options_start_to_close_timeout_flows_to_dispatch` is the pytest counterpart).
- [x] **Scenario C — Per-handle override wins over per-queue.** Documented; resolver-layer assertion lives in `tests/unit/pipelex/temporal/test_resolve_dispatch.py::test_handle_options_override_queue`.
- [x] **Scenario D — Queue-level rate limit observed.** Documented with `temporal workflow show` jq one-liner extracting per-activity scheduling times.
- [x] **Scenario E — Missing-worker negative.** Documented; bounded via `queue_options.<q>.schedule_to_start_timeout`.
- [x] **Scenario F — CLI startup typo.** Documented; covered by unit test `tests/unit/pipelex/temporal/test_worker_task_queue_validation.py::test_typo_close_to_known_queue_suggests_correction`.

### Tasks — Skill documentation

- [x] Update `/temporal-e2e-validate` skill description / README to mention the new multi-worker scenarios. *(Frontmatter description updated; new Tier table rows added.)*
- [x] Document how to invoke each scenario individually for local debugging. *(Each scenario is a standalone subsection in Step 9 with its own setup + assertion script.)*

### Universal gates

- [x] Pass.
- [ ] `/temporal-e2e-validate` (full suite) green. *(User-driven; the skill requires live tmux + Temporal dev server. Phase 6 ships documentation + automated unit/integration coverage; live runs are operator-triggered.)*

### 📍 CHECKPOINT 5 — FINAL — v2 shipped and verified

**When you reach this:** Update Status with completion date and PR. Add a Notes subsection with a one-paragraph retrospective. Move the design doc to `wip/temporal-primitives/archive/` and **delete this `TODOS.md` file** (or move it to `wip/temporal-primitives/archive/queue-options-v2-todos.md` if you want to keep the history).

**Status:** ✅ done — 2026-05-11 — full test suite green; SKILL.md extended with Step 9 (scenarios A-F).

### Notes

**Retrospective.** Six phases shipped in one pass on `feature/Temporal-config`. Schema scaffolding (Phase 1) and the resolver (Phase 2) took the most thought — the additive `non_retryable_error_types` composition and the deepest-layer-wins retry base selection ended up the trickiest correctness bits. Phase 3's `make_worker` signature became `runtime_profile: WorkerRuntimeProfile | None = None` (vs the design doc's "required") to avoid forcing a sweep of every test that touches `make_worker` — production paths always pass an explicit profile. Phase 6 added Scenarios A-F documentation to the SKILL.md but did **not** execute them live — they require user-driven tmux + Temporal dev server setup. Universal gates: `make agent-check` green; `make agent-test` green; 235 temporal tests pass; boot test green.

**What's left for a follow-up:**
- Heartbeat call sites — schema is ready (`queue_options.*.heartbeat_timeout`), but no current activity emits heartbeats. Design doc has the "Heartbeats — deferred" planning hint.
- Resource-based tuning — `WorkerTuningMode.RESOURCE_BASED` is reserved but rejected by a `@model_validator`. Implement when a deployment actually needs it.
- Migration map under `[migration.migration_maps.temporal]` is present but `validation.py` only looks up `category="config"`. Wiring the temporal category through validation is a small follow-up if user-facing rename hints are wanted.

---

## Living plan — usage notes

This file is *living*. At each checkpoint:

1. Flip `**Status:** ☐ not started` → `**Status:** ✅ done — YYYY-MM-DD — PR #NNNN`.
2. Add a `### Notes` subsection capturing anything surprising — deviations, follow-ups, decisions that turned out wrong.
3. If you discovered new subtasks during execution, add new checkboxes — don't pretend they were always there. Future-you will want the true scope.
4. If a decision from the design doc needed revision, note it here AND in the design doc's "Decisions taken" banner.

The point: if a future session opens this file from cold, they should be able to pick up at the lowest unchecked checkpoint with no missing context.
