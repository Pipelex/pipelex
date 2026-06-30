---
title: "Orchestrator Plugins"
description: "How Pipelex dispatches a pipe run by orchestration mode through the orchestrator seam, the Orchestrator SPI a host-runtime plugin compiles against, and how the external pipelex-temporal plugin rides it."
---

# Orchestrator Plugins

A pipe a host runtime invokes through the runtime bridge runs along **two orthogonal axes**:

- **`orchestration_mode`** — *which* orchestrator runs the pipe. An **open string token**, not a closed enum: core owns only `"direct"` (in-process); every other token is contributed by the plugin that owns its orchestrator — [`"temporal"`](https://pipelex.com/products#temporal) (durable, on a Temporal worker fleet) by `pipelex-temporal`, [`"mistral-workflows"`](https://pipelex.com/products#mistral-workflows) (decomposed into Mistral Workflows primitives) by `pipelex-mistralai-workflows`. Neither is built into the open-source `pipelex` core: both ship as external, closed-source host-runtime backends, distributed privately rather than on PyPI as part of Pipelex's [workflow-orchestration offer](https://pipelex.com/products#durable-execution).
- **`delivery`** — *whether the caller waits*. A **closed** core `DeliveryMode` enum (`BLOCKING` / `FIRE_AND_FORGET`), set by the endpoint and passed as a parameter to `run`, never received from a caller. An orchestrator honors it per its nature; `supports_fire_and_forget` advertises whether it can do genuine async.

An **orchestrator** is what knows how to run a pipe under one token. Core names no orchestrator by import or by string. The bridge resolves the orchestrator for the requested token from a registry (keyed by the token `str`) and calls its `run` — `"direct"` is contributed by a core plugin, `"temporal"` by the Temporal plugin, `"mistral-workflows"` by the external `pipelex-mistralai-workflows` plugin. A lookup miss raises a generic `MissingOrchestratorError` that names no orchestrator. This page documents that seam, the **Orchestrator SPI** a host-runtime plugin compiles against, and how the Temporal plugin is wired.

---

## The seam in one view

```
<host-side bridge entry>(input_payload)       # closed pipelex-transport library
  → build the PipeJob (boundary decode + library scope + trace_context)
  → orchestrator = get_orchestrator_registry().get_optional(mode=orchestration_mode)
  → if orchestrator is None: raise MissingOrchestratorError(mode)   # generic, names no orchestrator
  → return await orchestrator.run(pipe_job=..., delivery_assignment=..., delivery=...)
```

The registry is built once at boot from whatever the discovered plugins contributed (`build_registrar` → `OrchestratorRegistry` on the hub). There is no `match orchestration_mode:` anywhere in the bridge — the token set is open, so validation is the registry lookup itself; adding a mode's behavior means registering an orchestrator for its token, nothing in core changes.

!!! note "Open seam, closed host-side entry"
    The host-side entry — the bridge entry point and `PipeJob` builder, plus the dispatch primitives that decode the boundary payload, scope the per-call library, and deliver results — lives in the **closed `pipelex-transport` library**. Embedding Pipelex into a host runtime (Temporal, Mistral, Airflow, your own) is a Pipelex [commercial capability](https://pipelex.com/products#durable-execution), not an open extension point. What stays **open** is the seam a third-party orchestrator extends: the orchestrator registry, `OrchestratorProtocol`, and the `pipelex.runtime_bridge` modules listed in [The Orchestrator SPI](#the-orchestrator-spi) below.

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

Not every orchestrator goes this far. A per-call-only plugin — `pipelex-mistralai-workflows` is the minimal example — contributes just its `"mistral-workflows"` orchestrator and claims **no** hub slots: its router is installed per workflow invocation by the workflow body itself, so there is no process-global boot slot to claim and it never participates in the boot gate below. The boot-orchestrator machinery in this section applies only to a plugin that boots the process as its runtime (today, `pipelex-temporal`).

```python
if registrar.config.plugins.boot_orchestrator == self.name:
    registrar.claim_content_generator(_make_temporal_content_generator)   # a thunk, not an instance
    registrar.claim_task_manager(_setup_temporal_task_manager)
    registrar.claim_pipe_router(_make_temporal_pipe_router)
    registrar.claim_pipe_run(_make_temporal_pipe_run)
    registrar.add_teardown(_teardown_temporal)
```

Each `claim_*` takes a **thunk** (a zero-arg factory), never a constructed instance. The thunk runs only at the boot apply-point, so `register` itself imports no `temporalio` — even on a worker. This is the deferred-thunk rule that keeps the import-light invariant intact at boot.

Because the gate is a name-match, `plugins.boot_orchestrator` must name a plugin that actually registered. After discovery, `Pipelex.setup` rejects a `boot_orchestrator` that no registered plugin carries — a typo or a missing plugin (e.g. `--orchestrator temporal` without `pipelex-temporal` installed) raises `UnknownBootOrchestratorError` instead of silently running in-process: nothing would claim the hub slots, so the process would otherwise fall through to the core defaults and execute on the wrong runtime. The check matches against **plugin names** (the same namespace the gate uses), not the `orchestration_mode` registry — a plugin's name and the token(s) it serves are separate namespaces that *may* differ, even where a shipped plugin keeps them identical (`pipelex-temporal` is named `temporal` and serves `temporal`). The error names no specific plugin, keeping core decoupled.

### Injection precedence

At each ordered hub slot, `Pipelex.setup` resolves in this precedence:

1. an explicit `setup()` parameter (test/host injection) — always wins;
2. a plugin slot-claim thunk;
3. the core default.

A slot claim must never silently override an explicit injection. Teardown runs the plugin-registered teardown callbacks **LIFO**, before core teardown, so a worker's in-flight runtime resources release first.

---

## Operational commands ship as console scripts

The plugin seam does **not** contribute commands to the host `pipelex` CLI. An operational command — a worker daemon, a one-time namespace bootstrap — is a daemon/utility, not a way a pipe *runs*, so a plugin that needs one ships its own `[project.scripts]` console script, which pip materializes into a standalone executable. Nothing is harvested onto `pipelex` at import time, so a broken or colliding plugin can never brick `pipelex --help` / `doctor` / `init`.

The `pipelex-temporal` plugin follows this rule: its `worker` and `setup-namespace` commands ship as the `pipelex-temporal` console script (`pipelex-temporal worker`, `pipelex-temporal setup-namespace`), declared in the plugin distribution's `pyproject.toml`:

```toml
[project.scripts]
pipelex-temporal = "pipelex_temporal.temporal_cli:app"
```

Because the script is declared by the `pipelex-temporal` distribution itself, it travels with that dist — nothing in core to harvest or move.

---

## The Orchestrator SPI

What an out-of-tree orchestrator imports *is* a contract. The SPI is a documented, versioned set of modules and symbols (gated by `PLUGIN_API_VERSION` in `pipelex/plugins/contract.py`) — not an `__init__.py` re-export shim. It is sized to what a real orchestrator (`pipelex-mistralai-workflows`) actually imports, not guessed. Anything an orchestrator needs that is *outside* this surface is a design bug — promote it into the SPI or remove the need.

| Area | Modules / symbols |
|---|---|
| Boundary serialization + boot | `pipelex.runtime_bridge.serialization` (`serialize_pipe_output`, `serialize_completed_output`, `PIPE_DISPATCH_ERRORS`), `pipelex.runtime_bridge.payloads` (`PipelexPipeRunInput`, `PipelexPipeRunOutput`), `pipelex.runtime_bridge.bootstrap` (`ensure_pipelex_booted`) |
| Mode + delivery + errors | `pipelex.runtime_bridge.orchestration_mode` (`OrchestrationMode`, `DIRECT_ORCHESTRATION_MODE`), `pipelex.runtime_bridge.delivery_mode` (`DeliveryMode`), `pipelex.runtime_bridge.exceptions` (`MissingOrchestratorError`, `PipelexBridgeDispatchError`) |
| Working-memory hydration | `pipelex.runtime_bridge.primitives.hydration` (re-hydrate `working_memory_raw` → typed `WorkingMemory`; stayed open because it is host-agnostic — used by core delivery and the open `pipelex-api` runner, and re-used across the boundary by `pipelex-transport`) |
| Plugin contract | `pipelex.plugins.contract` (`PipelexPlugin`, `PLUGIN_API_VERSION`), `pipelex.plugins.registrar` (`PluginRegistrar` menu: `add_orchestrator`, `add_http_error_mapper`, `claim_*`, `add_teardown`; read accessor: `get_http_error_mappers`), `pipelex.plugins.orchestrator_registry` (`OrchestratorProtocol`) |
| Execution protocols | `PipeRouterProtocol`, `PipeRunProtocol`, `ContentGeneratorProtocol`, the task-manager protocol |
| Payload / core types | `PipeJob`, `PipeOutput`, `DeliveryAssignment`, `WorkingMemory` (+ factory, `dump_for_transport`), `JobMetadata`, `LibraryCrate` |
| Library + hub scoping | `set_current_library` / `get_current_library`, `scoped_pipe_router`, `get_class_registry` (per-call library hydration via `library_crate_dump`) |
| Tracing / graph hooks | `trace_events`, `graph_tracer_manager`, `tracing_assembly` (per-step trace/usage events across the boundary) |

!!! warning "Not in the open SPI — the closed `pipelex-transport` layer"
    The host-side bridge entry point, the cross-process dispatch primitives (boundary delivery, pipe classification, submitter-side hydration, trace flush, scoped-library, and the submit-arg envelope), and the transport-prep helpers were extracted out of open core into the **closed `pipelex-transport` library**. Embedding Pipelex into a host runtime is a Pipelex commercial capability — Pipelex's own host-runtime plugins (`pipelex-temporal`, `pipelex-mistralai-workflows`) compile against `pipelex-transport`; a third-party out-of-tree orchestrator compiles against the **open** rows above only.

---

## Worked example: the `pipelex-temporal` plugin

`pipelex_temporal/temporal_plugin.py` (in the external `pipelex-temporal` distribution) is the reference orchestrator plugin. Its `register`:

- **always** (regardless of the boot gate): contributes a single `TemporalOrchestrator` registered once under the `"temporal"` token (import-light; `temporalio` is pulled lazily inside `run`). It advertises `supports_fire_and_forget = True`, and its `run` branches on the endpoint-chosen `delivery`: `BLOCKING` awaits completion and reports `make_workflow_id(...)`; `FIRE_AND_FORGET` calls `.start(...)` and returns an `is_completed=False` output carrying the workflow id;
- **only when `plugins.boot_orchestrator == "temporal"`**: claims the content-generator / task-manager / pipe-router / pipe-run hub slots with thunks and registers the teardown callback — booting this process as a Temporal-default runtime.

The orchestrator itself (`pipelex_temporal/temporal_orchestrators.py`) carries both delivery bodies behind one exhaustive `match delivery`, keeping the `WorkflowExecutionError` catch and the `make_workflow_id` recompute in the blocking arm. It serializes its `PipeOutput` through `pipelex.runtime_bridge.serialization`, shared with the core DIRECT orchestrator so the boundary shape cannot drift.

The Temporal plugin is **external** — it ships as the `pipelex-temporal` distribution and is discovered through a `pipelex.plugins` entry point in that dist's `pyproject.toml`, not through `BUILTIN_PLUGINS`. Core's `BUILTIN_PLUGINS` (`pipelex/plugins/builtins.py`) holds only the always-shipped inference and `direct` plugins and explicitly excludes Temporal; installing `pipelex-temporal` is all it takes to make the `"temporal"` orchestrator available — zero config, no core import of `temporalio`. Its operational `worker` / `setup-namespace` commands ship as the standalone `pipelex-temporal` console script, so they travel with that dist.

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
