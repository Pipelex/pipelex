# Orchestrators as Pipelex plugins

**Status:** assessment / design notes (not started)
**Scope:** turn the *orchestrators* — the strategies that decide **where and how** a pipe runs (in-process, on a Temporal worker fleet, on Mistral Workflows) — into discoverable plugins, so core ships only the in-process orchestrator and every distributed one is an optional, separately-installable plugin wired through one seam.

> An **orchestrator** decides how a whole pipe job is scheduled and where it executes — distinct from a *pipe controller*, which sequences sub-pipes *within* a single run. (We deliberately avoid "backend" here: that word already names the inference SDK adapters in the [driver doc](inference-backends-as-plugins.md).) This is the **strategy** half of the plugin story: orchestrators *replace core orchestration behavior*. The **driver** half — inference SDK wrappers selected by a model's `sdk` handle — is in [`inference-backends-as-plugins.md`](inference-backends-as-plugins.md). Temporal's concrete seam-by-seam extraction lives in [`temporal-as-plugin.md`](temporal-as-plugin.md), which references this doc for the shared mechanism. Cross-cutting best practices are in [`README.md`](README.md).

## The category

An orchestrator answers *"where/how does this pipe run?"* — not *"which model/SDK?"* (that's a driver). Pipelex already models the choice as `PipelexExecutionMode` in `runtime_bridge/execution_mode.py`:

- **`DIRECT`** — in-process async. The trivial orchestrator. **Ships in core.**
- **`TEMPORAL_BLOCKING` / `TEMPORAL_FIRE_AND_FORGET`** — distributed via Temporal. Lives in `pipelex/temporal/` today; destined for `pipelex-temporal`.
- **`MISTRAL_NATIVE`** — distributed via Mistral Workflows. Lives in the external `pipelex-mistralai-workflows` repo.

`DIRECT` is the only one that belongs in core. The other two are **peers**: optional, discovered, neither privileged. Today core fails that test — it names *both* external orchestrators by string (see the seam below). Mistral is the proof that "orchestrator" is a *category with ≥2 members*, so the seam must be generic and N-ary, not "Temporal plus a special case."

## Two worked instances

|  | `DIRECT` (core) | `pipelex-temporal` | `pipelex-mistralai-workflows` |
|---|---|---|---|
| **Maps a pipe onto** | in-process async calls | Temporal workflows + activities | Mistral Workflows workflows + activities |
| **Pipelex contracts implemented** | core default | `PipeRouterProtocol`, `PipeRunProtocol`, `ContentGeneratorProtocol`, task manager | `PipeRunProtocol`, `PipeRouterProtocol` |
| **How core couples to it *today*** | n/a | lazy imports gated on `get_config().temporal.is_enabled` (hub injection in `pipelex.py`) + `bridge._run_temporal_*` + **hard** CLI imports in `_cli.py` | **hard-coded import** in `bridge._run_mistral_native` of `pipelex_mistralai_workflows.primitives.pipe_run` + a `requires_mistral_workflows_extra` gate |
| **Activation model** | default | **boot-global** (hub swap when enabled) **+ per-call** modes | **per-call** (`execution_mode`); installs its router *inside* the workflow at runtime |
| **Also a plugin for…** | — | its host: register workflows/activities with a Temporal worker | its host: register workflows/activities with a Mistral worker (`register_pipelex_primitives`) |

Two different couplings, same fix: invert them through one registry.

## The seam: an execution-mode → orchestrator registry

`bridge.py` currently does a `match input_payload.execution_mode:` whose arms hard-code both external orchestrators — the `TEMPORAL_*` arms lazily import `pipelex.temporal`, the `MISTRAL_NATIVE` arm lazily imports `pipelex_mistralai_workflows`. That is **two string couplings** to remove.

Replace the `match` with a registry keyed by execution mode. Core registers `DIRECT`; each orchestrator plugin registers its mode(s) through the shared `pipelex.plugins` entry point; the bridge collapses to a lookup:

```python
orchestrator = orchestrator_registry.get(input_payload.execution_mode)
if orchestrator is None:
    raise MissingOrchestratorError(
        mode=input_payload.execution_mode,
        hint="install pipelex-temporal / pipelex-mistralai-workflows",
    )
return await orchestrator.run(pipe_job=pipe_job, delivery_assignment=delivery_assignment)
```

**Keep the `PipelexExecutionMode` enum in core.** It is a small, stable *taxonomy of strategies*; core can know the *names* without the *implementations*. That is what lets the error above name the missing package, and keeps the `requires_pipelex_temporal` / `requires_mistral_workflows_extra` gates statically typed. Plugins supply *orchestrators* for existing enum values — they do not invent modes. (Third-party-defined modes would mean an open, string-keyed mode space; that's a larger change, defer it until something actually needs it.)

## Two activation models → the `Plugin` protocol is a menu of hooks

The orchestrators do not use the seam the same way, and the protocol must not be modelled on Temporal alone:

- **Per-call dispatch (primary).** The bridge picks an orchestrator by `execution_mode` for each run. Both Temporal modes *and* Mistral use this. Hook: **`register_orchestrators(registry)`**.
- **Boot-global swap (Temporal only).** When `temporal.is_enabled`, the default router / run / content-generator / task-manager are swapped at boot via hub injection — necessary because *inside a Temporal worker* the content generator must dispatch each operation as an activity. Hook: **`register_hub_implementations(hub, config)`** + lifecycle.
- **Mistral needs no boot swap.** It installs `MistralWorkflowsPipeRouter` *inside* the child workflow at runtime, per call — so it uses `register_orchestrators` and essentially nothing at boot. It is the counter-example that keeps the protocol honest: hooks are a **menu**, each plugin implements the subset it needs.
- **CLI is optional.** Temporal contributes `worker` + `setup-temporal-namespace`; Mistral contributes none (the worker is the user's Mistral worker). Hook: **`register_cli_commands(app)`**.

## The orchestrator SPI (published surface)

A clean plugin must depend only on a *designed* surface, never reach into internals. Where the two orchestrators sit today:

- **Temporal** depends on hub setters + the three protocols + its config field — mostly already protocol-shaped.
- **Mistral** reaches deeper, and says so: its own `wip/boundary-violation-mistral-native.md` documents that the native tier imports `pipelex.hub`, `pipelex.pipe_run.*`, `pipelex.core.*`, `pipelex.graph.*`, `pipelex.tracing.*` — well outside the declared `runtime_bridge.*`-only surface.

That is a **signal, not a sin**: running a pipe out-of-process genuinely needs library/crate access (`hub`), the `PipeJob` / `PipeOutput` types (`core`), the router/run protocols (`pipe_run`), and the trace/tracer hooks (`graph` / `tracing`). The fix is to **publish that set as an orchestrator SPI**, not to keep an honor-system "runtime_bridge only" rule that's already breached. Define the SPI as:

- the orchestrator registry + the `PipeRouterProtocol` / `PipeRunProtocol` / `ContentGeneratorProtocol`;
- `PipeJob` / `PipeOutput` and the boundary payload types;
- library-crate access (for per-call library hydration — Mistral already does this via `library_crate_dump`);
- the tracing/graph hooks an orchestrator must integrate with.

Anything an orchestrator imports *outside* the SPI is a design bug to resolve — promote it into the SPI, or remove the need. (This is the same theme as the OpenAI *substrate* becoming a deliberate contract in the [driver doc](inference-backends-as-plugins.md): once an out-of-tree consumer depends on you, the dependency surface must be designed, not accidental.)

## One repo, two hosts (the adapter shape)

`pipelex-mistralai-workflows` depends on **both** `pipelex` and `mistralai-workflows`. It is a bridge/adapter: a Pipelex orchestrator plugin on one side, a Mistral Workflows activity/workflow library on the other. The two "plugin" directions use **different mechanisms**, and conflating them causes confusion:

- **→ Pipelex: entry-point discovery.** Declare `[project.entry-points."pipelex.plugins"]`; installing the wheel makes `MISTRAL_NATIVE` available and core stops hard-coding the import.
- **→ Mistral: registration-by-import.** Mistral has no plugin registry; the user (or the package's `register_pipelex_primitives(workflows, activities)` helper) hands the workflow/activity classes to their worker. No entry point — and nothing to change. (Temporal is identical on *its* host: you always register workflows/activities with a worker explicitly.)

```toml
[project]
name = "pipelex-mistralai-workflows"
dependencies = ["pipelex>=X", "mistralai-workflows>=3.4.0"]   # depends on BOTH hosts

# Pipelex side — discovery
[project.entry-points."pipelex.plugins"]
mistral-native = "pipelex_mistralai_workflows.plugin:MistralWorkflowsOrchestrator"

# Mistral side — NO entry point: users call register_pipelex_primitives(...) on their worker.
```

This is the natural shape for an adapter — **don't split it.** The host-agnostic decomposition plumbing (pipe classification) already lives in core under `runtime_bridge/primitives/`; everything left is inherently bi-lateral.

## Effort & risk

- **The per-call dispatch inversion is small** — one `match` → a registry lookup; both external orchestrators are already behind lazy/dynamic imports.
- **The SPI definition is the real design work** — settle what core publishes and resolve Mistral's boundary violation against it. This gates a *clean* extraction (the mechanical move is easy; the contract is the part worth getting right).
- **Temporal's boot-global hub-injection inversion is the heavier mechanical piece** — detailed seam-by-seam in [`temporal-as-plugin.md`](temporal-as-plugin.md).
- **Watch:** registration timing — `DIRECT` must always be registered, and a requested-but-absent orchestrator must produce the "install X" error, not a `None` deref. Keep the enum + `requires_*` gates as the typed source of truth for *which modes exist*.

## Suggested phasing

- **Phase 0 — define the seam.** `Plugin` protocol + entry-point discovery + the execution-mode → orchestrator registry + the published orchestrator SPI. Register `DIRECT` in core through it and collapse the bridge `match` to a registry lookup (external orchestrators still resolved as today, now *behind* the registry — no behaviour change). _Checkpoint: the bridge no longer matches on specific external modes; `DIRECT` flows through the registry; suite green._
- **Phase 1 (Temporal) — through the seam.** See [`temporal-as-plugin.md`](temporal-as-plugin.md) Phase 1 (register hub implementations + orchestrators + CLI; resolve the config cut line).
- **Phase 1′ (Mistral) — through the seam.** Replace `bridge._run_mistral_native`'s hard import with the orchestrator the `pipelex-mistralai-workflows` entry point registers; resolve its boundary violation against the published SPI. _Checkpoint: core has zero string references to `pipelex_mistralai_workflows`; `MISTRAL_NATIVE` works purely via discovery._
- **Phase 2 — repackage as needed.** Temporal: extract `pipelex/temporal/` → `pipelex-temporal` (its doc). Mistral: already external — just flip the dev path-pin to a published `pipelex` once the SPI lands.
