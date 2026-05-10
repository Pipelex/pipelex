# Per-activity, per-handle Temporal queue routing

> **Status:** WIP design — out of scope for the `tprl_content_generation/` collapse PR (see [`TODOS.md`](../../TODOS.md) Phase 7). Filed as a follow-up after the design conversation that produced it.
>
> **Predecessor context:** `inference_task_queue` was introduced as a quick split-worker test ("LLM goes here, everything else goes to default"). That two-queue model is provisional. This doc proposes the proper general design that supersedes it.

## Problem

Pipelex deployments need worker-pool granularity beyond the current binary "inference / default" split:

- **Per-provider scaling.** OpenAI worker pool scaled separately from Anthropic worker pool — independent rate limits, independent failure isolation, independent cost accounting.
- **Per-model scaling.** A heavy reasoning model (Claude Opus, o1) scaled differently from a fast model (Haiku, GPT-5 nano).
- **Per-activity-class isolation.** Image generation (slow, expensive, heavyweight payloads) on a different pool than LLM text.
- **Per-extract-backend.** OCR backend A on its own pool, backend B on another.

Today the dispatch side cannot express any of this. The registration side (`WorkerScopesConfig`) already supports arbitrary scopes — the gap is on the **dispatch** side, where every LLM call goes to a single `inference_task_queue` and every other activity goes to the workflow's own queue.

## Goals

- Configurable routing of every inference activity (LLM, image-gen, extract) to a named queue based on `(activity_name, runtime_handle)`.
- Single config table. No special-case keys.
- Workflow determinism preserved: routing decision uses only data already serialized into the activity assignment.
- Trivial fallback path: any `(activity, handle)` pair not explicitly mapped falls through to a per-activity default and finally to a worker-wide default queue.
- The "asymmetry" disappears: every inference dispatch site calls the same resolver. Non-inference dispatches don't, and the resolver returns the default for them.

## Non-goals (v1)

- Conditional routing on multiple dimensions (provider AND reasoning_effort AND ...). One key per activity (the handle) is enough until proven otherwise.
- Resolving handles to backends inside the workflow. (See "Provider-resolution problem" below — we route by handle name, not by resolved provider.)
- Routing for orchestration activities (`act_deliver`, `act_assemble_graph`, `act_flush_trace_events`, `act_jinja2_gen_text`, `act_render_page_views`). These have no per-handle dimension; they run on the workflow's own queue.
- Dynamic routing (a callable hook). Static config covers the use cases. Re-evaluate if a real need surfaces.

## The provider-resolution problem

At dispatch time inside the workflow, we have only the model handle string (`LLMSetting.model = "claude-opus-4-7"` or `"@reasoning-fast"` once aliases are resolved). We do **not** have the resolved backend/provider — that resolution lives in `RoutingProfileLibrary` and backend configs, which the workflow can't safely consult (non-determinism, plus pulling the entire model registry into the workflow's deterministic state would be expensive).

**Decision: route by handle, not by provider.** The user already knows which handles map to which backends. Their queue names align with provider/model groupings as a *convention*, not as an enforced derivation. Example:

- `gpt-5` → `openai_q`
- `gpt-5-mini` → `openai_q`
- `claude-opus-4-7` → `anthropic_q`
- `claude-haiku-4-5` → `anthropic_q`

If the user wants to group by provider, they group manually in config. Simple, explicit, deterministic.

## Schema

Replace the current `task_queue: str` + `inference_task_queue: str | None` in `WorkerConfig` with a single per-activity table.

```toml
[temporal.worker_config]
default_task_queue = "temporal_task_queue"

# Per-activity routing tables. Each entry declares:
#   default   = the queue when no per-handle override matches
#   by_handle = optional { handle_name -> queue }
#
# Activities NOT listed here use default_task_queue.

[temporal.worker_config.activity_queues.act_llm_gen_text]
default = "inference_q"
by_handle = { "claude-opus-4-7" = "anthropic_q", "gpt-5" = "openai_q" }

[temporal.worker_config.activity_queues.act_llm_gen_object]
default = "inference_q"
by_handle = { "claude-opus-4-7" = "anthropic_q", "gpt-5" = "openai_q" }

[temporal.worker_config.activity_queues.act_llm_gen_object_list]
default = "inference_q"
by_handle = { "claude-opus-4-7" = "anthropic_q", "gpt-5" = "openai_q" }

[temporal.worker_config.activity_queues.act_img_gen_images]
default = "image_gen_q"
by_handle = { "flux-1.1-pro" = "fal_q", "dall-e-3" = "openai_image_q" }

[temporal.worker_config.activity_queues.act_extract_gen_extract_pages]
default = "extract_q"
by_handle = { "mistral-ocr" = "mistral_extract_q" }
```

Resolution order at dispatch:

1. Look up `activity_queues[activity_name]`.
   - If absent: use `default_task_queue`. Done.
2. Within that block, look up `by_handle[runtime_handle]`.
   - If found: use it. Done.
3. Fall back to that activity's `default`. Done.

Three layers, no surprises.

Pydantic shape:

```python
class ActivityRouteConfig(ConfigModel):
    default: str
    by_handle: dict[str, str] = Field(default_factory=dict)

class WorkerConfig(ConfigModel):
    default_task_queue: str
    activity_queues: dict[str, ActivityRouteConfig] = Field(default_factory=dict)
    # ... existing timeout / retry fields unchanged
```

## Per-activity routing keys

The dispatcher extracts the routing key from each assignment shape. All three handles already exist on the assignment models — no model-shape changes required.

| Activity | Assignment | Routing key |
| --- | --- | --- |
| `act_llm_gen_text` | `LLMAssignment` | `llm_assignment.llm_handle` (= `llm_setting.model`) |
| `act_llm_gen_object` | `ObjectAssignment` | `object_assignment.llm_assignment_for_object.llm_handle` |
| `act_llm_gen_object_list` | `ObjectAssignment` | same as above |
| `act_img_gen_images` | `ImgGenAssignment` | `img_gen_assignment.img_gen_handle` |
| `act_extract_gen_extract_pages` | `ExtractAssignment` | `extract_assignment.extract_handle` |
| `act_render_page_views` | `RenderPageViewsAssignment` | none — uses `default_task_queue` |
| `act_jinja2_gen_text` | `TemplatingAssignment` | none — uses `default_task_queue` |
| `act_deliver`, `act_assemble_graph`, `act_flush_trace_events` | various | none — `default_task_queue` |

Definitions verified against `pipelex/cogt/content_generation/assignment_models.py` (LLM/ImgGen/Extract assignments all expose their handle directly).

## Dispatcher

A single resolver lives next to `WorkerConfig`:

```python
def resolve_queue(
    worker_config: WorkerConfig,
    activity_name: str,
    routing_key: str | None = None,
) -> str:
    activity_route = worker_config.activity_queues.get(activity_name)
    if activity_route is None:
        return worker_config.default_task_queue
    if routing_key is not None:
        per_handle = activity_route.by_handle.get(routing_key)
        if per_handle is not None:
            return per_handle
    return activity_route.default
```

Each `make_*` method in `ContentGeneratorInWorkflow` extracts its own routing key and calls `resolve_queue`:

```python
queue = resolve_queue(
    worker_config,
    activity_name="act_llm_gen_text",
    routing_key=llm_assignment.llm_handle,
)
generated_text = await workflow.execute_activity(
    act_llm_gen_text,
    arg=llm_assignment,
    task_queue=queue,
    start_to_close_timeout=worker_config.workflow_execution_timeout,
    retry_policy=worker_config.retry_policy,
    activity_id=activity_id,
)
```

Every dispatch site uses the same shape — `task_queue=queue`. Activities that don't need per-handle routing pass `routing_key=None`, get the default queue back, and the kwarg is uniform across all sites. The "asymmetric kwarg" disappears.

## Worker registration: matching scopes to queues

A worker in this design picks a **scope** (which activities to register) AND **one or more queues** (which task queues to listen on). `WorkerScope` already maps cleanly to "set of activities". Two viable options for queue assignment:

**Option 1 — Scope declares its queues** (cleaner — scope is the deployment unit):

```toml
[temporal.worker_scopes.scopes.openai_runner]
required_activities = ["act_llm_gen_text", "act_llm_gen_object", "act_llm_gen_object_list"]
disable_all_workflows = true
listen_queues = ["openai_q"]   # NEW

[temporal.worker_scopes.scopes.anthropic_runner]
required_activities = ["act_llm_gen_text", "act_llm_gen_object", "act_llm_gen_object_list"]
disable_all_workflows = true
listen_queues = ["anthropic_q"]   # NEW
```

**Option 2 — CLI flag overrides the queue** (current model extended). Already exists in `worker_cli.py:48` (`--task-queue`). Could grow `--task-queue-extra` for multi-queue listening.

Lean toward Option 1 — the scope captures the full deployment intent in one place. Decide during implementation.

## Migration from `inference_task_queue`

Per the project's "no backward compatibility" rule, the field is deleted in the same release with a CHANGELOG note. If a transition is wanted anyway, the loader can synthesize entries:

```python
if legacy_inference_queue is not None:
    for activity_name in ("act_llm_gen_text", "act_llm_gen_object", "act_llm_gen_object_list"):
        if activity_name not in activity_queues:
            activity_queues[activity_name] = ActivityRouteConfig(default=legacy_inference_queue)
```

Default config in `pipelex.toml` would set `default_task_queue = "temporal_task_queue"` and leave `activity_queues` empty — same effective behavior as today's "everything on the default queue" baseline.

## Validation

Two cheap startup validators worth adding:

1. **No orphan queues.** Every queue named in `activity_queues` (as `default` or in `by_handle`) should be covered by at least one `WorkerScope.listen_queues` (Option 1) or by some configured worker. Misconfigured deployments where a queue has no listeners would hang forever — fail fast at boot.
2. **No unknown activities.** Every key in `activity_queues` should match a registered activity name. Catches typos.

## Open questions

1. **Naming.** `default_task_queue` (more explicit) vs keeping `task_queue` (less churn). Slight lean toward keeping `task_queue` for the smallest diff.
2. **Multi-queue workers.** Temporal SDK lets one worker listen on N queues (must register all their activities). With per-provider routing, a "general inference fallback" worker that listens on multiple queues could absorb overflow. Out of scope for v1; design accommodates it via Option 1's `listen_queues`.
3. **Per-pipe routing override.** A user might want one specific pipe's LLM call to go to a special queue (a long-running pipe to a dedicated pool). Skip for v1 — handles cover the use case.
4. **Dynamic routing hook.** Skip for v1. Document the escape hatch (custom Python helper) as a v2 consideration if a use case appears.
5. **Where does the resolver live?** Options: a new tiny module `pipelex/temporal/queue_routing.py`; a method on `WorkerConfig`; a free function next to `WorkerConfig`. Method-on-config keeps it discoverable; free function is easier to mock. Slight lean toward method.

## What stays unchanged

- `WorkerScope` and `WorkerScopesConfig` (registration): no schema change beyond Open Question #2's optional `listen_queues`.
- Activity definitions (`@activity.defn(name=...)`): no change.
- Workflow code: no change beyond replacing the asymmetric kwarg with `task_queue=resolve_queue(...)`.
- Assignment models: no change. The handles are already there.

The change surface is concentrated in:

- `pipelex/temporal/config_temporal.py` (`WorkerConfig` schema + `ActivityRouteConfig`)
- `pipelex/temporal/tprl_content_generation/content_generator_in_workflow.py` (call sites use the resolver)
- A new tiny resolver (free function or method on `WorkerConfig`)
- `pipelex.toml` (default config: empty `activity_queues`, single `default_task_queue`)
- Tests (unit tests for the resolver; integration test that exercises per-handle routing in a split-worker setup)
- Docs (CHANGELOG; under-the-hood section on queue routing)

## Test plan (sketch)

- **Unit:** `resolve_queue` covers all three layers — unmapped activity → default; mapped activity, unmapped handle → activity default; mapped activity, mapped handle → per-handle queue.
- **Integration:** a split-worker setup with two named runners (e.g. `openai_runner` listening on `openai_q`, `anthropic_runner` listening on `anthropic_q`). Submit a workflow that dispatches an LLM call with each handle and assert via `WorkflowHandle.fetch_history()` that the activity landed on the expected queue.
- **Negative:** the boot-time validators catch (a) a queue with no listeners and (b) an unknown activity name in `activity_queues`.

## Relationship to current PR (`refactor/Temporal-primitives`)

Strictly out of scope. The current PR collapses `tprl_content_generation/` workflow types to direct activity dispatch — that surface is exactly the place where this routing change will land, but the routing change itself is a separate concern with its own design and migration story. The current PR survives with a tiny `_inference_dispatch_kwargs(worker_config)` helper that isolates the existing two-queue logic to a single deletion point (see `TODOS.md` Phase 7 — "Stopgap for this PR").
