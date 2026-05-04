# TODO: Raw `working_memory` end-to-end through `act_deliver`

> Goal: make distributed Temporal correct AND remove the global-registry-propagation hack.

---

## Background — why this work exists

### What's currently in place

The Temporal pipe layer ships user-defined dynamic concept classes through workflow boundaries via two mechanisms:

1. **`LibraryCrate` riding on `PipeJob`.** The crate (qualified concept/pipe blueprints + source) is a Pydantic field on `PipeJob` (`pipelex/pipe_run/pipe_job.py:20`). It's serialized inside the workflow input. Whichever worker picks up `WfPipeRouter` re-loads the crate locally: opens a per-workflow `ClassRegistry`, sets a `_library_id` `ContextVar`, calls `library_manager.load_from_crate(...)`, which `exec`s the dynamic Python source and registers the resulting classes (`pipelex/temporal/tprl_pipe/wf_pipe_router.py:51-69`).

2. **Dehydrate-to-raw-dict at workflow boundaries.** `WorkingMemory.dump_for_temporal()` (`pipelex/core/memory/working_memory.py:472-495`) serializes the working memory tree to a plain dict, embedding `__class__` and `__module__` metadata on every `ListContent` item. `PipeJob.prepare_for_temporal()` and `PipeOutput.prepare_for_temporal()` use this so the wire form is registry-free. The receiving worker calls `hydrate_working_memory(raw)` (`pipelex/temporal/tprl_pipe/hydration.py`) to rebuild typed `Stuff`/`StuffContent` instances using `get_class_registry()`.

3. **Two patches in `hydration.py` worth knowing about:**
   - `_validate_as_known_class` round-trips through `model_dump()` to defeat cross-exec class-identity mismatches (kajson eagerly rebuilds instances from `__class__` metadata using one class identity, then `load_from_crate` re-execs the source and replaces the registry entry with a new identity — same name, different `id()` — and Pydantic's `model_validate` would otherwise reject the older instance).
   - `_hydrate_list_item` handles `Anything[]` lists by reading per-item `__class__` metadata, falling back to `TextContent`.

4. **`Optional[BaseModel]` payload converter fix** (`pipelex/temporal/temporal_data_converter.py:107-121, 133-135`): added so `PipeOutput.graph_spec: GraphSpec | None` deserializes via kajson instead of falling through to the default JSON path.

5. **Schema-to-model enum forward-refs fix** (`pipelex/cogt/content_generation/schema_to_model.py:120-122`): `model_rebuild` now uses *all* generated types (models + enums), so forward references to dynamically generated `Enum` classes resolve correctly.

6. **The propagation hack** (`pipelex/temporal/tprl_pipe/wf_pipe_router.py:71-80`): after loading the crate into the per-workflow registry, copies all dynamic classes into the worker process's *global* `KajsonManager` registry. The stated reason: child workflows and activities don't see the per-workflow `ContextVar`, so they need the global to be primed.

### The cogt layer uses a fundamentally different (better) pattern

`pipelex/temporal/tprl_content_generation/*` ships dynamic classes via JSON schema in the assignment (e.g. `ObjectAssignment.object_class_schema`). The receiving side calls `model_class_from_json_schema(...)` (`pipelex/cogt/content_generation/schema_to_model.py:24-49`) which `exec`s the generated source on the fly. The reconstructed class carries `__kajson_class_source__` as a class attribute. The Temporal payload converter (`pipelex/temporal/temporal_data_converter.py:60-79`) embeds that source in payload metadata as `kajson_class_source`. On the receiving worker, `kajson.loads(..., class_source_code=...)` exec's the source into a temporary `ClassRegistry` (`kajson/kajson.py:141-159`) merged with the explicit registry. Result: **payloads are self-describing; no registry coordination across workers.** This is independent of the LibraryCrate path and is not affected by this change.

### Why the propagation hack breaks in distributed Temporal

A worker is a process polling a task queue. In distributed deployments multiple workers poll the same queue and any of them can pick up a child workflow or activity. ContextVars don't cross processes. So:

| Hop | Crosses worker? | Receiver has dynamic classes? |
| --- | --- | --- |
| User submitter → `WfPipeRouter` (top-level) | yes | yes — `WfPipeRouter` re-loads the crate from `PipeJob.library_crate` on its own worker |
| `WfPipeRun` parent → child `WfPipeRouter` | possibly different worker | yes — child gets the same `PipeJob` carrying the crate, re-loads on its worker |
| Child `WfPipeRouter` → `WfPipeRun` parent (rehydrate at `wf_pipe_run.py:50-52`) | possibly different worker | **NO — this is the bug.** `WfPipeRun` never opens its own per-workflow library. `hydrate_working_memory` falls back to the parent's global registry, which only has classes if the propagation hack ran on the *same* worker that the parent happens to be on. |
| `WfPipeRun` → `act_deliver` activity | possibly different worker | **NO.** The activity receives a typed `pipe_output` (because parent rehydrated). The activity worker's global registry doesn't have the crate. |
| `WfPipeRouter` → `act_flush_trace_events` | possibly different worker | safe — only ships `TraceEvent` (built-in) |
| `WfPipeRun` → `act_assemble_graph` | possibly different worker | safe — only ships scalar IDs |
| All cogt boundaries | possibly different worker | safe — `__kajson_class_source__` mechanism |

So the entire problem reduces to **two lines**: the parent-side rehydrate at `wf_pipe_run.py:50-52`. Remove it and `act_deliver` naturally receives the raw dict; the propagation hack has no remaining customer and gets deleted.

### Drawbacks of "raw end-to-end" (already discussed and accepted)

- **D1 — typed rendering for dynamic concepts is lost.** Built-in `StuffContent` subclasses (`ImageContent`, `PdfContent`, `MermaidContent`, `HtmlContent`, `TextContent`, `NumberContent`) are statically registered on every worker, so they can be rehydrated locally from `__class__` metadata. User-defined dynamic concepts fall back to a generic field-walking render (JSON-in-markdown / `<pre>`-in-HTML). User: **accepted**.
- **D2 — dual rendering path in `DeliveryExecutor`** (typed when `working_memory` is set, raw-dict when `working_memory_raw` is set). Mirrors the existing `working_memory` / `working_memory_raw` dual field on `PipeJob` and `PipeOutput`. User: **accepted (already a known pattern)**.
- **D3 — fix is delivery-scoped.** Other consumers of typed dynamic classes still need the crate. We confirmed (Explore agent enumeration) that no other consumers exist on the Temporal hot path; the cogt layer is independent. User: **OK, focus on delivery; flag others if any (none found)**.
- **D4 — `model_dump` subtleties.** `dump_for_temporal()` and `smart_dump()` already use `serialize_as_any=True`, so subclass-specific fields and computed fields are preserved. User: **noted**.
- **D5 — debuggability loss** (raw dict instead of typed `__repr__` inside the activity). User: **accepted**.

---

## Plan

### 1. Stop the parent rehydrate — `pipelex/temporal/tprl_pipe/wf_pipe_run.py`

- Remove lines 49-52 (the `if pipe_output.working_memory_raw is not None: pipe_output.working_memory = hydrate_working_memory(...)`).
- Forward `pipe_output` to `act_deliver` with `working_memory_raw` populated and `working_memory=None`.
- Remove the now-unused `hydrate_working_memory` import.

### 2. Delete the global-registry-propagation block — `pipelex/temporal/tprl_pipe/wf_pipe_router.py`

- Delete lines 71-80 (`# 4. Propagate dynamic classes to global registry...`).
- Renumber the trailing comment "5. Hydrate WorkingMemory" → "4." for consistency.
- The internal `hydrate_working_memory(workflow_arg.working_memory_raw)` at line 84 still works because the `_library_id` `ContextVar` is set just above (line 66) and `get_class_registry()` (`pipelex/hub.py:397-408`) routes to the per-workflow registry.

### 3. Make `DeliveryExecutor` accept either typed or raw `WorkingMemory` — `pipelex/pipe_run/delivery_executor.py`

`pipe_output.working_memory` may now be `None` while `pipe_output.working_memory_raw` is populated. `DeliveryExecutor.execute` and the helpers (`generate_result_files`, `_generate_main_stuff_files`, `_store_results`) need to branch on which field is populated.

Rendering policy per file:

| File | Typed path (today) | Raw-dict path (new) |
| --- | --- | --- |
| `working_memory.json` | `working_memory.smart_dump()` | `clean_json_dumps(working_memory_raw)` directly — already a dict produced by `dump_for_temporal()` |
| `main_stuff.json` | `main_stuff.content.rendered_json_async()` | extract main stuff dict from raw root by alias name; `clean_json_dumps` it |
| `main_stuff.md` / `.html` / `viewer.html` | `rendered_markdown_async()` / `rendered_html_async()` / `render_stuff_viewer()` | locally rehydrate the *single* main stuff using `__class__` lookup in the **global** registry (built-ins always present); on success, call existing typed renderers. On lookup miss (dynamic concept class not registered locally), fall back to a generic field-walking render that just dumps the dict as pretty JSON-in-markdown / `<pre>`-in-HTML. |
| `graphspec.json` / `mermaidflow.*` / `reactflow.html` | unchanged — `graph_spec` is independent of working_memory | unchanged |

Implementation note: introduce a small private helper `_local_hydrate_main_stuff(raw_root: dict, main_stuff_name: str) -> Stuff | None` that tries `Stuff.model_validate` against the registry's `__class__`-named class for the content, returning `None` if the class isn't locally available. Isolates the fallback decision in one place.

### 4. Verify-only (no change)

- `pipelex/temporal/tprl_pipe/wf_pipe_router.py:202-204` — `prepare_for_temporal()` on return when `library_crate is not None`. Keep — still correct for the WfPipeRouter→WfPipeRun edge.
- `pipelex/temporal/tprl_pipe/temporal_pipe_router.py:84-86` — top-level caller rehydrate. Keep — runs in the submitter's process which already has the classes loaded.

### 5. Tests

The repo has a Temporal-distributed validation harness — invoke the `temporal-e2e-validate` skill (true 3-process setup: server + worker + submitter, validates cross-process topology).

**Deterministic repro is now wired in.** Recent (staged) work added:

- **Worker scope split** (`pipelex/pipelex.toml:528-560`, `pipelex/temporal/config_temporal.py:59-91`, `pipelex/temporal/worker_cli.py`): named scopes `router` (`disable_all_activities=true`) and `runner` (`disable_all_workflows=true`) selectable via `--scope`. Two scoped workers on the same `temporal_task_queue` force every activity to be picked up by a different Python process than the workflow that scheduled it, making cross-process registry hops deterministic instead of probabilistic.
- **Repro script** `.claude/skills/temporal-e2e-validate/scripts/repro_runner_registry_bug.py`: mirrors the cloud / `start_pipeline` + webhook submission path by attaching a `DeliveryAssignment(storage=StorageTarget())`. This makes `wf_pipe_run.py:79-96` schedule `act_deliver` on the runner with hydrated `pipe_output`. Plain `pipelex run bundle` does **not** trigger this — without a `delivery_assignment`, `act_deliver` is skipped and the runner only ever sees trace/graph activity payloads (no dynamic-class decoding).
- **In-process scope test** `tests/integration/pipelex/temporal/library_crate/test_distributed_scopes.py`: validates the scope mechanism resolves correctly (cannot reproduce the cross-process bug because both workers share the same `KajsonManager`; documented in the test's module docstring).

Currently observable failure (with the parent rehydrate at `wf_pipe_run.py:50-52` still in place) when running the repro script against router+runner:

```
KajsonDecoderError: Class '<bundle>__<DynamicConcept>' not found
  in module 'builtins' or global registry
ApplicationError: Failed decoding arguments
  → temporalio/worker/_activity.py:566 (data_converter.decode_wrapper)
```

surfaced in the **runner** tmux session, raised by the activity worker before the `act_deliver` body runs. After the fix in steps 1–3, this should resolve to a successful `act_deliver` execution where the activity receives `working_memory_raw` (no class lookup needed).

Add/extend:

- Promote the repro script into a pytest case (or call it from one) that drives the deterministic 2-scope failure path and asserts success post-fix.
- Verify `main_stuff.md` for a dynamic concept passes via the generic fallback path.
- Regression test that distributed delivery does not import the dynamic concept module on the activity worker (e.g. run the activity worker process with a stripped library set, confirm no `ClassRegistry` lookup errors).
- Existing crate isolation tests (`temporal-test-crate` skill) should continue to pass — and now be more strongly isolated since the propagation no longer pollutes the global.

---

## Files to modify

- `pipelex/temporal/tprl_pipe/wf_pipe_run.py` — drop parent rehydrate (lines 49-52), drop unused import.
- `pipelex/temporal/tprl_pipe/wf_pipe_router.py` — delete propagation block (lines 71-80), tidy step comment.
- `pipelex/pipe_run/delivery_executor.py` — dual-mode rendering; new `_local_hydrate_main_stuff` helper.
- (tests) — extend the temporal-e2e harness; add a dynamic-concept delivery test.

## Files to leave alone

- `pipelex/temporal/temporal_data_converter.py` — `Optional[BaseModel]` and `BaseModel | list[BaseModel]` paths remain correct.
- `pipelex/temporal/tprl_pipe/hydration.py` — still used by `WfPipeRouter` internally (per-workflow scope) and by `temporal_pipe_router.py` at the submitter side. Both contexts have the registry primed.
- `pipelex/core/memory/working_memory.py` — `dump_for_temporal()` already preserves `__class__` metadata on `ListContent` items, which the local-hydrate fallback uses.
- `pipelex/temporal/tprl_content_generation/*` — independent system (`__kajson_class_source__`).

---

## Verification checklist

1. `make agent-check` from `pipelex/` — type checks + linting clean.
2. `make agent-test` from `pipelex/` — full unit/integration suite green.
3. Deterministic distributed repro via `temporal-e2e-validate` Tier 2b (router + runner scoped workers + `repro_runner_registry_bug.py`) — runs end-to-end with a hydrated `pipe_output` reaching `act_deliver` on the runner, no `KajsonDecoderError`, no class lookup on the runner side. Activity worker never loads the crate.
4. `temporal-test-crate` skill — concurrent workflows with conflicting concept names still produce correct outputs.
5. Single-worker smoke: local `pipelex run` against a pipe using a dynamic concept; delivery files byte-equivalent for built-in content types and structurally-equivalent (JSON/MD/HTML) for dynamic concepts.
