# Temporal as a Pipelex plugin

**Status:** assessment / proposed plan (not started)
**Scope:** the concrete, seam-by-seam extraction of the Temporal integration into a first-class plugin — wired through the shared orchestrator seam rather than named by string from core. An independent release cadence becomes a *possible consequence* of this, not the goal.

> This is the **Temporal-specific** detail of one orchestrator. The shared mechanism — the `Plugin` protocol, entry-point discovery, the execution-mode → orchestrator registry, the published orchestrator SPI, and the activation-model menu of hooks — lives in [`orchestrators-as-plugins.md`](orchestrators-as-plugins.md), where Temporal and `pipelex-mistralai-workflows` are the two worked instances. The **driver** half (inference SDK wrappers) is in [`inference-backends-as-plugins.md`](inference-backends-as-plugins.md); cross-cutting best practices are in [`README.md`](README.md). Read the category doc first; this one assumes it.

## Verdict

Highly separable — the runtime is already ~90% decoupled. All Temporal code lives in `pipelex/temporal/` (plus its tests under `tests/{unit,integration}/pipelex/temporal/`). The dependency direction is one-way: `pipelex/temporal/` imports *from* core, and core almost never names `pipelex.temporal` back. The runtime already injects the Temporal implementations through the hub (`set_content_generator`, `set_pipe_router`, `set_pipe_run`, plus `temporal_hub.set_task_manager`) behind existing protocols, and nearly every reference is a **lazy** import gated on `if get_config().temporal.is_enabled:`. `temporalio` is already an opt-in extra, and `config_temporal.py` is deliberately importable *without* the SDK (a `TYPE_CHECKING` / `Any` placeholder stands in for `RetryPolicy`).

So this is **not** a refactor of the Temporal code. It is about (1) defining a plugin seam in core, and (2) inverting the handful of places where core still names `pipelex.temporal` so they go through that seam instead.

## How Temporal uses the orchestrator seam

Temporal is the **heaviest** instance of the orchestrator category — it exercises nearly every hook the shared `Plugin` protocol offers (Mistral, the other instance, uses only a subset; that contrast is what keeps the protocol generic — see the category doc's "activation models" section). What Temporal needs:

- **`register_hub_implementations(hub, config)`** — inject `ContentGeneratorInWorkflow`, `TemporalPipeRouter`, `TemporalPipeRun`, `TemporalTaskManager` when its config slice is enabled. This is the **boot-global** activation model; Temporal is the only current backend that needs it (inside a Temporal worker the content generator must dispatch each operation as an activity).
- **`register_orchestrators(registry)`** — own the `TEMPORAL_BLOCKING` / `TEMPORAL_FIRE_AND_FORGET` orchestrators the bridge dispatches to (the **per-call** activation model, shared with Mistral).
- **`register_cli_commands(app)`** — add the `worker` and `setup-temporal-namespace` Typer commands.
- **`register_config_section(...)`** — contribute (or validate) its `temporal` config slice. (See config decision below — this hook is only load-bearing if the schema moves out of core.)
- **lifecycle** — `setup()` / `teardown()` so the worker/task-manager teardown currently inlined in `pipelex.py` moves behind the plugin.

## What's already in our favour

- **One package, one direction.** Everything Temporal-specific is under `pipelex/temporal/` (`tprl_pipe/` router+run workflows, `tprl_content_generation/` activities, `codec/`, `temporal_data_converter.py`, `temporal_task_manager.py`, `config_temporal.py`, `exceptions.py`, `worker_cli.py`). Core → temporal references are the only thing to cut.
- **Hub injection seams exist.** `PipelexHub` already accepts swappable implementations behind protocols (`set_content_generator`, `set_pipe_router`, `set_pipe_run`); `temporal_hub.set_task_manager` covers the task manager. The Temporal variants (`ContentGeneratorInWorkflow`, `TemporalPipeRouter`, `TemporalPipeRun`, `TemporalTaskManager`) all implement those protocols.
- **Protocols exist.** `ContentGeneratorProtocol`, `PipeRouterProtocol`, `PipeRunProtocol` already abstract the swap points.
- **Opt-in extra.** `pyproject.toml`: `temporal = ["temporalio==1.24.0", "aiohttp>=3.14.0"]`. The SDK is never a hard dependency of base.
- **SDK-free config.** `config_temporal.py` imports no `temporalio` at runtime (`if TYPE_CHECKING: from temporalio.common import RetryPolicy` / `else: RetryPolicy = Any`), so the config schema is importable on installs that skipped the extra.
- **SDK-free capability detection.** `reporting/reporting_manager.py` detects "am I inside a Temporal activity?" via `sys.modules.get("temporalio.activity")` — no import, so it never pulls the SDK onto the boot hot path. This pattern survives extraction unchanged.

## The complete list of seams to cut

| # | Site | Current coupling | Hard or lazy |
|---|------|------------------|--------------|
| 1 | `system/configuration/configs.py` | `from pipelex.temporal.config_temporal import Temporal` (top import) + `temporal: Temporal` field on `PipelexConfig` | **HARD** (the only non-lazy import of the package) |
| 2 | `pipelex.py` boot | content generator (`ContentGeneratorInWorkflowFactory`), task manager (`Tasks` + `temporal_hub` + `TemporalTaskManager`), pipe router (`make_temporal_pipe_router`), pipe run (`make_temporal_pipe_run`) — all gated on `get_config().temporal.is_enabled`, injected via the hub | lazy |
| 3 | `pipelex.py` teardown | `temporal_hub` reset + `TemporalTaskManager.teardown()`, gated on a stored handle | lazy |
| 4 | `runtime_bridge/bridge.py` | `_run_temporal_blocking` / `_run_temporal_fire_and_forget` (lazy imports of `temporal.exceptions` + `make_temporal_pipe_run`) + `_require_pipelex_temporal_extra()` availability check | lazy |
| 5 | `cli/_cli.py` | top imports of `worker_cmd` / `setup_temporal_namespace_cmd` + their `app.command(...)` registration | **HARD** |
| 6 | `cli/commands/worker_cmd.py` | lazy `from pipelex.temporal.temporal_hub import get_task_manager` + `temporal_enabled=True` boot flag | lazy (rides with the command, moves wholesale) |
| 7 | `reporting/reporting_manager.py` | `sys.modules.get("temporalio.activity")` — introspection only, never imports | already decoupled — leave as-is |

Only **#1 and #5 are hard imports.** Everything else is already behind a lazy/gated seam and just needs to call through a registry instead of a literal module path.

## Recommended approach: invert Temporal's seams onto the shared registry

The generic plumbing — the `Plugin` protocol, entry-point discovery, the execution-mode → orchestrator registry, and the published orchestrator SPI — is defined once in [`orchestrators-as-plugins.md`](orchestrators-as-plugins.md) (Phase 0 there). It does **not** belong to Temporal. This section assumes that seam exists and covers only what's Temporal-specific.

1. **Invert seams #2–#6 onto the seam.** Replace the four `if is_enabled: from pipelex.temporal...` boot blocks and the matching teardown with `register_hub_implementations` / lifecycle hooks. The bridge's run-mode dispatch (`TEMPORAL_BLOCKING` / `TEMPORAL_FIRE_AND_FORGET`) becomes an orchestrator lookup the plugin populated, so `bridge.py` no longer names `pipelex.temporal` at all. CLI registration in `_cli.py` becomes plugin-driven `app.command(...)` instead of two hard imports.

2. **Decide the config-field cut line (#1) — the one real decision.** Two options:
   - **(Recommended) Keep the `Temporal` config schema in open `pipelex`** and move only the *implementation*. The schema is pure data with no `temporalio` runtime dependency; the genuine logic (workflows, activities, worker, converter, codec) is what moves. Lowest churn, keeps the root config statically typed, makes seam #1 a no-op. The `register_config_section` hook then stays dormant for Temporal.
   - **Move config out too** for a truly zero-`pipelex.temporal` open repo: replace the typed `temporal: Temporal` field with a pluggable section the plugin parses its own slice of. Cleaner boundary, but loses static typing on that subtree and adds validation plumbing — this is the only thing that makes `register_config_section` load-bearing.

3. **Repackage as a real plugin dist.** Move `pipelex/temporal/` and its tests into `pipelex-temporal`, depending on `pipelex` + `temporalio`, declaring the `pipelex.plugins` entry point. Downstream consumers (`pipelex-worker`, `pipelex-api-hosted`) pin `pipelex-temporal` instead of `pipelex[temporal]`. The base `pipelex` `temporal` extra is dropped (or reduced to just `temporalio` for anyone integrating against the protocols without our implementation). **This is the step that makes an independent release cadence trivial** — but it's optional: the plugin can equally well stay in-repo as long as it's wired through the seam.

## Open question to settle before coding

- **Does the config schema (`config_temporal.py`) stay open/in-core or move into the plugin?** This drives whether seam #1 is a no-op (schema stays, only implementation moves) or requires a pluggable-config mechanism. Recommendation above is to keep it in core.

## The data converter / codec

`temporal_data_converter.py` + `codec/` (incl. `codec_server_cli.py`, `storage_payload_codec.py`) is the most logic-heavy piece, but it is self-contained and Temporal-specific — it moves wholesale with the package. It registers through Temporal's own client/worker config, not through any core seam, so it adds no new coupling to cut.

## Distribution mechanics

- New package `pipelex-temporal`, depends on `pipelex` + `temporalio`, declares `[project.entry-points."pipelex.plugins"]`. Published wherever fits (PyPI or `git+ssh`) — the seam is identical either way.
- The `temporal` pytest marker and the `--temporal-server` CLI option plumbing (in `conftest.py`) relocate with the tests.
- Downstream pins flip from `pipelex[temporal]==X` to `pipelex-temporal==Y` (which itself pins a compatible `pipelex`).
- The base `pipelex` `temporal` extra is dropped or reduced to just `temporalio` for protocol-level integrators.

## Effort & risk

- **Low-to-moderate.** The hard work (protocol-based injection, lazy gating, SDK-free config, SDK-free activity detection) already landed with the runtime-bridge work. The remaining work is mostly mechanical: build the plugin/registry seam, rewire the small number of call sites, make CLI + run-mode registration dynamic, lift the package + tests.
- **Watch-items:**
  - The config-field decision above.
  - The data converter / codec is logic-heavy but self-contained.
  - The Temporal test suite (unit + integration) moves wholesale, with the marker and the `--temporal-server` option.
  - `reporting_manager.py`'s `sys.modules` check must keep working without importing `pipelex.temporal` (it already does).
  - Don't build the seam to Temporal's shape. Temporal exercises every hook (boot-global hub swap + per-call modes + CLI + config), which makes it tempting to over-fit. `pipelex-mistralai-workflows` uses only per-call mode registration and no boot swap — it's the counter-example that keeps the protocol a menu of hooks. See [`orchestrators-as-plugins.md`](orchestrators-as-plugins.md).

## Suggested phasing

Assumes the shared seam from [`orchestrators-as-plugins.md`](orchestrators-as-plugins.md) Phase 0 (Plugin protocol, entry-point discovery, execution-mode → orchestrator registry, SPI) already exists.

- **Phase 0 — decide config cut line.** Settle the open question. _Checkpoint: cut line agreed before any code moves._
- **Phase 1 — wire Temporal through the seam, in-tree.** Convert seams #2–#6: hub injection → `register_hub_implementations`; run-mode dispatch → registered handlers; CLI → `register_cli_commands`; teardown → lifecycle hook. No behaviour change (Temporal still in-repo, now registered through the seam instead of hard/lazy imports). _Checkpoint: full suite green with Temporal still in-repo but wired through the seam — proves it before extraction._
- **Phase 2 — extract.** Move `pipelex/temporal/` + tests into `pipelex-temporal`, wire its entry point, flip downstream pins, drop/reduce the base extra. _Checkpoint: base `pipelex` has zero `pipelex.temporal` references; `pipelex-temporal` test suite green against the published base._
