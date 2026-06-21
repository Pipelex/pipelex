---
title: "Orchestrator Plugins"
description: "How Pipelex dispatches a pipe run by execution mode through the orchestrator seam, the Orchestrator SPI a host-runtime plugin compiles against, and how the in-tree Temporal plugin rides it."
---

# Orchestrator Plugins

Every pipe a host runtime invokes through the runtime bridge runs under an **execution mode** — `DIRECT` (in-process), `TEMPORAL_BLOCKING` / `TEMPORAL_FIRE_AND_FORGET` (durable, on a Temporal worker fleet), or `MISTRAL_NATIVE` (decomposed into Mistral Workflows primitives). An **orchestrator** is what knows how to run a pipe under one mode. Which orchestrator handles a given run is decided entirely by the mode on the request.

Core names no orchestrator by import or by string. The bridge resolves the orchestrator for the requested mode from a registry and calls its `run` — DIRECT is contributed by a core plugin, the `TEMPORAL_*` modes by the in-tree Temporal plugin, `MISTRAL_NATIVE` by the external `pipelex-mistralai-workflows` plugin. This page documents that seam, the **Orchestrator SPI** a host-runtime plugin compiles against, and how the Temporal plugin is wired.

---

## The seam in one view

```
run_pipe_via_bridge(input_payload)            # pipelex/runtime_bridge/bridge.py
  → build the PipeJob (boundary decode + library scope + trace_context)
  → orchestrator = get_orchestrator_registry().get_optional(mode=execution_mode)
  → if orchestrator is None: raise MissingOrchestratorError(mode)   # per-mode install hint
  → return await orchestrator.run(pipe_job=..., delivery_assignment=...)
```

The registry is built once at boot from whatever the discovered plugins contributed (`build_registrar` → `OrchestratorRegistry` on the hub). There is no `match execution_mode:` anywhere in the bridge — adding a mode's behavior means registering an orchestrator for it, nothing in core changes.

---

## The orchestrator contract

An orchestrator satisfies `OrchestratorProtocol` (`pipelex/plugins/orchestrator_registry.py`):

```python
class OrchestratorProtocol(Protocol):
    async def run(self, *, pipe_job: PipeJob, delivery_assignment: DeliveryAssignment | None) -> PipelexPipeRunOutput: ...
```

A plugin contributes one per mode it serves by calling the registrar menu in its `register`:

```python
registrar.add_orchestrator(mode=PipelexExecutionMode.TEMPORAL_BLOCKING, orchestrator=TemporalBlockingOrchestrator())
```

Constructing the orchestrator instance must be **import-light** — it must not import the host-runtime SDK (`temporalio`, …) at module scope or in its `__init__`. The heavy import happens lazily inside `run` (and a friendly `MissingOrchestratorError` is raised there if the mode's extra is absent), so discovering and registering the plugin never pulls the SDK. This is what keeps boot import-light even on a process that will never use the mode.

### Per-mode errors

A mode with no registered orchestrator (its plugin is not installed), or an in-tree orchestrator whose extra is absent, raises `MissingOrchestratorError(mode=...)` (`pipelex/runtime_bridge/exceptions.py`). The message is derived from the mode, so each carries its exact, actionable install hint (`pip install 'pipelex-temporal'` vs `pip install pipelex-mistralai-workflows`). The hint survives STRICT error disclosure.

---

## HTTP error mappers: rendering an orchestrator's transport faults

An orchestrator's *runtime* (a Temporal client, a Mistral workflow runner) raises SDK-specific transport faults — a server unreachable, a workflow timeout — that a host runtime serving HTTP must turn into a proper error response, not a catch-all 500. But core names no web framework and the SDK lives only in the plugin, so the host (`pipelex-api`) cannot itself know how to classify `temporalio.TemporalError`.

The plugin bridges that gap by contributing a **framework-agnostic mapper** — a function from one exception type to a structured `ErrorReport` (`pipelex/base_exceptions.py`):

```python
registrar.add_http_error_mapper(
    exc_type=TemporalError,                       # imported lazily inside the closure, never at register
    to_error_report=lambda exc: ErrorReport(...), # classified transient / RUNTIME
)
```

The contract is deliberately split so no layer overreaches:

- **The plugin** owns *classification* — which exception, transient or not, which error domain. It stays import-light: `register` only records the closure; the SDK import happens lazily when the mapper is first invoked.
- **Core** owns *transport* — it collects the mappers keyed by `exc_type` (fail-loud on a duplicate exception type, naming both plugins) and exposes them via `registrar.get_http_error_mappers()`. `ErrorReport` is a core type, so the seam carries **no** web-framework import.
- **The host runtime** owns *presentation* — at app construction it iterates the collected mappers and wraps each into one framework error handler (FastAPI, …) that runs the mapper, then renders the `ErrorReport` through its own RFC 7807 + `DisclosureMode` path. FastAPI / Starlette stays only in the host; core and the plugin import neither.

This is what lets the public `pipelex-api` base be orchestrator-agnostic and still render a Temporal (or Mistral) transport fault correctly: install the flavor's plugin and its mapper rides in; install none and there is simply nothing to wrap. The capability is optional, so it grew the plugin contract by one method → `PLUGIN_API_VERSION` is now **2**.

---

## Boot-orchestrator plugins: claiming the runtime

Some orchestrators don't just serve a per-call mode — they reconfigure the whole process to run *as* that runtime (a Temporal worker). Such a plugin **claims process-global hub slots**, but only when the core-owned boot gate names it. `plugins.boot_orchestrator == self.name` means "boot this process as a Temporal-default runtime", not "the Temporal plugin is on". The gate is a backend-agnostic name-match — core names no orchestrator, and `register` reads no config file (the rich orchestrator config self-loads inside the thunks):

```python
if registrar.config.plugins.boot_orchestrator == self.name:
    registrar.claim_content_generator(_make_temporal_content_generator)   # a thunk, not an instance
    registrar.claim_task_manager(_setup_temporal_task_manager)
    registrar.claim_pipe_router(_make_temporal_pipe_router)
    registrar.claim_pipe_run(_make_temporal_pipe_run)
    registrar.add_teardown(_teardown_temporal)
```

Each `claim_*` takes a **thunk** (a zero-arg factory), never a constructed instance. The thunk runs only at the boot apply-point, so `register` itself imports no `temporalio` — even on a worker. This is the deferred-thunk rule that keeps the import-light invariant intact at boot.

### Injection precedence

At each ordered hub slot, `Pipelex.setup` resolves in this precedence:

1. an explicit `setup()` parameter (test/host injection) — always wins;
2. a plugin slot-claim thunk;
3. the core default.

A slot claim must never silently override an explicit injection. Teardown runs the plugin-registered teardown callbacks **LIFO**, before core teardown, so a worker's in-flight runtime resources release first.

---

## Operational commands ship as console scripts

The plugin seam does **not** contribute commands to the host `pipelex` CLI. An operational command — a worker daemon, a one-time namespace bootstrap — is a daemon/utility, not a way a pipe *runs*, so a plugin that needs one ships its own `[project.scripts]` console script, which pip materializes into a standalone executable. Nothing is harvested onto `pipelex` at import time, so a broken or colliding plugin can never brick `pipelex --help` / `doctor` / `init`.

The in-tree Temporal plugin follows this rule: its `worker` and `setup-namespace` commands ship as the `pipelex-temporal` console script (`pipelex-temporal worker`, `pipelex-temporal setup-namespace`), declared in `pyproject.toml`:

```toml
[project.scripts]
pipelex-temporal = "pipelex_temporal.temporal_cli:app"
```

When Temporal externalizes to its own `pipelex-temporal` distribution (Phase 5), that dist owns this console script natively — nothing in core to move.

---

## The Orchestrator SPI

What an out-of-tree orchestrator imports *is* a contract. The SPI is a documented, versioned set of modules and symbols (gated by `PLUGIN_API_VERSION` in `pipelex/plugins/contract.py`) — not an `__init__.py` re-export shim. It is sized to what a real orchestrator (`pipelex-mistralai-workflows`) actually imports, not guessed. Anything an orchestrator needs that is *outside* this surface is a design bug — promote it into the SPI or remove the need.

| Area | Modules / symbols |
|---|---|
| Bridge entry + boundary | `pipelex.runtime_bridge.bridge` (`run_pipe_via_bridge`, `build_pipe_job_from_input`, `serialize_pipe_output`), `pipelex.runtime_bridge.serialization` (`serialize_completed_output`, `PIPE_DISPATCH_ERRORS`), `pipelex.runtime_bridge.payloads` (`PipelexPipeRunInput`, `PipelexPipeRunOutput`), `pipelex.runtime_bridge.bootstrap` (`ensure_pipelex_booted`) |
| Mode + errors | `pipelex.runtime_bridge.execution_mode` (`PipelexExecutionMode`), `pipelex.runtime_bridge.exceptions` (`MissingOrchestratorError`, `PipelexBridgeDispatchError`) |
| Host-runtime primitives | `pipelex.runtime_bridge.primitives.*` (`delivery`, `hydration`, `pipe_classification`, `submitter_hydration`, `trace_flush`) |
| Plugin contract | `pipelex.plugins.contract` (`PipelexPlugin`, `PLUGIN_API_VERSION`), `pipelex.plugins.registrar` (`PluginRegistrar` menu: `add_orchestrator`, `add_http_error_mapper`, `claim_*`, `add_teardown`; read accessor: `get_http_error_mappers`), `pipelex.plugins.orchestrator_registry` (`OrchestratorProtocol`) |
| Execution protocols | `PipeRouterProtocol`, `PipeRunProtocol`, `ContentGeneratorProtocol`, the task-manager protocol |
| Payload / core types | `PipeJob`, `PipeOutput`, `DeliveryAssignment`, `WorkingMemory` (+ factory), `JobMetadata`, `LibraryCrate` |
| Library + hub scoping | `set_current_library` / `get_current_library`, `scoped_pipe_router`, `get_class_registry` (per-call library hydration via `library_crate_dump`) |
| Tracing / graph hooks | `trace_events`, `graph_tracer_manager`, `tracing_assembly` (per-step trace/usage events across the boundary) |

---

## Worked example: the in-tree Temporal plugin

`pipelex_temporal/temporal_plugin.py` (in the externalized `pipelex-temporal` distribution) is the reference orchestrator plugin. Its `register`:

- **always** (regardless of the boot gate): contributes `TemporalBlockingOrchestrator` / `TemporalFireAndForgetOrchestrator` (import-light; `temporalio` is pulled lazily inside `run`);
- **only when `plugins.boot_orchestrator == "temporal"`**: claims the content-generator / task-manager / pipe-router / pipe-run hub slots with thunks and registers the teardown callback — booting this process as a Temporal-default runtime.

The orchestrators themselves (`pipelex_temporal/temporal_orchestrators.py`) are extracted verbatim from the bridge's former `_run_temporal_*` arms, keeping the `WorkflowExecutionError` catch and the `make_workflow_id` recompute. They serialize their `PipeOutput` through `pipelex.runtime_bridge.serialization`, shared with the core DIRECT orchestrator so the boundary shape cannot drift.

The Temporal plugin is in-tree today and discovered through `BUILTIN_PLUGINS` (a hardcoded list in `pipelex/plugins/builtins.py`) — pipelex declares **no** `[project.entry-points."pipelex.plugins"]` on itself. Externalizing it into a `pipelex-temporal` distribution (Phase 5) is therefore not "the same entry point from a new dist": it means *removing* the plugin from `BUILTIN_PLUGINS` and *adding* a `pipelex.plugins` entry point in the new dist's `pyproject.toml`. Its operational `worker` / `setup-namespace` commands already ship as the standalone `pipelex-temporal` console script, so they travel with that dist unchanged.

---

## Authoring an out-of-tree orchestrator plugin

A third-party host-runtime plugin is a distribution that:

1. defines a plugin class (`name`, `targets_api`, `register`) whose `register` calls `add_orchestrator(mode=..., orchestrator=...)` for the mode(s) it serves — import-light;
2. compiles its orchestrator against the Orchestrator SPI above (and nothing outside it);
3. advertises itself under the `pipelex.plugins` entry-point group:

```toml
[project.entry-points."pipelex.plugins"]
my_runtime = "my_package.my_plugin:MyRuntimePlugin"
```

Installing the distribution makes the mode available; uninstalling removes it. No core change, no central registration list. A discovered plugin can be quarantined without uninstalling via the `plugins.disabled` denylist (see [Inference Backend Plugins](inference-backend-plugins.md) for the shared discovery/denylist machinery).
