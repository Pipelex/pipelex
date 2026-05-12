# Temporal IDs and Naming — Design

## Status

**Implemented.** Phases 1–6 shipped on `feature/Temporal-ids` (latest: commit `c89674f5`, Phase 6 hard-fail worker boot + configurable search attributes + setup CLI). See `02-id-and-naming-plan.md` for the per-phase execution log and checkpoint notes. This doc remains the authoritative reference for the architectural decisions.

Reads cleanly with the primitives catalogued in `00-temporal-id-primitives.md`. The original problem statement (`workflow-and-activity-ids.md`) and the pre-checkpoint plan (`id-and-naming-plan.md`) are archived under `wip/archive/`.

Decisions taken in this session, recorded so the next session does not reopen them:

- **Workflow ID.** Top-level Workflow ID is `{env_prefix}{pipeline_run_id}` — the existing UUID from `JobMetadata`, with the existing run-mode prefix (`ut-`, `ci-`, `cc-`, `cct-`, or empty). No session truncation, no random suffix, no class name.
- **Activity ID.** No customization. The Temporal Python SDK auto-assigns sequential integers; Pipelex never passes `activity_id=`. The worker-singleton LRU and `is_replaying()` short-circuit in `content_generator_in_workflow.py` are deleted.
- **Search attributes.** Five custom Keyword search attributes (`PipeCode`, `PipelineRunId`, `SessionId`, `UserId`, `DomainCode`) are registered once per namespace and set on every workflow start.
- **`wfid` parameter.** Dropped from `PipeRunProtocol`, `PipeRouterProtocol`, `ContentGeneratorProtocol`, all implementations, and every call site. Identity flows entirely via `JobMetadata.pipeline_run_id` and `pipe_job.pipe.code`; observability is auto-derived.

## Guiding principle

Pipelex already mints the right identifiers: `pipeline_run_id`, `pipe_code`, `domain_code`, `user_id`, `session_id`. The Temporal layer does not need to invent its own — it threads Pipelex's identity model through Temporal's primitives one-for-one. Anything that diverges from this principle (truncated session prefixes, random suffixes, class names embedded in the Workflow ID, an `activity_id` co-opted from a workflow-id parameter) is a defect to be removed, not a convention to be preserved.

The redesign maps Pipelex identity to Temporal identity on a single sheet:

| Pipelex concept | Temporal primitive |
|---|---|
| `pipeline_run_id` (UUID from `PipelineFactory`) | Workflow ID (top-level) |
| Implicit "child role" (a router under a run, a sub-pipe under a router) | Suffix appended to parent's Workflow ID |
| Pipe family | Workflow Type (registered: `wf_pipe_run`, `wf_pipe_router`) |
| Generation method (`make_llm_text`, …) | Activity Type (registered: `act_llm_gen_text`, …) |
| One call to a generator method inside a workflow | Activity ID (SDK-default integer) |
| `pipe_code` | Search attribute `PipeCode` + leading segment of `static_summary` |
| `domain_code` | Search attribute `DomainCode` |
| `user_id` | Search attribute `UserId` |
| `session_id` | Search attribute `SessionId` |
| Pipe description | Tail of `static_summary` |
| Per-call observability context (model handle, class name, etc.) | Per-activity `summary` |

No information is lost on the way down; no information is invented along the way.

## The four layers

### Layer 1 — Identity (the IDs)

#### Top-level Workflow ID

```
{env_prefix}{pipeline_run_id}
```

- `env_prefix` is selected from `runtime_manager.run_mode` (unchanged from today's `make_top_workflow_id`): `ut-`, `ci-`, `cc-`, `cct-`, or empty for `NORMAL`.
- `pipeline_run_id` is the existing UUID from `JobMetadata.pipeline_run_id`, set upstream by `PipelineFactory.make_pipeline_run_id`. The design treats it as an opaque string; callers who want a stable id pass one to `PipelineFactory.make_pipeline`.

Examples:

- `ut-3f9c8b2a-1e4d-4f5b-9c7a-2d8e1f0a6b3c`
- `ci-3f9c8b2a-1e4d-4f5b-9c7a-2d8e1f0a6b3c`
- `3f9c8b2a-1e4d-4f5b-9c7a-2d8e1f0a6b3c`

`WorkflowIDReusePolicy` stays at the SDK default (`ALLOW_DUPLICATE`). Pipelex semantics are "a new run is a new run": if a caller reuses a `pipeline_run_id`, Temporal accepts the new workflow execution under the same chain with a fresh `run_id`. Pipelex does not rely on Temporal-side ID uniqueness for anti-replay; that protection belongs upstream.

#### Child Workflow ID

```
{parent_workflow_id}/{suffix}
```

The separator is `/`, not `-`. UUIDs already contain `-`, and a different separator keeps the path structure unambiguous to humans and trivial to parse with `split("/")`.

Two suffix conventions, applied at the two existing construction sites:

- **Fixed-role child (1:1, known role).** Used by `wf_pipe_run` when it spawns `wf_pipe_router` as its sole child. Suffix is the role name: `pipe-router`. Example: `ut-3f9c…b3c/pipe-router`.
- **Dynamic child (router-spawned sub-pipe).** Used by `TemporalPipeRouter._run_pipe_job` inside a workflow when it dispatches another workflow for a sub-pipe. Suffix is `{pipe_code}-{disambiguator}`. Example: `ut-3f9c…b3c/pipe-router/translate_doc-7c1e2f8a`.

The disambiguator is `str(workflow.uuid4())[:8]` — replay-safe (Temporal's `workflow.uuid4()` is deterministic) and 32 bits is comfortably enough entropy for siblings of a single parent. The `pipe_code` prefix gives the path its semantic readability; the uuid suffix guarantees siblings cannot collide even when the same pipe is spawned multiple times by the same parent.

Nested paths look like `ut-3f9c…b3c/pipe-router/translate_doc-7c1e2f8a/extract_text-4d9b1c83/…`. At ~25 chars per level, the design comfortably stays under Temporal's 1000-character Workflow ID ceiling for deep nesting.

#### Activity ID

The `activity_id=` argument is **never passed** by Pipelex code. Temporal's Python SDK auto-assigns sequential integers (`"1"`, `"2"`, …) per workflow run. These ids are:

- Unique per `(workflow_id, run_id)` by construction.
- Deterministic across replay (assigned by history position).
- Visible in Event History next to the Activity Type and per-activity summary.

This removes the entire reason the worker-singleton LRU exists in `content_generator_in_workflow.py`. The TDD gate test in `test_default_activity_id_collision_bug.py` turns green because the two `make_llm_text` calls now receive activity_ids `"1"` and `"2"`, both unique.

#### Run ID

Server-assigned. Today's code uses `(workflow_id, run_id)` as a key on the LRU; after the LRU is deleted, Pipelex does not touch `run_id` except to read it for diagnostics.

### Layer 2 — Type / Name (registered)

#### Workflow Type

Unchanged. Two registered types:

- `wf_pipe_run` — top-level orchestrator that runs the router then delivery.
- `wf_pipe_router` — runs one pipe (controller or operator).

No dynamic registration of per-pipe workflow types. Filtering by pipe in the dashboard goes through the `PipeCode` search attribute, which is the right Temporal primitive for that need. The cost of registering one workflow type per pipe family (worker fleet consistency, registration logistics) outweighs the benefit when search attributes already give us a filterable column.

#### Activity Type

Unchanged. The registered activity functions (`act_llm_gen_text`, `act_llm_gen_object`, `act_llm_gen_object_list`, `act_img_gen_images`, `act_jinja2_gen_text`, `act_render_page_views`, `act_extract_gen_extract_pages`, `act_assemble_graph`, `act_flush_trace_events`, `act_deliver`) already carry the right semantic granularity. The bug was at the id layer, not the type layer.

### Layer 3 — Observability (display only)

These fields do not affect identity or routing. They are the operator-facing surface. Pipelex uses zero of them today.

#### Static Summary

Set once at top-level workflow start, on the submitter side, via the `static_summary=` argument to `client.start_workflow` / `client.execute_workflow`. 200-byte limit, single-line Markdown.

Format:

```
{pipe_code} — {description}
```

- `pipe_code` comes from `pipe_job.pipe.code`.
- `description` comes from `pipe_job.pipe.description` if present; otherwise the dash and tail are omitted.
- The combined string is truncated to fit 200 bytes (UTF-8), with a trailing `…` if truncated.

Example: `translate_doc — Translate a document from English to French`.

#### Static Details

Set once at top-level workflow start, alongside Static Summary. 20 KB limit, multi-line Markdown.

Contents (markdown table):

```markdown
| Field | Value |
|---|---|
| Pipe | `translate_doc` |
| Domain | `documents` |
| Pipeline run | `3f9c8b2a-1e4d-4f5b-9c7a-2d8e1f0a6b3c` |
| User | `acme-corp` |
| Session | `EdgdJ7Yk4Q3HF2pXyZv9w8` |
| Library crate | `documents@2.1.4` |
| Input | `working_memory keys: source_text, target_language` |
```

Library crate version and the input-shape line are best-effort — emitted when available, omitted otherwise. No exception is raised if the optional fields cannot be derived; the section simply shrinks.

#### Current Details

Not used in v1. The architecture supports adding this later from inside `WfPipeRouter` (e.g. `workflow.set_current_details(f"Executing {controller}…")`) to surface in-flight progress in the dashboard. Tracked in **Out of scope / future work**.

#### Per-Activity Summary

Set on every `workflow.execute_activity(...)` call via `summary=`. 200-byte limit. This is the field that carries the per-call meaning that previously (incorrectly) lived in `activity_id`.

Format by method, where `{pipe_code}` is read from `job_metadata.pipe_code`:

| Method | Summary format |
|---|---|
| `make_llm_text` | `LLM text · pipe={pipe_code} · model={llm_handle}` |
| `make_object` | `LLM object · pipe={pipe_code} · class={class_name}` |
| `make_object_list` | `LLM object list · pipe={pipe_code} · class={class_name}` |
| `make_single_image` | `Img gen 1× · pipe={pipe_code} · model={img_gen_handle}` |
| `make_image_list` | `Img gen N× · pipe={pipe_code} · model={img_gen_handle} · n={nb_images}` |
| `make_templated_text` | `Templated text · pipe={pipe_code}` |
| `make_render_page_views` | `Render page views · pipe={pipe_code}` |
| `make_extract_pages` (extract step) | `Extract pages · pipe={pipe_code} · handle={extract_handle}` |
| `make_extract_pages` (render step) | `Render page views (extract) · pipe={pipe_code}` |

The platform-level activities (`act_assemble_graph`, `act_flush_trace_events`, `act_deliver`) also get summaries: `Assemble graph · pipeline_run_id=…`, `Flush trace events · n={count}`, `Deliver · pipeline_run_id=… · status={status}`.

If `pipe_code` is unavailable (test fixtures with no pipe), the format degrades gracefully to the method label alone.

### Layer 4 — Search & Filter (custom search attributes)

#### Required namespace registration

Custom Keyword-typed search attributes, registered once per Temporal namespace:

| Attribute | Type | Value source |
|---|---|---|
| `PipeCode` | Keyword | `pipe_job.pipe.code` |
| `PipelineRunId` | Keyword | `pipe_job.job_metadata.pipeline_run_id` |
| `SessionId` | Keyword | `TemporalManager.get_instance().session_id` |
| `UserId` | Keyword | `pipe_job.job_metadata.user_id` |
| `DomainCode` | Keyword | `pipe_job.pipe.domain_code` |

These are required for the Pipelex Temporal integration. The Pipelex side does not register them automatically — the cluster admin runs the equivalent of:

```bash
temporal operator search-attribute create \
  --namespace default \
  --name PipeCode --type Keyword \
  --name PipelineRunId --type Keyword \
  --name SessionId --type Keyword \
  --name UserId --type Keyword \
  --name DomainCode --type Keyword
```

(or the corresponding `tctl` invocation, or the Temporal Cloud UI action.)

A bootstrap check at worker start performs `DescribeNamespace` and logs a clear warning naming any missing attributes, including the exact registration command. The check is a soft fail: in-process test servers (the CI default) skip search attributes entirely, and a dev environment without registration still runs — only the dashboard experience is degraded.

#### Where the values are set

- **Top-level workflow start (submitter side).** `WorkflowExecutor.execute_workflow` and `start_workflow` build the search-attribute dict from `pipe_job` and pass it via `search_attributes=` to `client.execute_workflow` / `client.start_workflow`.
- **Child workflow start (workflow-side).** `TemporalPipeRouter._run_pipe_job` (child branch) and `WfPipeRun` (the fixed `pipe-router` child) pass `search_attributes=` to `workflow.execute_child_workflow` / `workflow.start_child_workflow`. `PipeCode` and `DomainCode` reflect the child's pipe; the other three are inherited unchanged from the workflow context (`workflow_arg.job_metadata` + `TemporalManager`).

Built-in attributes (`WorkflowType`, `WorkflowId`, `StartTime`, `ExecutionStatus`, `TaskQueue`) come for free and need no registration.

#### Memo (v1: minimal)

Memo is left mostly empty in v1. The single planned entry carries non-filterable context for future expansion:

```python
memo = {"pipelex": {"library_crate": "<id>@<version>"}}
```

This is an extension point. Anything that should round-trip with the execution but does not need filtering (OTel trace IDs, dispatch-resolution trace pointers, larger input fingerprints) lives here in later versions.

## Determinism (the why behind each choice)

| Choice | Why it is replay-safe |
|---|---|
| Workflow ID set at submitter side | Set outside workflow code; no replay concern |
| SDK-default `activity_id` | Server-assigned deterministically by history position |
| Child workflow ID uses `workflow.uuid4()` | Temporal's `workflow.uuid4()` is deterministic by design |
| Child workflow ID uses `pipe_job.pipe.code` | Reads from workflow input, not from outside state |
| Search attribute values | Derived from `pipe_job` (workflow input) and `JobMetadata` — deterministic |
| Static summary / details | Set at submit time, outside workflow code |
| Per-activity summary | Derived from `job_metadata` + activity input — no I/O, no time, no randomness |

The LRU + `(workflow_id, run_id)` keying + `is_replaying()` short-circuit in `content_generator_in_workflow.py` existed solely to defend against worker-singleton state issues with the activity-id disambiguator. Once the disambiguator stops existing on the worker singleton (because the SDK assigns it), all of that complexity is unnecessary — and stops being a trap for future contributors.

## Side-by-side: before / after

### Workflow list view (Temporal dashboard)

Before (today):

| Workflow ID | Type | Summary | PipeCode | Status |
|---|---|---|---|---|
| `EdgdJ-HR5fd-TemporalPipeRun-pipe-router` | `wf_pipe_run` | *(empty)* | *(unset)* | Running |
| `EdgdJ-HR5fd-TemporalPipeRun-pipe-router` (child) | `wf_pipe_router` | *(empty)* | *(unset)* | Running |
| `EdgdJ-HR5fd-TemporalPipeRun-pipe-router` (child) | `wf_pipe_router` | *(empty)* | *(unset)* | Running |

After:

| Workflow ID | Type | Summary | PipeCode | Status |
|---|---|---|---|---|
| `ut-3f9c…b3c` | `wf_pipe_run` | `translate_doc — Translate EN→FR` | `translate_doc` | Running |
| `ut-3f9c…b3c/pipe-router` | `wf_pipe_router` | `translate_doc — Translate EN→FR` | `translate_doc` | Running |
| `ut-3f9c…b3c/pipe-router/extract_text-4d9b1c83` | `wf_pipe_router` | `extract_text — Extract paragraphs` | `extract_text` | Running |

### Event history (Temporal dashboard, one workflow)

Before:

```
ActivityTaskScheduled: id=craft-text, type=act_llm_gen_text
ActivityTaskScheduled: id=craft-text, type=act_llm_gen_text    ← collision, workflow crashes
```

After:

```
ActivityTaskScheduled: id=1, type=act_llm_gen_text
  Summary: LLM text · pipe=translate_doc · model=gpt-4o
ActivityTaskScheduled: id=2, type=act_llm_gen_text
  Summary: LLM text · pipe=translate_doc · model=gpt-4o
ActivityTaskScheduled: id=3, type=act_llm_gen_object
  Summary: LLM object · pipe=translate_doc · class=Section
```

### Pipe author API

Before — `wfid` thread through everything, never actually used in production:

```python
async def make_llm_text(
    self,
    job_metadata: JobMetadata,
    llm_setting_main: LLMSetting,
    llm_prompt_for_text: LLMPrompt,
    wfid: str | None = None,    # what is this? who passes it? answer: nobody, only tests
) -> str: ...
```

After — single concern per parameter:

```python
async def make_llm_text(
    self,
    job_metadata: JobMetadata,
    llm_setting_main: LLMSetting,
    llm_prompt_for_text: LLMPrompt,
) -> str: ...
```

Identity (`pipeline_run_id`) and observability (`pipe_code`, `domain_code`, …) flow through `job_metadata`, which is already a required argument. Pipe authors do not think about Temporal ids.

## Detailed change set (the design's footprint in code)

This section specifies what the design implies for the codebase. Sequencing, effort, and risk belong in a separate implementation plan.

### Files modified

**`pipelex/temporal/temporal_manager.py`**

- Replace `make_top_workflow_id(base_id: str)` with `make_top_workflow_id_for_pipeline_run(pipeline_run_id: str)` returning `f"{prefix}{pipeline_run_id}"`. The session-id and random-id pieces are removed from the Workflow ID. `session_id` remains accessible on the manager — it is consumed by the `SessionId` search-attribute builder.

**`pipelex/temporal/tprl/workflow_caller.py`**

- `WorkflowExecutor.make_workflow_id(...)` simplifies to accept a `pipeline_run_id: str` and delegate to the new manager method.
- `execute_workflow` and `start_workflow` accept additional `search_attributes`, `static_summary`, `static_details`, `memo` parameters and pass them through to the SDK.

**`pipelex/temporal/tprl_pipe/temporal_pipe_run.py`**

- Drop the `wfid` parameter from `run(...)` and `start(...)`.
- Compute `pipeline_run_id = pipe_job.job_metadata.pipeline_run_id` and pass to `make_workflow_id`.
- Build and pass the search-attribute dict, static_summary, and static_details from the helpers below.

**`pipelex/temporal/tprl_pipe/temporal_pipe_router.py`**

- Drop the `wfid` parameter from `_run_pipe_job(...)`.
- Top-level branch: same as `temporal_pipe_run.py` — derive workflow id, search attributes, and summary from `pipe_job`.
- Child branch: `child_workflow_id = f"{parent_workflow_id}/{pipe_job.pipe.code}-{str(workflow.uuid4())[:8]}"`. Pass updated search attributes (`PipeCode` + `DomainCode` reflect the child's pipe; others inherit from the workflow argument's `job_metadata` and `TemporalManager`).

**`pipelex/temporal/tprl_pipe/wf_pipe_run.py`**

- Line 46: change `f"{workflow.info().workflow_id}-pipe-router"` to `f"{workflow.info().workflow_id}/pipe-router"` (separator switch).
- Pass `search_attributes=` to the `execute_child_workflow` call. `PipeCode` does not change between `wf_pipe_run` and its `wf_pipe_router` child (it is the same pipe — the router is just executing it), so the search attributes from the parent are reused unchanged.

**`pipelex/temporal/tprl_content_generation/content_generator_in_workflow.py`**

- Delete `_seen_activity_ids`, `_MAX_SEEN_RUNS`, and `_record_activity_id`. Delete every call site of `_record_activity_id`.
- Drop the `wfid` parameter from every `make_*` method signature.
- Drop the `activity_id = wfid or "…"` line from every method.
- Drop the `activity_id=activity_id` argument on every `workflow.execute_activity(...)` call (SDK auto-generates).
- Add `summary=` per the per-activity-summary format table.

**`pipelex/cogt/content_generation/content_generator_protocol.py`**

- Drop `wfid` from every `make_*` method signature.

**`pipelex/cogt/content_generation/content_generator.py`** (direct mode), **`content_generator_dry.py`** (dry mode)

- Drop `wfid` parameters. Direct mode and dry mode never used the value for anything anyway.

**`pipelex/pipe_run/pipe_run.py`, `pipe_run_protocol.py`**

- Drop `wfid` from `run(...)`.

**`pipelex/pipe_run/pipe_router.py`, `pipe_router_protocol.py`, `dry_pipe_router.py`**

- Drop `wfid` from `run(...)` and `_run_pipe_job(...)`.

### Helpers to be added

A new module `pipelex/temporal/tprl/observability.py` consolidates the formatting policy in one place:

- `build_search_attributes(pipe_job: PipeJob) -> Mapping[str, list[str]]` — returns the dict for top-level workflow start.
- `build_search_attributes_for_child(child_pipe_job: PipeJob, parent_search_attrs: Mapping[str, list[str]]) -> Mapping[str, list[str]]` — updates `PipeCode` + `DomainCode` for a child pipe; inherits the rest.
- `build_static_summary(pipe: PipeBase) -> str` — returns the 200-byte-truncated summary string.
- `build_static_details(pipe_job: PipeJob, library_crate_id: str | None) -> str` — returns the markdown details block.
- `build_activity_summary(method_label: str, job_metadata: JobMetadata, **extras: str) -> str` — returns the 200-byte-truncated per-activity summary string.

A single home for the formatting policy keeps the call sites (in `content_generator_in_workflow.py`, `temporal_pipe_run.py`, `temporal_pipe_router.py`, `wf_pipe_run.py`) thin and trivially unit-testable.

### Tests

**To delete or rewrite:**

- `tests/unit/pipelex/temporal/test_content_generator_in_workflow.py::test_make_llm_text_threads_explicit_wfid` — concept no longer exists.
- `…::test_duplicate_wfid_raises_content_generation_error` — concept no longer exists (no duplicate to raise; LRU is gone).
- `…::test_default_wfids_for_image_methods_are_distinct` — concept no longer exists; replaced by an assertion that `activity_id` is unset (SDK default) and per-activity summaries are correctly populated.

**To turn green naturally (the TDD gate):**

- `tests/unit/pipelex/temporal/test_default_activity_id_collision_bug.py::test_two_make_llm_text_calls_without_wfid_should_succeed` — passes because `activity_id` is no longer customized; SDK assigns `"1"` then `"2"`.
- `…::test_two_make_llm_text_calls_with_same_explicit_wfid_should_succeed` — the test's call site cannot pass `wfid` after the parameter is dropped; the test collapses into the first one, so one of the two becomes the canonical regression gate.

**To add:**

- `test_workflow_id_construction.py` — top-level `{env_prefix}{pipeline_run_id}` shape and child slash-separated nesting (fixed-role and dynamic).
- `test_search_attribute_dict_construction.py` — the five keys and their value sources for representative `pipe_job`s.
- `test_observability_helpers.py` — `build_static_summary`, `build_static_details`, `build_activity_summary`, including the 200-byte truncation behavior.

## Answers to the open questions in the reference doc

Mapping every question from `temporal-id-primitives.md` §7 to a decision:

1. **Workflow ID shape.** `{env_prefix}{pipeline_run_id}`. Pipelex's existing UUID with the existing run-mode prefix. No info loss, no invented fields.
2. **Child workflow id derivation.** `{parent_workflow_id}/{role-or-pipe_code-and-uuid8}`. Slash separator for clarity; role-name suffix for fixed 1:1 children; `{pipe_code}-{workflow.uuid4()[:8]}` for dynamic ones.
3. **Activity id policy.** SDK-default integers. No customization. The disambiguator concern disappears with the LRU.
4. **Workflow Type granularity.** Stay with the small registered set (`wf_pipe_run`, `wf_pipe_router`). Filter by `PipeCode` search attribute instead of registering one type per pipe.
5. **Summary / details strategy.** `static_summary` = `{pipe_code} — {description}`; `static_details` = markdown table of identity + crate + input shape; `current_details` deferred to a later iteration.
6. **Search attribute schema.** `PipeCode`, `PipelineRunId`, `SessionId`, `UserId`, `DomainCode` — all Keyword.
7. **Memo contents.** Minimal in v1 (optional `library_crate` fingerprint). Reserved as extension point for non-filterable context (OTel pointers, dispatch trace pointers, larger fingerprints) in later versions.
8. **`wfid` parameter rename.** Dropped, not renamed. Identity flows entirely via `JobMetadata.pipeline_run_id`; observability is auto-derived from `pipe_code` / `domain_code`. No caller hint is needed for either purpose.

## Breaking changes (per `CLAUDE.md`, no transition period)

- Workflow ID format changes from `{env}{session5}-{rand5}-{ClassName}` to `{env_prefix}{pipeline_run_id}`. Any operational tooling that grepped for the old shape is updated.
- The `wfid` parameter is removed from public protocols (`PipeRunProtocol`, `PipeRouterProtocol`, `ContentGeneratorProtocol`). No production code passed it; tests are the only blast radius.
- Activity IDs change from semantic labels (`craft-text`, `craft-object-direct`, …) to SDK-default integers (`"1"`, `"2"`, …). Anything that filtered or grouped Event History by these strings now reads the per-activity `summary` or the Activity Type.
- Child Workflow ID separator changes from `-` to `/`. Operational tooling parsing the existing nested ID format adapts.

These changes are noted in `CHANGELOG.md` with the implementation.

## Search attribute registration runbook

For the implementer of the runbook step:

- Document the required attributes in `docs/temporal-deployment.md` (new section) with the exact `temporal operator search-attribute create` invocation.
- On worker startup, log a clearly-worded warning if a `DescribeNamespace` call reveals any of the required attributes are missing — the log line includes the exact registration command so the operator does not have to look it up.
- Pipelex Cloud / Temporal Cloud bootstrap scripts add the registration step. Self-hosted Temporal users follow the docs.

The bootstrap check is a soft fail: in-process test servers (CI default) skip search attributes entirely, and a dev environment without registration produces warnings but still runs (with a degraded dashboard experience). A hard fail would block legitimate dev setups for a dashboard-only concern.

## Out of scope / future work

- **Current Details for in-flight progress.** Wire `workflow.set_current_details(...)` inside `WfPipeRouter` to expose controller-by-controller progress in the Temporal dashboard. Useful for long-running pipes; not required to land the redesign.
- **Memo population.** Move the OTel trace pointer, dispatch resolution trace pointer, and any other large or non-filterable context into Memo. Touches the OTel and tracing modules.
- **Per-pipe Workflow Types.** Could register a Workflow Type per pipe family for dashboard-column filterability without search attributes. Rejected for v1 (registration logistics, worker fleet consistency cost) but the door is open if `PipeCode`-search-attribute filtering proves insufficient.
- **Search attribute schema versioning.** A small migration helper to add new attributes on existing namespaces will likely be needed once the v1 schema is in production.
- **Pipe-author DX surface.** With `wfid` gone, the protocol surfaces are clean. A future iteration could add an *optional* `display_label` parameter at the `PipeRun` entry point that prepends to `static_summary` — useful for CLI / test runs that want to tag a run findable in the dashboard. Not required; trivial to add later without breaking anything.
