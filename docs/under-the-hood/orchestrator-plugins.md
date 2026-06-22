---
title: "Orchestrator Plugins"
description: "How Pipelex dispatches a pipe run by orchestration mode through the orchestrator seam, the Orchestrator SPI a host-runtime plugin compiles against, and how the in-tree Temporal plugin rides it."
---

# Orchestrator Plugins

A pipe a host runtime invokes through the runtime bridge runs along **two orthogonal axes**:

- **`orchestration_mode`** — *which* orchestrator runs the pipe. An **open string token**, not a closed enum: core owns only `"direct"` (in-process); every other token is contributed by the plugin that owns its orchestrator — `"temporal"` (durable, on a Temporal worker fleet) by `pipelex-temporal`, `"mistralai-workflows"` (decomposed into Mistral Workflows primitives) by `pipelex-mistralai-workflows`.
- **`delivery`** — *whether the caller waits*. A **closed** core `DeliveryMode` enum (`BLOCKING` / `FIRE_AND_FORGET`), set by the endpoint and passed as a parameter to `run`, never received from a caller. An orchestrator honors it per its nature; `supports_fire_and_forget` advertises whether it can do genuine async.

An **orchestrator** is what knows how to run a pipe under one token. Core names no orchestrator by import or by string. The bridge resolves the orchestrator for the requested token from a registry (keyed by the token `str`) and calls its `run` — `"direct"` is contributed by a core plugin, `"temporal"` by the Temporal plugin, `"mistralai-workflows"` by the external `pipelex-mistralai-workflows` plugin. A lookup miss raises a generic `MissingOrchestratorError` that names no orchestrator. This page documents that seam, the **Orchestrator SPI** a host-runtime plugin compiles against, and how the Temporal plugin is wired.

---

## The seam in one view

```
run_pipe_via_bridge(input_payload)            # pipelex/runtime_bridge/bridge.py
  → build the PipeJob (boundary decode + library scope + trace_context)
  → orchestrator = get_orchestrator_registry().get_optional(mode=orchestration_mode)
  → if orchestrator is None: raise MissingOrchestratorError(mode)   # generic, names no orchestrator
  → return await orchestrator.run(pipe_job=..., delivery_assignment=..., delivery=...)
```

The registry is built once at boot from whatever the discovered plugins contributed (`build_registrar` → `OrchestratorRegistry` on the hub). There is no `match orchestration_mode:` anywhere in the bridge — the token set is open, so validation is the registry lookup itself; adding a mode's behavior means registering an orchestrator for its token, nothing in core changes.

---

## The orchestrator contract

An orchestrator satisfies `OrchestratorProtocol` (`pipelex/plugins/orchestrator_registry.py`):

```python
class OrchestratorProtocol(Protocol):
    supports_fire_and_forget: bool

    async def run(self, *, pipe_job: PipeJob, delivery_assignment: DeliveryAssignment | None, delivery: DeliveryMode) -> PipelexPipeRunOutput: ...
```

`run` honors the endpoint-chosen `delivery` per the orchestrator's nature (in-process always blocks; a distributed orchestrator awaits completion for `BLOCKING` and returns a workflow id for `FIRE_AND_FORGET`). `supports_fire_and_forget` is the capability a runner reads *before* dispatch — `/start` rejects honestly (4xx) when the resolved mode cannot do genuine async, instead of silently running blocking and acking.

A plugin contributes one per token it serves by calling the registrar menu in its `register`, passing the token as a raw string (no enum, no cast):

```python
registrar.add_orchestrator(mode="temporal", orchestrator=TemporalOrchestrator())
```

Constructing the orchestrator instance must be **import-light** — it must not import the host-runtime SDK (`temporalio`, …) at module scope or in its `__init__`. The heavy import happens lazily inside `run` (and a friendly `MissingOrchestratorError` is raised there if the mode's extra is absent), so discovering and registering the plugin never pulls the SDK. This is what keeps boot import-light even on a process that will never use the mode.

### A missing orchestrator is a generic, plugin-decoupled error

A token with no registered orchestrator (its plugin is not installed) raises `MissingOrchestratorError(mode=...)` (`pipelex/runtime_bridge/exceptions.py`). The message names the token but **no orchestrator** — *"No orchestrator is registered for orchestration mode '{mode}'; is its plugin installed?"* — so core stays fully decoupled from its plugins (it never spells out `pipelex-temporal` / `pipelex-mistralai-workflows`). The one special case is the core `"direct"` token: its orchestrator is always present, so a miss there reports a boot/discovery fault. The message survives STRICT error disclosure.

---

## HTTP error mappers: rendering an orchestrator's transport faults

An orchestrator's *runtime* (a Temporal client, a Mistral workflow runner) raises SDK-specific transport faults — a server unreachable, a workflow timeout — that a host runtime serving HTTP must turn into a proper error response, not a catch-all 500. But core names no web framework and the SDK lives only in the plugin, so the host (`pipelex-api`) cannot itself know how to classify `temporalio.TemporalError`.

The plugin bridges that gap by contributing a **framework-agnostic mapper** — a function from one exception type to a structured `ErrorReport` (`pipelex/base_exceptions.py`):

```python
registrar.add_http_error_mapper(
    exc_type_provider=lambda: TemporalError,      # SDK imported only when a host resolves the mappers, never at register
    to_error_report=lambda exc: ErrorReport(...), # classified transient / RUNTIME
)
```

The exc type is supplied as a **provider thunk**, not the bare class, on purpose: naming `temporalio.TemporalError` requires importing `temporalio` (the whole SDK), so a bare `exc_type=` would force that import at `register` — breaking the import-light invariant for a plugin that hard-depends on a heavy SDK. The provider defers the import to read time (a host runtime's app construction), where the plugin — and therefore its SDK — is by definition installed.

The contract is deliberately split so no layer overreaches:

- **The plugin** owns *classification* — which exception, transient or not, which error domain. It stays import-light: `register` only records the provider + closure; the SDK import happens when the provider runs at read time (and the `to_error_report` closure when the mapper is first invoked), never at registration.
- **Core** owns *transport* — `registrar.get_http_error_mappers()` runs every provider, builds the `{exc_type: mapper}` dict, and is fail-loud on a duplicate *resolved* exception type (naming both plugins). `ErrorReport` is a core type, so the seam carries **no** web-framework import.
- **The host runtime** owns *presentation* — at app construction it iterates the resolved mappers and wraps each into one framework error handler (FastAPI, …) that runs the mapper, then renders the `ErrorReport` through its own RFC 7807 + `DisclosureMode` path. FastAPI / Starlette stays only in the host; core and the plugin import neither.

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
| Mode + delivery + errors | `pipelex.runtime_bridge.orchestration_mode` (`OrchestrationMode`, `DIRECT_ORCHESTRATION_MODE`), `pipelex.runtime_bridge.delivery_mode` (`DeliveryMode`), `pipelex.runtime_bridge.exceptions` (`MissingOrchestratorError`, `PipelexBridgeDispatchError`) |
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
