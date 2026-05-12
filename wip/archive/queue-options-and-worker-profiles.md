# Queue options and worker-runtime profiles

> **Status:** Design ready for implementation. Builds on `per-activity-queue-routing-v1.md` (shipped). Extends the deployment surface in two orthogonal directions:
>
> 1. **Submitter-side**: timeouts and retry policies become per-queue (with rare per-handle exceptions), instead of one set of values applied to every activity.
> 2. **Worker-side**: concurrency slots, pollers, and rate-limit knobs (currently hardcoded in `make_worker`) become named profiles selectable per worker process — so a deployment manifest can spin up `N` workers with different shapes against different queues.
>
> **Predecessor context:** v1 introduced `activity_queues` to route `(activity_name, handle)` → queue. That solved "where does this activity run." This doc solves "how is this activity invoked, and how does the worker on the other side behave."
>
> **End-goal framing:** a deployment manifest (docker-compose, k8s) declares which workers run with which profiles against which queues. Locally testable through the existing `temporal-e2e-validate` skill, which already drives multi-process setups.
>
> **Decisions taken** (resolves the open questions section that closes this doc):
> - `heartbeat_timeout` lives on `QueueOptions` only, not on `HandleOptions`.
> - `non_retryable_error_types` composes **additively** across layers.
> - Startup validation: **warn** on routing entries that name unknown queues; **fail** when `--task-queue` on the worker CLI doesn't appear anywhere in routing/options/defaults.
> - Resource-based tuning is reserved as a future `tuning_mode` enum value, **not shipped in v2**.
> - No per-worker `--server` override.
> - Resolver tracing is added under a new `is_dispatch_resolution_traced` flag in `temporal_log_config`, **off by default**.
> - `pipelex/temporal/wrapper/activity.py` (`start_tprl_activity`) is **dead code** (zero callers) — deleted in v2, not migrated.
> - Heartbeat *call sites* are out of scope for v2 (see "Heartbeats — deferred" below).

## First actions (cold-start checklist)

1. Read `per-activity-queue-routing-v1.md` for the v1 routing model — this doc layers on top of it and reuses its resolution chain.
2. Map the current config shape: `pipelex/temporal/config_temporal.py` (`WorkerConfig`, `ActivityRouteConfig`) and `pipelex/pipelex.toml` `[temporal.worker_config]`.
3. Map the hardcoded worker knobs we plan to lift: `pipelex/temporal/temporal_task_manager.py:120-138` (`make_worker`).
4. Map the dispatch sites that will read the new resolution chain: every `workflow.execute_activity` call in `pipelex/temporal/tprl_content_generation/content_generator_in_workflow.py`. The wrapper file `pipelex/temporal/wrapper/activity.py` (`start_tprl_activity`) has **zero callers** — confirm with `grep -rn "start_tprl_activity"` and delete the file as part of v2.
5. Gates: `make agent-check` and `make agent-test` after each phase. Use `/temporal-e2e-validate` for deployment-topology verification.

## Problem

Two concrete pain points motivate this, plus a structural one.

**1. One timeout fits nothing.** Today every dispatch site uses `worker_config.workflow_execution_timeout` (a workflow-level concept) as the activity `start_to_close_timeout`. A jinja2 render gets the same 1h budget as a 30s LLM call as a 20-minute big-PDF extract. The pipe wrapper `wrapper/activity.py` punts entirely with `max_timeout = 24h` on every timeout. There is no expression for "this queue talks to a fast backend, that one talks to a slow batch backend."

**2. Worker tuning is invisible.** `make_worker` hardcodes `max_concurrent_activities=1000`, `max_activities_per_second=1000`, `max_task_queue_activities_per_second=1000`, plus poller counts and heartbeat intervals. None of this is in TOML. A deployment that needs a small GPU worker pool (`max_concurrent_activities=2`) sitting next to a high-throughput Anthropic pool (`max_concurrent_activities=100`, server-side queue cap of 50 RPS to match a tier budget) cannot be expressed.

**3. Name conflation.** `worker_config` today mixes submitter-side defaults (timeouts, retry policy, `resolve_queue`) with one worker-side field (`task_queue`, the worker's home queue). The rest of the worker-side knobs aren't in `worker_config` at all — they're in source code. Splitting these concerns into orthogonal config sections makes both ends usable without bleeding into each other.

## Goals

- **Per-queue submitter options.** Timeouts and retry policy attach to the queue name. The queue name is the natural anchor because it represents the backend pool on the other side — the thing whose RPS budget and latency profile we are tuning for.
- **Per-handle option overrides for the rare case.** A specific handle (e.g. a long-context model with 20-minute generations) can override the queue baseline without forcing a separate queue.
- **Named worker-runtime profiles.** A profile bundles all the `Worker(...)` constructor knobs. A worker process selects one at startup.
- **Both rate-limit knobs exposed.** Worker-local (`max_activities_per_second`) AND server-side cluster-wide (`max_task_queue_activities_per_second`). They solve different problems; both are first-class.
- **Same config drives local tests and prod.** `temporal-e2e-validate` exercises the same TOML resolution paths a prod deployment uses.
- **Deterministic resolution.** Every lookup falls back through a fixed chain. No magic; no callable hooks (deferred to a future iteration if a real need surfaces).

## Non-goals (v2)

- Resource-based tuning (Temporal's `WorkerTuner.create_resource_based`). Useful, but second-pass; the explicit-knob shape we ship first is what most deployments will actually configure.
- Dynamic per-pipe routing/options overrides (covered in v1's open questions, still deferred).
- Re-keying the routing chain on resolved-provider instead of handle. v1's decision stands: route by handle, not by provider.
- Editing namespace-level Temporal CLI knobs (e.g. `temporal task-queue config set --queue-rps-limit`). We surface SDK-side rate-limit settings; out-of-band server-side settings remain the operator's responsibility.

## Schema

The full `[temporal]` section after this change.

```toml
[temporal]
is_enabled = true

[temporal.payload_codec_config]
# unchanged

[temporal.temporal_config]
# server connection — unchanged
selected_server = "local"
# ...

####################################################################################################
# Submitter-side defaults
####################################################################################################

[temporal.worker_config]
default_task_queue = "temporal_task_queue"        # fallback when no activity_queues entry matches
workflow_execution_timeout = "1:00:00"            # for the workflow itself (NOT used as activity timeout anymore)
run_timeout = "1:00:00"
task_timeout = "0:00:10"
start_delay = "0:00:00"
rpc_timeout = "1:00:00"
default_activity_start_to_close_timeout = "0:10:00"   # NEW: baseline activity timeout
default_activity_heartbeat_timeout = "0:01:00"        # NEW: baseline

[temporal.worker_config.retry_policy_config]
# Baseline retry policy. Per-queue and per-handle overrides layer on top.
initial_interval = "0:00:03"
backoff_coefficient = 2.0
maximum_interval = "unlimited"
maximum_attempts = 3
non_retryable_error_types = [
  "ExtractHandleNotFoundError",
  "FileNotFoundError",
  "ImgGenHandleNotFoundError",
  "LLMHandleNotFoundError",
  "ModelNotFoundError",
  "ValidationError",
]

####################################################################################################
# Per-activity routing (v1 — unchanged structure)
####################################################################################################

[temporal.worker_config.activity_queues.act_llm_gen_text]
default = "inference_q"
by_handle = { "claude-opus-4-7" = "anthropic_q", "gpt-5" = "openai_q" }

[temporal.worker_config.activity_queues.act_img_gen_images]
default = "image_gen_q"
by_handle = { "flux-1.1-pro" = "fal_q" }

# Rare: per-handle option overrides. Most handles share their queue's options.
# Use this when ONE handle on a queue needs different tuning (e.g. a 1M-context
# variant with a much longer timeout).
[temporal.worker_config.activity_queues.act_llm_gen_text.handle_options."claude-opus-4-7-1m"]
start_to_close_timeout = "0:25:00"

####################################################################################################
# Per-queue submitter options (NEW)
####################################################################################################

# Default options for activities that fall through to default_task_queue.
[temporal.queue_options.temporal_task_queue]
start_to_close_timeout = "0:10:00"

[temporal.queue_options.anthropic_q]
start_to_close_timeout = "0:05:00"
heartbeat_timeout = "0:01:00"             # only meaningful for activities that emit heartbeats — see "Heartbeats — deferred"
# Anthropic 429-aware retry: longer max_interval, more attempts.
[temporal.queue_options.anthropic_q.retry_policy_config]
initial_interval = "0:00:05"
backoff_coefficient = 2.0
maximum_interval = "0:02:00"
maximum_attempts = 6
# Additive on top of worker_config baseline. Use for backend-specific 4xx classes
# (e.g. AnthropicBadRequestError, OpenAIContentFilterError) that should never retry.
non_retryable_error_types_extra = []

# Queue-level rate limit. Cluster-wide, server-enforced. Any worker that polls
# this queue conveys this value at startup; the latest one wins on the server.
# Pipelex requires consistent values across all workers on the same queue
# (validated at startup).
max_task_queue_activities_per_second = 50

[temporal.queue_options.openai_q]
start_to_close_timeout = "0:05:00"
max_task_queue_activities_per_second = 80

[temporal.queue_options.image_gen_q]
start_to_close_timeout = "0:10:00"
[temporal.queue_options.image_gen_q.retry_policy_config]
initial_interval = "0:00:10"
backoff_coefficient = 2.0
maximum_interval = "0:05:00"
maximum_attempts = 4

[temporal.queue_options.extract_q]
start_to_close_timeout = "0:30:00"        # extract can be slow

####################################################################################################
# Worker-runtime profiles (NEW)
####################################################################################################

# A profile bundles every Worker(...) tuning knob. The worker process selects
# one at startup via --profile.
[temporal.worker_runtime_profiles.default]
tuning_mode = "explicit"                  # only "explicit" is implemented in v2; "resource_based" is reserved for a future iteration
max_cached_workflows = 10000
max_concurrent_workflow_tasks = 1000
max_concurrent_activities = 1000
max_concurrent_local_activities = 1000
max_concurrent_workflow_task_polls = 100
max_concurrent_activity_task_polls = 100
max_activities_per_second = 1000          # worker-local rate limit
sticky_queue_schedule_to_start_timeout = "0:30:00"
max_heartbeat_throttle_interval = "1:00:00"
default_heartbeat_throttle_interval = "1:00:00"
graceful_shutdown_timeout = "0:30:00"

[temporal.worker_runtime_profiles.anthropic-tier4]
max_concurrent_activities = 100
max_activities_per_second = 60            # ~match Anthropic tier
max_concurrent_activity_task_polls = 20
# everything else inherits from worker_runtime_profiles.default

[temporal.worker_runtime_profiles.image-gen-heavy]
max_concurrent_activities = 4              # small parallelism, large payloads
max_activities_per_second = 4
graceful_shutdown_timeout = "0:10:00"

[temporal.worker_runtime_profiles.jinja2-burst]
max_concurrent_activities = 200            # cheap, fast
max_activities_per_second = 5000

[temporal.worker_runtime_profiles.router]
max_concurrent_activities = 0              # workflow-only worker; counterpart of runners
max_concurrent_workflow_tasks = 500

# selected if --profile not passed at startup
default_profile = "default"

####################################################################################################
# Worker registration scopes (v1 — unchanged)
####################################################################################################

[temporal.worker_scopes]
default_scope = "full"
# Pipelex SHOULD ship at least these specialized scopes (in addition to full/router/runner)
# so each "runner" worker process only registers the activities it actually handles:
#   - runner-llm           (LLM activities only)
#   - runner-img-gen       (image-gen activities only)
#   - runner-extract       (extract activities only)
#   - runner-jinja2        (jinja2 activities only)
# These are simple additions to worker_scopes.scopes and don't require any code changes.

####################################################################################################
# Logging (one new flag for v2)
####################################################################################################

[temporal.temporal_config.temporal_log_config]
# ... existing flags unchanged ...
is_dispatch_resolution_traced = false     # NEW. When true, every workflow.execute_activity dispatch logs
                                          # the resolved queue + start_to_close_timeout + retry_policy and
                                          # the layer each value came from (baseline / queue_options / handle_options).
                                          # Off by default — verbose. Turn on when debugging mis-tuned timeouts.
```

### Pydantic shapes

```python
# config_temporal.py

class QueueOptions(ConfigModel):
    """Per-queue submitter options + queue-level rate limit.

    Resolution order at dispatch (for timeouts and retry):
      per-handle override (handle_options.<handle>) →
      this (queue_options[resolved_queue]) →
      worker_config defaults.

    Note: `heartbeat_timeout` lives here (queue scope) because heartbeat cadence
    is a property of the backend on the other side of the queue. It is NOT on
    `HandleOptions`. If a single model on a backend ever needs a different
    cadence, add the field to `HandleOptions` then — schema change is one line.
    """

    start_to_close_timeout: timedelta | None = Field(default=None, strict=False)
    schedule_to_close_timeout: timedelta | None = Field(default=None, strict=False)
    schedule_to_start_timeout: timedelta | None = Field(default=None, strict=False)
    heartbeat_timeout: timedelta | None = Field(default=None, strict=False)
    retry_policy_config: RetryPolicyConfig | None = None
    # Cluster-wide queue rate limit, conveyed to server by every worker on this queue.
    max_task_queue_activities_per_second: float | None = None


class HandleOptions(ConfigModel):
    """Per-handle option overrides. Layers on top of QueueOptions for the resolved queue.

    Deliberately narrow: only timeout and retry. Heartbeat is queue-level.
    Other fields will be added on demand when a real case surfaces.
    """

    start_to_close_timeout: timedelta | None = Field(default=None, strict=False)
    retry_policy_config: RetryPolicyConfig | None = None


class ActivityRouteConfig(ConfigModel):
    """Per-activity routing entry. v1 fields preserved; handle_options added."""

    default: str
    by_handle: dict[str, str] = Field(default_factory=dict)
    handle_options: dict[str, HandleOptions] = Field(default_factory=dict)  # NEW


class WorkerTuningMode(StrEnum):
    """How a worker scales its slot counts.

    Only EXPLICIT is implemented in v2. RESOURCE_BASED is reserved for a future
    iteration (Temporal SDK's `WorkerTuner.create_resource_based`). Defined now
    so the profile schema doesn't break when we add it.
    """

    EXPLICIT = "explicit"
    RESOURCE_BASED = "resource_based"


class WorkerRuntimeProfile(ConfigModel):
    """Bundle of Worker(...) constructor tuning. One worker process selects one profile.

    `tuning_mode` MUST be `"explicit"` in v2. A model_validator rejects
    `"resource_based"` with a clear "not implemented yet" message until the
    follow-up iteration ships the resource-based path.
    """

    tuning_mode: WorkerTuningMode = Field(strict=False)
    max_cached_workflows: int
    max_concurrent_workflow_tasks: int
    max_concurrent_activities: int
    max_concurrent_local_activities: int
    max_concurrent_workflow_task_polls: int
    max_concurrent_activity_task_polls: int
    max_activities_per_second: float                       # worker-local cap
    sticky_queue_schedule_to_start_timeout: timedelta = Field(strict=False)
    max_heartbeat_throttle_interval: timedelta = Field(strict=False)
    default_heartbeat_throttle_interval: timedelta = Field(strict=False)
    graceful_shutdown_timeout: timedelta = Field(strict=False)

    @model_validator(mode="after")
    def reject_unimplemented_tuning_mode(self) -> Self:
        match self.tuning_mode:
            case WorkerTuningMode.EXPLICIT:
                return self
            case WorkerTuningMode.RESOURCE_BASED:
                msg = "tuning_mode='resource_based' is reserved but not implemented in v2; use 'explicit'."
                raise TemporalConfigError(msg)


class WorkerRuntimeProfilesConfig(ConfigModel):
    """Named worker-runtime profiles selectable via --profile on the worker CLI."""

    default_profile: str
    profiles: dict[str, WorkerRuntimeProfile]

    @model_validator(mode="after")
    def validate_default_profile(self) -> Self:
        if self.default_profile not in self.profiles:
            msg = f"default_profile '{self.default_profile}' not in profiles (known: {sorted(self.profiles.keys())})"
            raise TemporalConfigError(msg)
        return self


class WorkerConfig(ConfigModel):
    """Submitter-side defaults plus the worker's home queue."""

    default_task_queue: str                                # renamed from `task_queue` for clarity
    activity_queues: dict[str, ActivityRouteConfig]
    workflow_execution_timeout: timedelta = Field(strict=False)
    run_timeout: timedelta | None = Field(default=None, strict=False)
    task_timeout: timedelta | None = Field(default=None, strict=False)
    start_delay: timedelta | None = Field(default=None, strict=False)
    rpc_timeout: timedelta | None = Field(default=None, strict=False)
    default_activity_start_to_close_timeout: timedelta = Field(strict=False)  # NEW
    default_activity_heartbeat_timeout: timedelta | None = Field(default=None, strict=False)  # NEW
    retry_policy_config: RetryPolicyConfig                                    # baseline


class Temporal(ConfigModel):
    is_enabled: bool
    temporal_config: TemporalConfig
    worker_config: WorkerConfig
    queue_options: dict[str, QueueOptions]                 # NEW
    worker_runtime_profiles: WorkerRuntimeProfilesConfig   # NEW
    worker_scopes: WorkerScopesConfig
    payload_codec_config: PayloadCodecConfig
```

## Resolution chain

### Submitter side — `resolve_dispatch(activity_name, routing_key)`

Returns a `DispatchOptions` bundle (`task_queue`, `start_to_close_timeout`, `retry_policy`, …) that the workflow passes verbatim to `workflow.execute_activity(...)`.

```
resolve queue:
  1. activity_queues[activity_name].by_handle[routing_key]   →  use it
  2. activity_queues[activity_name].default                  →  use it
  3. worker_config.default_task_queue                        →  use it

resolve timeouts and retry (independent of step above):
  start_with worker_config.{default_activity_start_to_close_timeout, retry_policy_config baseline}
  if queue_options[resolved_queue] exists:
      overlay its non-None fields    (last-wins for scalars)
  if activity_queues[activity_name].handle_options[routing_key] exists:
      overlay its non-None fields    (last-wins for scalars)
```

Three deterministic layers, in the same shape the v1 routing chain already uses. The key invariant: **every value has a clear, single source of truth** for any given `(activity_name, routing_key)` pair.

**One exception to last-wins: `non_retryable_error_types`.** This list composes **additively** across layers:

```
final non_retryable_error_types =
    worker_config.retry_policy_config.non_retryable_error_types
  ∪ queue_options[resolved_queue].retry_policy_config.non_retryable_error_types_extra
  ∪ activity_queues[…].handle_options[…].retry_policy_config.non_retryable_error_types_extra  (rare)
```

Rationale: this list is a safety brake against retry storms. The risk of *accidentally dropping* a baseline non-retryable (e.g. `ValidationError`) on one queue and retrying bad input forever is worse than the inconvenience of being unable to *remove* an entry per-queue. The expected use is backend-specific 4xx errors (e.g. `AnthropicBadRequestError`, `OpenAIContentFilterError`) — purely additive. If a real "must downgrade a baseline non-retryable on one queue" case ever appears, we can add a `non_retryable_error_types_remove` list later.

Replaces every direct `worker_config.retry_policy` / `worker_config.workflow_execution_timeout` read at dispatch sites. One method on `WorkerConfig` returns the bundle.

### Worker side — `resolve_runtime_profile(profile_name | None)`

```
profile_name or worker_runtime_profiles.default_profile  →  the WorkerRuntimeProfile
```

The worker process composes:

```python
runtime_profile = resolve_runtime_profile(args.profile)
queue_opts = get_config().temporal.queue_options.get(args.task_queue)

worker = Worker(
    client,
    task_queue=args.task_queue,
    workflows=workflows,
    activities=activities,
    # from runtime_profile (worker-local):
    max_concurrent_activities=runtime_profile.max_concurrent_activities,
    max_activities_per_second=runtime_profile.max_activities_per_second,
    max_concurrent_workflow_tasks=runtime_profile.max_concurrent_workflow_tasks,
    # …all the others…
    # from queue_options (cluster-wide, attached to the queue this worker polls):
    max_task_queue_activities_per_second=(
        queue_opts.max_task_queue_activities_per_second if queue_opts else None
    ),
)
```

## CLI

`pipelex worker` gains a `--profile` flag.

```bash
pipelex worker                                    # uses default_profile + default_scope + default_task_queue
pipelex worker --profile anthropic-tier4 --scope runner-llm --task-queue anthropic_q
pipelex worker --profile image-gen-heavy --scope runner-img-gen --task-queue image_gen_q
pipelex worker --profile router --scope router --task-queue temporal_task_queue
```

Three orthogonal axes:

| Flag | Selects from | Controls |
| --- | --- | --- |
| `--scope` | `worker_scopes.scopes` | Which workflows/activities this process **registers** |
| `--profile` | `worker_runtime_profiles.profiles` | How the `Worker(...)` is **tuned** |
| `--task-queue` | (free string) | Which queue this worker **polls** |

The fourth dimension — what server to connect to — already lives in `temporal.temporal_config.selected_server` (and is process-wide). Not a per-worker flag because typical deployments connect every worker in a cluster to the same Temporal server. Override that via env override on `selected_server` if needed.

## Startup validation

Two layers — one lenient (catches likely typos), one strict (catches the CLI-side typo that would silently misroute traffic).

**Lenient (warn, don't fail).** When the config loads, for every queue name referenced in `activity_queues.*.default` and `activity_queues.*.by_handle.*` that has no corresponding `queue_options.<queue>` entry, log a WARN:

```
WARN  temporal: queue 'anthrpic_q' is referenced by activity_queues.act_llm_gen_text.by_handle["claude-opus-4-7"] but has no queue_options entry — it will use worker_config defaults. Typo?
```

Rationale: a queue ridding worker_config defaults is a legitimate state (small deployments don't need per-queue tuning), so this isn't a fatal error. But the message is loud enough that typos surface in CI / on first boot.

**Strict (fail at worker startup).** When `pipelex worker --task-queue <X>` is invoked, refuse to start if `<X>` doesn't appear in **any** of:

- `worker_config.default_task_queue`
- `activity_queues.*.default`
- `activity_queues.*.by_handle.*`
- `queue_options.*`

Rationale: a worker polling a queue that nothing routes to is a typo. The runtime can't *detect* that no activity will ever land — it would just sit there idle. Fast-fail at boot:

```
ERROR temporal: --task-queue 'anthrpic_q' is not referenced by any routing or options entry.
       Known queues: ['temporal_task_queue', 'anthropic_q', 'openai_q', 'image_gen_q', 'extract_q']
       Did you mean 'anthropic_q'?
```

The "did you mean" suggestion uses simple Levenshtein matching against the known-queue set.

**Not validated at startup** (deferred): "every named queue has at least one worker polling it." That requires a deployment registry the Pipelex runtime doesn't have. An operator who wants this check can add a pre-deploy step that diffs their docker-compose / k8s manifest against the TOML.

## Deployment manifest shape

A docker-compose excerpt (illustrative — Pipelex doesn't own the orchestrator config; this is what an operator writes):

```yaml
services:
  router:
    image: my-org/pipelex:latest
    command: pipelex worker --profile router --scope router --task-queue temporal_task_queue
    deploy: { replicas: 2 }

  worker-llm-anthropic:
    image: my-org/pipelex:latest
    command: pipelex worker --profile anthropic-tier4 --scope runner-llm --task-queue anthropic_q
    deploy: { replicas: 3 }

  worker-llm-openai:
    image: my-org/pipelex:latest
    command: pipelex worker --profile openai-tier5 --scope runner-llm --task-queue openai_q
    deploy: { replicas: 2 }

  worker-img-gen:
    image: my-org/pipelex:latest
    command: pipelex worker --profile image-gen-heavy --scope runner-img-gen --task-queue image_gen_q
    deploy: { replicas: 1, resources: { reservations: { devices: [{ capabilities: [gpu] }] } } }

  worker-extract:
    image: my-org/pipelex:latest
    command: pipelex worker --profile extract-batch --scope runner-extract --task-queue extract_q
    deploy: { replicas: 2 }

  worker-jinja2:
    image: my-org/pipelex:latest
    command: pipelex worker --profile jinja2-burst --scope runner-jinja2 --task-queue temporal_task_queue
    deploy: { replicas: 1 }
```

The TOML file declares the named knobs. The manifest declares the deployment shape. Neither knows about the other.

## Local testing via `/temporal-e2e-validate`

The existing skill already runs the 3-process topology (server + worker + submitter). v2 needs:

- A new test scenario in the skill that boots **multiple workers** with different `--profile` / `--scope` / `--task-queue` combinations, then submits work whose `(activity_name, handle)` pairs route to each queue, and verifies each activity executed on the worker registered for it.
- Per-queue option assertions: schedule an activity that would time out on the default budget but succeeds with the `extract_q` budget; confirm the workflow used the queue-resolved timeout.
- Rate-limit assertion: schedule a burst, confirm the worker-local cap or server-side cap actually throttles (a tight burst above `max_activities_per_second` should produce visible `schedule_to_start` latency — assert through workflow history events, not wall-clock).
- A negative scenario: misconfigured worker (queue declared in TOML but no worker polling it) — the submitter should report a clear `schedule_to_start` timeout, not hang silently. (We may add an optional **startup validator** that checks "every queue named in `queue_options` or `activity_queues.*.default/by_handle` is polled by at least one declared worker in a manifest registry" — but that requires a deployment registry, which is out of scope for v2 unless the operator opts in.)

The 3-process test already proves the cross-worker hop is real. v2 extends it to a 5-process test (1 router + N runner profiles + 1 submitter) so we know per-queue options and per-profile tuning flow correctly end-to-end.

## Heartbeats — deferred (raised here for planning)

`heartbeat_timeout` ships on `QueueOptions` in v2 so the schema is ready, but **no current Pipelex activity actually emits heartbeats**. Temporal heartbeats are explicit: the activity code calls `activity.heartbeat(...)` in its loop, and if no heartbeat arrives within `heartbeat_timeout`, Temporal reschedules the activity (assuming worker death). Setting `heartbeat_timeout` on an activity that doesn't heartbeat does nothing useful.

Activities that *could* meaningfully heartbeat:

- **Anthropic LLM (streaming)** — `act_llm_gen_text` / `act_llm_gen_object` on streaming backends. Could emit one heartbeat per chunk or every N tokens. Detects dead workers within seconds instead of waiting for `start_to_close_timeout`.
- **Image generation with polling backends** (Fal-style "is it done yet" loops). One heartbeat per poll cycle.
- **Extract on batch backends** if they expose progress callbacks.

Activities that **cannot** heartbeat without changing their shape: anything that's "send one HTTP request, await one response." That's most of our LLM activities today (non-streaming OpenAI, non-streaming Anthropic, non-streaming Gemini, etc.). Adding heartbeats there would require interleaving a heartbeat task alongside the HTTP call, which is plausible but invasive.

**v2 leaves the call sites untouched.** The schema field exists, queue_options can set the timeout, but until call sites are wired up, the value has no effect.

**Planning hint for a future pass:**

1. Decide the cadence policy per queue. E.g. `anthropic_q`: heartbeat every 5s (covers streaming dropouts); `image_gen_q`: heartbeat every 30s (covers Fal polling).
2. Identify the activities that have a natural loop. Modify them to call `activity.heartbeat(progress_info)` inside the loop.
3. For activities without a natural loop, decide whether to spin a background heartbeat task during the request (a small async helper around the HTTP call). Probably not worth it for fast LLM calls; possibly worth it for slow extract batch jobs.
4. Tune `max_heartbeat_throttle_interval` and `default_heartbeat_throttle_interval` on the worker side (already in `WorkerRuntimeProfile`) so the throttling matches the call-site cadence.

This is its own design pass. v2 just ensures the config surface won't have to change when we get to it.

## Migration

Breaking, single-step (per project policy: no compat shims). For each existing client config:

| Before | After |
| --- | --- |
| `[temporal.worker_config].task_queue` | `[temporal.worker_config].default_task_queue` |
| `[temporal.worker_config].workflow_execution_timeout` doubling as activity timeout | New `[temporal.worker_config].default_activity_start_to_close_timeout`; existing `workflow_execution_timeout` reverts to its real meaning |
| Hardcoded `max_*` in `make_worker` (`temporal_task_manager.py:120-138`) | `[temporal.worker_runtime_profiles.default]` (ship with current values as the default profile) |
| `pipelex/temporal/wrapper/activity.py` (`start_tprl_activity`) | **Delete the file.** Confirmed zero callers. Not part of any current dispatch path. |

A migration map entry under `[migration.migration_maps.temporal]` renames the `task_queue` key automatically. The new fields have explicit defaults shipped in `pipelex/pipelex.toml`. Client `.pipelex/pipelex.toml` files that previously overrode `task_queue` need a one-line edit.

## Decisions taken

All six original open questions are resolved.

1. **Heartbeat timeout granularity.** `heartbeat_timeout` lives on `QueueOptions` only. Not on `HandleOptions` — backend rhythm is a queue-scope property. Per-handle override can be added later if a single model on a backend ever needs a different cadence; schema change is one line. See **Heartbeats — deferred** above for the broader picture: the *call sites* that actually emit heartbeats aren't in scope for v2; this design only ships the configuration surface.
2. **`non_retryable_error_types` composition.** Additive across layers. Per-queue and per-handle layers contribute `non_retryable_error_types_extra` lists that union with the worker_config baseline. The safety-leaning default; matches the realistic use case (backend-specific 4xx classes).
3. **Startup validation.** Two-layer:
   - **WARN** on routing entries that reference a queue with no `queue_options` entry (lenient — a queue ridding worker_config defaults is legitimate).
   - **FAIL** on `pipelex worker --task-queue X` when `X` doesn't appear anywhere in routing/options/default queue (strict — catches CLI typos that would silently misroute traffic). Error message includes a "did you mean?" suggestion.
4. **Resource-based tuning.** Reserved as `WorkerTuningMode.RESOURCE_BASED` in the enum but rejected by a `@model_validator` in v2 with a clear "not implemented yet" message. Ships only `tuning_mode = "explicit"`. Adding the resource-based path later won't break the schema.
5. **Per-worker server override.** Not added. Process-wide `temporal.temporal_config.selected_server` stays the only knob. Adding the CLI flag now would freeze surface we don't need.
6. **Pretty resolver tracing.** Add behind a new `temporal_log_config.is_dispatch_resolution_traced` flag, **off by default**. When on, each `workflow.execute_activity` dispatch logs the resolved queue + start_to_close_timeout + retry_policy and the layer each value came from (baseline / queue_options / handle_options). Verbose but invaluable when a timeout is mis-tuned.

## What this does *not* change

- The `temporal-e2e-validate` skill's overall execution model.
- `worker_scopes` registration logic (v1).
- `activity_queues` routing logic (v1) — `by_handle` keys still resolve to plain queue names; `handle_options` is a sibling table.
- The payload codec, server connection, log config sections.
- The `make_temporal_pipe_router` factory shape (it'll just consume the new resolver internally).
