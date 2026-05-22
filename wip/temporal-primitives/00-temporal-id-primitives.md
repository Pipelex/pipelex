# Temporal Identifiers, Names, and UI Enrichment — A Reference

## Purpose

This is a **read-only reference** of every identifier, name, and UI-enrichment field that Temporal exposes — what is *required* to be unique, what is *required* to be deterministic, what shows up in the Temporal Web UI, and what is just decoration. It is the input to the next session where we redesign Pipelex's workflow/activity naming model.

It deliberately does **not** propose a Pipelex design. It only collects the primitives we get to choose from.

Sources: the bundled `temporal-developer` skill (`references/python/*.md`, `references/core/*.md`) and the official docs at <https://docs.temporal.io>.

---

## 1. The full inventory of identifiers and names

Temporal distinguishes between two very different things in every layer:

- **An ID** — a *runtime* identifier of one *instance* of something (one execution, one activity invocation). Always scoped to a namespace / workflow / task queue. Has hard uniqueness rules.
- **A Type / Name** — a *static* identifier of *what kind of thing* it is (which workflow class, which activity function). Maps to code. Has no per-instance uniqueness rule.

Get those two confused and the design will be wrong before it starts. Pipelex currently conflates them in several places (see "Current Pipelex pain points" below).

### 1.1. Namespace

- Top-level tenant boundary on the Temporal cluster.
- Workflow IDs are unique *within a namespace*. The same workflow ID can be reused in a different namespace.
- Shown in the Web UI as the namespace selector / breadcrumb.
- Not something Pipelex picks per call; it is cluster-config-level.

### 1.2. Workflow ID

- A **user-supplied string**, passed as `id=` to `client.start_workflow` / `client.execute_workflow` / `workflow.execute_child_workflow`.
- **Uniqueness rule.** Unique within `(namespace, set of currently-open workflows)`. Reuse of an ID for a *new* execution is governed by `WorkflowIDReusePolicy` (`ALLOW_DUPLICATE`, `ALLOW_DUPLICATE_FAILED_ONLY`, `REJECT_DUPLICATE`, `TERMINATE_IF_RUNNING`).
- **Reuse via continue-as-new / retry / cron.** Same Workflow ID, new Run ID. The chain is the "Workflow Execution Chain".
- **Required?** Yes — no SDK-generated default. You must pass one. (Conventional samples use `str(uuid.uuid4())`.)
- **Determinism rule for child workflows.** A child workflow ID chosen *from inside* a parent's workflow code must be replay-safe → derive it from parent IDs (e.g. `f"{workflow.info().workflow_id}-child-{n}"`) or use `workflow.uuid4()`. **Never** `uuid.uuid4()` from stdlib.
- **Dashboard visibility.** Yes — it is the primary clickable identifier of an execution in every list and detail view. Searchable. Filterable.
- **Use as.** The thing humans grep for. The thing oncall pastes into the dashboard. The thing your own UI links to.

### 1.3. Run ID

- A **server-assigned UUID**, one per individual run inside a Workflow Execution Chain.
- **Uniqueness rule.** Globally unique. You do not control it; you read it from `workflow.info().run_id` or the start handle.
- **Required?** No — server generates it.
- **Dashboard visibility.** Yes — shown alongside Workflow ID; you can drill into a specific run. Most lists show only the latest run for a given Workflow ID, with a link to "history" for prior runs.
- **Use as.** The disambiguator across continue-as-new / retry / cron. Useful as a key when you need per-run worker-side state (this is what the current `_seen_activity_ids` LRU keys on, for good reason).

### 1.4. Workflow Type (a.k.a. Workflow Name)

- **A static string**, registered with the worker. Defaults to the workflow class name; overridable via `@workflow.defn(name="my_workflow_type")`.
- **Uniqueness rule.** Must be **registered on every worker that polls a given task queue**. All workers on a queue must register the same set of workflow types (one exception: Worker Versioning during upgrades). No per-execution uniqueness — this is the *kind*, not the *instance*.
- **Required?** Yes — implicit (class name) or explicit.
- **Dashboard visibility.** Yes — shown as the **"Workflow Type"** column in every list view, separate from Workflow ID. This is what an operator scans to recognise "what kind of pipeline is this".
- **Why it matters for us.** Today Pipelex registers a small fixed set (`wf_pipe_router`, `wf_pipe_run`, …) so every row looks the same. A redesign could either (a) register more workflow types — one per pipe code, or per family — or (b) keep the registered set small and lean on **search attributes / memo / summary** to surface the pipe code. Both are valid; the trade-off is registration cost vs filterability of the type column itself.
- **Versioning.** Renaming a workflow type is **incompatible** with in-flight executions of the old name. The recommended pattern for major changes is to register `OrderWorkflowV2` alongside `OrderWorkflow`, not to mutate the existing type.

### 1.5. Workflow Execution

- Not an identifier itself — the *concept* of "one run", uniquely keyed by `(namespace, workflow_id, run_id)`.
- Every API call into the cluster (signal, query, cancel, terminate, describe) targets a Workflow Execution by `(workflow_id, [run_id])`. If `run_id` is omitted, the cluster operates on the latest run of that chain.

### 1.6. Activity ID

- A **per-invocation string** identifying *one* call to `workflow.execute_activity(...)`. Can be system-generated or supplied by the workflow.
- **Uniqueness rule.** "Unique among the **open** Activity Executions of a Workflow Run." This is the rule that the current Pipelex bug violates. Once an activity with a given id has completed (or failed terminally), the id can be reused for a fresh activity *within the same workflow run* — but in practice nobody designs for reuse; just give every activity a distinct id.
- **Required?** No — if you pass nothing, the Python SDK generates one (sequential integer string scoped to the workflow run; effectively `"1"`, `"2"`, …). **This is the easy correct default** and is what most user code does.
- **Determinism rule.** Whatever you pass *from inside* workflow code must be replay-safe. Safe sources: `workflow.info().workflow_id`, `workflow.uuid4()`, a workflow-local counter incremented in workflow code (replays produce identical counter values because the code path is identical). Unsafe sources: stdlib `uuid.uuid4()`, `time.time()`, worker-singleton counters, anything that reads outside state.
- **Dashboard visibility.** Yes — shown in the workflow's **Event History** view, on each `ActivityTaskScheduled` event. Not a top-level list column, so its naming matters less than Workflow ID. It is mostly useful (a) when you need to correlate logs / metrics back to a specific call, or (b) when you cancel a specific in-flight activity via its id.
- **Custom value: useful when.** You want logs to read `activity_id=craft-text-for-section-3` rather than `activity_id=7`. Otherwise: don't bother, take the default.

### 1.7. Activity Type (a.k.a. Activity Name)

- **A static string**, the registered name of the activity function. Defaults to the Python function name; overridable via `@activity.defn(name="my_activity_type")`.
- **Uniqueness rule.** Must be registered on every worker polling the relevant task queue. Same rule as Workflow Type. No per-call uniqueness.
- **Required?** Yes — implicit (function name) or explicit.
- **Dashboard visibility.** Yes — shown in Event History on `ActivityTaskScheduled` events, next to the Activity ID. This is what tells an operator "this was an LLM call" vs "this was an OCR call". `act_llm_gen_text` is good. A generic `craft` is bad.
- **Use as.** The semantic label for *what kind of work* happened. Pipelex's current `act_*` names are already reasonable; the bug is at the *id* layer, not here.

### 1.8. Task Queue

- A **named queue** that workers poll for tasks. Specified at `start_workflow` time (workflow tasks) and optionally per-activity (activity tasks default to the parent workflow's queue).
- **Uniqueness rule.** No uniqueness across executions — a task queue is a *channel*, many workflows on the same queue is the normal case. The constraint is that every worker polling the same task queue must register an identical set of workflow types + activity types (modulo Worker Versioning).
- **Dashboard visibility.** Yes — shown per-execution in the detail view; you can list workflows by task queue.
- **Use as.** Routing. Throttling (server-side rate limits apply per task queue). Isolation of worker fleets (e.g. one task queue for GPU activities, one for cheap ones — this is exactly the Pipelex per-activity routing work that recently landed).
- **Naming.** Kebab-case strings, stable across deploys. Naming is purely operational, not for end-user observability.

### 1.9. Worker

- A process polling one or more task queues.
- **No formal "Worker ID"** in the user-visible model. Workers identify themselves by `(task_queue, build_id)` for the Worker Versioning system, and by `identity` (a free-form string, typically `pid@host`) for diagnostics.
- **Dashboard visibility.** Indirect — the dashboard shows workers polling each task queue, with their `identity` and `build_id`, on the task queue detail page.

---

## 2. Determinism cheat-sheet for inside-workflow id generation

When workflow code itself needs to *pick* an id (for a child workflow, for an activity, for anything else), it must be **deterministic across replay**. The same code, replayed, must produce the same id.

| Need | Use | Do NOT use |
|---|---|---|
| Unique-per-call disambiguator | `workflow.uuid4()` | `uuid.uuid4()` from stdlib (sandbox forbids; also non-deterministic) |
| Sequence / counter | Plain Python `int` incremented in workflow code (the *code path* is deterministic, so the counter is too) | A counter living on the worker-singleton instance |
| Derived from parent | `workflow.info().workflow_id`, `workflow.info().run_id` | `os.getpid()`, `socket.gethostname()`, env vars |
| Current time component | `workflow.now()` (note: time progresses *in the workflow* — same value on replay) | `datetime.now()`, `time.time()` |
| Randomness | `workflow.random()` | `random.*` from stdlib |

**Key consequence for Pipelex.** The current LRU on `ContentGeneratorInWorkflow` is a worker-singleton — that's why it has to be keyed by `(workflow_id, run_id)` and gated on `is_replaying()`. Both of those complications **disappear** if the disambiguator lives in workflow-local state (a counter on the workflow class, or `workflow.uuid4()` per call). The singleton survives only because the current design accidentally requires it.

---

## 3. Enrichment primitives — observability without touching ids

Temporal provides several fields that **do not affect ids or routing** but show up in the Web UI and are searchable / filterable. These are the right place to put "operator-readable context" instead of stuffing it into the Workflow ID.

### 3.1. Static Summary

- Set at workflow start: `client.start_workflow(..., static_summary="Order #12345 — expedited shipping")`.
- **Limit:** 200 bytes, single-line, Markdown (no images / HTML / scripts).
- **UI:** Appears in the **Workflow list view**, alongside Workflow ID and Workflow Type. This is the column an operator skims to know "what is this run *about*".
- **Pipelex fit.** Perfect for the pipe code / human-readable label that today is jammed into the Workflow ID.

### 3.2. Static Details

- Same call as static_summary: `client.start_workflow(..., static_details="...")`.
- **Limit:** 20 KB, multi-line, Markdown.
- **UI:** Shown on the workflow's detail page, not in the list. Good for the structured run context (inputs hash, user, session, etc.).

### 3.3. Current Details

- Mutable from inside workflow code: `workflow.set_current_details("Processing chunk 17/42")`.
- **Replay-safe:** can be set multiple times across the run.
- **UI:** Overlays the static details on the detail page; reflects latest state.
- **Pipelex fit.** Phase / step indicator for a pipeline as it progresses through controllers. Costs nothing.

### 3.4. Per-Activity Summary

- Set per-call: `workflow.execute_activity(act_llm_gen_text, ..., summary="Draft section 3, model=gpt-5")`.
- **Limit:** 200 bytes.
- **UI:** Rendered in **purple text** next to the corresponding `ActivityTaskScheduled` event in the Event History view. Visible without expanding the event.
- **Pipelex fit.** This is the *correct* place to put per-call context like "craft-text for `summary_paragraph`" — not in the Activity ID. The id becomes the SDK default integer; the summary carries the meaning.

### 3.5. Per-Timer Summary

- Set per-call: `workflow.sleep(timedelta(minutes=5), summary="Wait for upstream batch")`.
- **Limit:** 200 bytes.
- **UI:** Same purple-text rendering on `TimerStarted` events.

### 3.6. Search Attributes (typed, indexed, filterable)

- Set at start *or* upserted from inside the workflow.
- **Indexed:** these are the only fields you can query with `list_workflows("PipeCode = 'translate_doc'")`.
- **Schema:** custom attributes must be registered on the cluster ahead of time (per-namespace, via `tctl`/`temporal operator search-attribute create`). Built-in ones (`WorkflowType`, `WorkflowId`, `StartTime`, `ExecutionStatus`, `TaskQueue`, …) come for free.
- **Types:** `Keyword`, `Text`, `Int`, `Double`, `Bool`, `Datetime`, plus `KeywordList`.
- **UI:** Shown as filterable columns in the list view; users can build custom views per-namespace.
- **Pipelex fit.** The *queryable* slice of the operator story: `PipeCode`, `SessionId`, `UserId`, `RootPipelineId`. Pair with summary/details for the human-readable slice.

### 3.7. Memo

- Set at start: `client.start_workflow(..., memo={"customer_name": "Acme", "trace_url": "https://..."})`.
- **NOT indexed / searchable** — arbitrary metadata, returned with the workflow handle and visible in the UI but not filterable.
- **Readable from workflow code** via `workflow.memo_value(key, type_hint=...)`.
- **Pipelex fit.** Larger or sensitive context that doesn't need filtering (e.g. dispatch resolution trace pointer, library crate version).

---

## 4. What the Temporal Web UI actually shows you

Approximate column layout in the workflow **list view** (default; users can customise):

| Column | Source |
|---|---|
| Status | Cluster-managed (`Running`, `Completed`, `Failed`, …) |
| Workflow ID | The `id=` you passed at start |
| Run ID | Server-generated, latest of the chain |
| Workflow Type | The `@workflow.defn(name=...)` (or class name) |
| Task Queue | The `task_queue=` you passed at start |
| Start Time | Cluster |
| End Time | Cluster |
| **Summary** | `static_summary` (if set) — purple |
| Custom search attributes | Whatever you registered on the namespace |

In the **detail view** for one execution:

- Header: Workflow ID, Run ID, Workflow Type, Task Queue, Status, Start/End, Summary, Details (static + current).
- Event History: each `ActivityTaskScheduled` shows Activity ID, Activity Type, Task Queue, attempt number, and (if set) the per-activity Summary in purple. Timers show similarly.
- Pending Activities panel: live view of currently-open activities (with their Activity ID — relevant for cancelling a specific one).

What is **not** in the UI by default:

- Memo values (you can see them in the "Memo" tab on the detail page, but they don't filter lists).
- The internal counter Temporal uses to auto-assign default Activity IDs (you just see `"1"`, `"2"`, … on each event).

---

## 5. Naming best practices distilled

### Workflow ID

- **Readable** is good but **stable + unique** matters more.
- Use a deterministic, business-meaningful prefix when possible: `order-{order_id}`, `pipeline-{pipe_code}-{session}-{shortuuid}`.
- Avoid embedding things that change between retries (timestamps fine if you want chain-level temporal ordering; *attempt numbers* not fine).
- Avoid embedding things that a human cannot copy-paste (spaces, special chars).
- If you need pure uniqueness with zero semantics, `str(uuid.uuid4())` at the **client** is fine. Inside workflow code, use `workflow.uuid4()`.

### Workflow Type

- One per *kind* of orchestration. Don't dynamically generate; the worker has to register them statically.
- If you want per-pipe filterability without registering 200 workflow types, use a **search attribute** instead.

### Activity ID

- **Default to letting the SDK generate it** (omit the parameter). Sequential integers per workflow run, guaranteed unique, no thought required.
- Customize **only** when you want a specific log/metric anchor or when you'll cancel by id.
- If you do customize, derive from workflow-local state (counter or `workflow.uuid4()`), never from worker-singleton state.

### Activity Type

- One per *kind* of side effect. Stable, descriptive, registered on the worker (`act_llm_gen_text`, `act_extract_pages`).
- Don't embed parameters in the type; put parameters in the per-activity summary or in structured logs.

### Task Queue

- Stable, operational names. One per worker fleet / capacity class.
- Per-activity overrides for routing-by-capability (already in place in Pipelex).

### Summary / details / search attributes

- **Use them.** They are free observability. Pipelex currently uses zero of them.
- Decide for each piece of context: do operators *filter* on this (→ search attribute) or do they *read* this (→ summary / details)?

---

## 6. Mapping back to the Pipelex pain points

This section is descriptive, not prescriptive — it just lines up the primitives above with the issues catalogued in `workflow-and-activity-ids.md`. The *design* (which primitive to use for what) is for the next session.

| Pipelex symptom | Primitive(s) that can address it |
|---|---|
| `activity_id = "craft-text"` collides on second call | (a) Omit the param → SDK default integers. (b) Counter on `ContentGeneratorInWorkflow` *not* the worker singleton — per-execution counter passed through workflow state. (c) `workflow.uuid4()` per call. |
| `wfid` parameter conflates "child workflow id base" and "activity id" | Two different primitives; split the parameter at the protocol layer. The activity-side concern can be dropped entirely if Pipelex stops customizing activity_id (option (a) above). |
| Workflow IDs like `EdgdJ-HR5fd-TemporalPipeRun-pipe-router` are uninformative | Move semantic context to `static_summary` (display) and search attributes (filtering). The Workflow ID can stay opaque-and-unique. |
| Only `wf_pipe_router` / `wf_pipe_run` show up in the Workflow Type column | Either (a) register more workflow types (one per pipe family) or (b) keep the small set and surface pipe-code via `PipeCode` search attribute. Either works. |
| LRU + `is_replaying()` + `(workflow_id, run_id)` keying in `_seen_activity_ids` | All of this exists *only* because the disambiguator lives on a worker singleton. Move the disambiguator into workflow-local state → all this machinery becomes deletable. |
| Operators cannot trace a row in our own webapp back to a Temporal execution | Pass the Pipelex run id as Workflow ID (or store both via memo / search attribute). The current "5-char prefix of session + 5-char prefix of shortuuid + class name" loses information for no benefit. |

---

## 7. Open questions for the design session

These are the choices the next session has to make, with the primitives above as the menu:

1. **Workflow ID shape.** Pure UUID? `{pipe_code}-{session_short}-{uuid}`? Something else? Determinism is a constraint only for *child* workflow ids; top-level ids are set client-side and can use anything.
2. **Child workflow id derivation.** `{parent_workflow_id}-child-{counter}` vs `{parent_workflow_id}-{workflow.uuid4()}` vs `workflow.uuid4()` alone.
3. **Activity id policy.** Default integers (recommended) vs custom strings. If custom: where does the disambiguator live (workflow-local counter, `workflow.uuid4()`, both)?
4. **Workflow Type granularity.** One per pipe code (registered dynamically — adds complexity) vs the current handful plus search attributes.
5. **Summary / details strategy.** What goes in `static_summary` (operator skim), what goes in `static_details` (structured context), what goes in `current_details` (in-flight progress).
6. **Search attribute schema.** Which custom attributes do we register on the namespace? Minimum likely set: `PipeCode` (Keyword), `SessionId` (Keyword), `UserId` (Keyword), `RootPipelineId` (Keyword). Anything else?
7. **Memo contents.** Anything large or sensitive that we want round-tripped with the execution but not indexed (e.g. dispatch resolution debug pointer)?
8. **`wfid` parameter rename.** Once activity-id concerns are off this parameter, what does it represent? Probably "base for the workflow id" — name it accordingly (`workflow_id_base`? `caller_id`?).

The TDD gate in `tests/unit/pipelex/temporal/test_default_activity_id_collision_bug.py` must turn green as a side effect of whichever activity-id policy is picked.
