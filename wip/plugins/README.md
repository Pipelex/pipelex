# Pipelex plugin architecture

**Status:** assessment / design notes (not started)

> **The decided design lives in [`design.md`](design.md)** — a single unified design covering both inference (driver) plugins and orchestration (strategy) plugins, with decisions and rationale. **The executable [`implementation-plan.md`](implementation-plan.md)** is built from it (phases 0–5, grounded `file:line` refs, per-phase tests, decisions D1–D6, reviewed via `/plan-eng-review` + codex). The four documents here ([`README.md`](README.md), [`inference-backends-as-plugins.md`](inference-backends-as-plugins.md), [`orchestrators-as-plugins.md`](orchestrators-as-plugins.md), [`temporal-as-plugin.md`](temporal-as-plugin.md)) are the background assessment that fed the design. Start with `design.md`, then `implementation-plan.md`; read these for the deeper per-area analysis.

Pipelex has two families of optional integrations that should become real, discoverable **plugins** behind a single shared seam:

1. **[Orchestrators](orchestrators-as-plugins.md)** — *strategy* plugins. They decide *where/how* a pipe runs and replace core orchestration seams. Core ships only the in-process `DIRECT` orchestrator; the distributed ones are optional plugins. Two worked instances:
    - **[Temporal](temporal-as-plugin.md)** — `pipelex/temporal/` → `pipelex-temporal`. The heavy case: boot-global hub swap + per-call modes + CLI + config.
    - **Mistral Workflows** — the external `pipelex-mistralai-workflows` repo. Per-call only; also a plugin for *its* host (a two-host adapter). Already wired (by a hard-coded core import — the coupling to invert).
2. **[Inference backends](inference-backends-as-plugins.md)** — *driver* plugins. The SDK wrappers under `pipelex/plugins/` (OpenAI, Anthropic, Google, Mistral, Bedrock, Fal, Docling, Linkup, …). Homogeneous, many, selected at runtime by a model's `sdk` handle.

All are already ~80–90% decoupled (lazy imports, optional extras, abstract contracts, hub/registry seams). None is yet a *plugin* in the installable sense — orchestrators are still named by string from core (both Temporal *and* Mistral); inference backends are still dispatched from hardcoded `match` statements. The work is the same shape for all: **invert the last coupling through a registry, discover via entry points, optionally repackage.**

> **Naming caveat:** "plugin" is currently overloaded. `pipelex/plugins/` holds in-tree SDK adapters, `Plugin` is a backend selector, `PluginManager`/`PluginSdkRegistry` is an SDK-client cache — none is a real plugin system. The inference doc proposes renaming those before building the real thing. Read that first if the vocabulary trips you up.

---

## Synthesis: best practices for plugins on a codebase like this

Concise, ordered roughly by what to do first.

1. **Invert the dependency, always.** Core must never name a plugin module — not by import, not by string. Plugins depend on core's *published protocols*; core depends on nothing downstream. Every current coupling (Temporal's lazy imports, the inference `match` statements) becomes "ask a registry / call a hook." This is the whole game; the rest is mechanism.

2. **One discovery mechanism: entry points.** Use `importlib.metadata.entry_points(group="pipelex.plugins")`, loaded once at boot. Installing a dist makes it discoverable — zero config, no import-by-string, no scanning. Both strategy and driver plugins ride the same group.

3. **A thin `Plugin` protocol whose hooks are a *menu*, called at known lifecycle points.** Core invokes hooks (`register_hub_implementations`, `register_cli_commands`, `register_orchestrators`, `register_workers`, `setup`, `teardown`); each plugin implements only the subset it needs. Temporal uses nearly all of them (boot-global hub swap + per-call modes + CLI + config); Mistral uses only per-call mode registration. Designing the protocol against *both* keeps it from over-fitting one backend. No magic, no base-class inheritance from core internals — structural typing against a `Protocol`.

4. **Registries replace both `match` statements and hub hard-wiring.** Core owns the registry + the abstract contract (`InferenceWorkerAbstract`, `PipeRouterProtocol`, …); plugins own the entries. Three shapes, one idea: driver registries keyed by data (the `sdk` handle); the execution-mode → orchestrator registry keyed by `PipelexExecutionMode` (per-call dispatch, replacing the bridge `match`); singleton hub setters (boot-global strategy swap). Keep the *taxonomy* enums (`PipelexExecutionMode`) in core so the names exist without the implementations — that's what lets a missing backend produce "install pipelex-temporal" instead of a `None` deref.

5. **Dogfood the plugin API in-tree before externalizing.** Make the built-in backends and Temporal register *through the seam* while still living in the repo. This proves the seam with a green test suite (Phase 1 in both docs) and turns later extraction into a packaging move, not a refactor. Don't externalize on faith.

6. **Lazy SDK imports + a great `MissingDependencyError`.** Never touch a heavy SDK until its plugin is selected. Gate with `importlib.util.find_spec(...)`, and when missing, raise an error naming the lib *and* the extra *and* (where possible) an alternative — the inference factories already do this well; preserve that quality when the guard moves into registration.

7. **Optional extras are a stepping stone, not the destination.** `pipelex[temporal]`, `pipelex[anthropic]` are good today. A real plugin dist packages its own deps, so the extra collapses into the dist's dependency list. Split a dist out only when dependency weight or release cadence justifies it.

8. **Keep config schema importable without the SDK.** The `if TYPE_CHECKING: from sdk import X / else: X = Any` placeholder (see `config_temporal.py`) lets a typed config field survive on installs that skipped the extra. Decide per integration whether the schema stays in core (recommended — keeps static typing) or moves into the plugin (needs a pluggable-config hook).

9. **Detect capability without importing.** Cross-cutting code that must *not* drag an SDK onto the hot path should sniff `sys.modules.get("...")` rather than import (see `reporting_manager.py` detecting a Temporal activity context). Survives extraction unchanged.

10. **Lifecycle symmetry.** `setup()` / `teardown()` hooks, idempotent, with teardown in `finally`/registry cleanup (the `SdkClientRegistry.teardown()` and Temporal teardown already model this). Move the teardown currently inlined in `pipelex.py` behind the plugin so the boot file stops knowing about specific integrations.

11. **Publish the dependency surface as a designed SPI — don't let consumers reach into internals.** Once an out-of-tree plugin depends on you, what it imports *is* a contract. Orchestrators legitimately need more than the runtime bridge (library-crate access, `PipeJob`/`PipeOutput`, the router/run protocols, tracer hooks) — so define an orchestrator SPI rather than an honor-system "this package only" rule (which `pipelex-mistralai-workflows` already breaches). Same theme as the OpenAI *substrate* in the driver doc: a designed surface, not an accidental one. Anything imported outside the SPI is a design bug — promote it or remove the need.

12. **One repo can plug into several hosts.** An adapter is naturally multi-sided (`pipelex-mistralai-workflows` is a Pipelex orchestrator plugin *and* a Mistral Workflows activity library). One wheel, two contracts, two registrations — and they can use different mechanisms (Pipelex: entry-point discovery; Mistral: registration-by-import, since it has no registry). Don't split an adapter whose whole job is bridging two worlds.

13. **Version the core↔plugin contract.** A plugin should declare which core API it targets so an incompatible pairing fails loud at load time, not mysteriously at runtime. "No backward compatibility" is the repo policy — make the contract break *visible*. **Not yet achieved by the implementation** — the shipped `PLUGIN_API_VERSION` gate is documentary only (every plugin imports the constant, so its declared version always equals the installed core and the exact-match gate can never fire; `#1000` already shipped a breaking orchestrator-SPI change without a bump and nothing caught it). The task to build this properly (pin a literal built-against version; semver compat rule) is [`plugin-api-version-gating-semver.md`](plugin-api-version-gating-semver.md).

14. **Tests, markers, and CLI options travel with the plugin.** The `temporal` pytest marker and `--temporal-server` option move with `pipelex-temporal`; backend tests move with their dist. Keep protocol-level conformance tests in core so any plugin can be checked against the contract.

15. **Fail loud on a broken plugin.** If a discovered entry point fails to import or register, surface it with context — don't silently skip (a silently-missing backend looks like a config bug to the user). Distinguish "not installed" (fine, expected) from "installed but broken" (loud).

### The one-line version

> Define a single entry-point–discovered `Plugin` protocol; turn every place core currently *names* an integration (Temporal's lazy imports, the inference `match` statements) into a *registry lookup* or *hook call*; prove it in-tree with a green suite; repackage only what's worth repackaging.
