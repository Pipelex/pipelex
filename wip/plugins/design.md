# Pipelex plugin system — design

**Status:** design (proposed, not started)
**Supersedes for design intent:** the four assessment notes in this folder ([`README.md`](README.md), [`inference-backends-as-plugins.md`](inference-backends-as-plugins.md), [`orchestrators-as-plugins.md`](orchestrators-as-plugins.md), [`temporal-as-plugin.md`](temporal-as-plugin.md)) are the research that fed this document. This is the single, decided design the implementation plan is built from.

This document defines one plugin system covering both families of optional integration Pipelex has today: **inference backends** (the SDK adapters selected by a model's `sdk` handle) and **orchestrators** (the strategies that decide where/how a whole pipe runs — Temporal, Mistral Workflows). They are different in shape but share one discovery mechanism, one plugin contract, and one set of design rules.

---

## 1. Motivation

Pipelex already has both integration families, and both are already ~80–90% decoupled — lazy imports, optional extras, abstract contracts, hub/registry seams. What's missing in both is the *last* inversion: core still **names** each integration.

- **Inference backends** are dispatched from centralized `match plugin.sdk:` statements inside four worker factories (`cogt/{llm,img_gen,extract,search}/*_worker_factory.py`). A third party cannot add a backend without editing core.
- **Orchestrators** are named by string in `runtime_bridge/bridge.py`'s `match input_payload.execution_mode:` — the `TEMPORAL_*` arms lazy-import `pipelex.temporal`, the `MISTRAL_NATIVE` arm **hard-imports** `pipelex_mistralai_workflows`. Temporal is further wired into core boot/teardown (`pipelex.py`), config (`system/configuration/configs.py`, the one hard import of the package), and the CLI (`cli/_cli.py`, two hard imports).

The job is the same for both: **invert the last coupling through a registry, discover via entry points, and (only where it pays off) repackage.** This is not a rewrite of the integration code — it is a seam in core plus rewiring a small, enumerated set of call sites.

### The naming overload (fix first)

"Plugin" is currently overloaded three ways in `pipelex/plugins/`, and the ambiguity has already leaked into the codebase (the hub raises `"PluginManager2 is not initialized"`). None of the three is a plugin in the installable sense:

- `pipelex/plugins/<backend>/` — directories holding **in-tree SDK adapters**.
- `Plugin` (`plugins/plugin.py`) — a value object (`sdk` + `backend` + `variant`, with an `sdk_handle` like `anthropic@bedrock/claude`). A **backend selector / handle**.
- `PluginManager` / `PluginSdkRegistry` — a **runtime cache of instantiated SDK clients**, keyed by that handle.

The word "plugin" is reserved, from here on, for the new concept: an installable, discoverable unit that registers extensions at boot. See §4 for the rename.

---

## 2. Goals and non-goals

### Goals

- **Core names no integration.** No import of an integration module, no string literal naming one, anywhere on the core code path.
- **One discovery mechanism** for both families: the `pipelex.plugins` entry-point group, plus a static built-in list for in-tree plugins.
- **One plugin contract** — a small, menu-style registration surface that a plugin implements only the subset of.
- **Dogfood in-tree first.** Built-in backends and Temporal register *through the seam* while still living in the repo, proven by a green suite, before anything is externalized. Externalization then becomes a packaging move, not a refactor.
- **Designed dependency surfaces (SPIs).** What an out-of-tree plugin imports is a contract; publish it deliberately instead of letting plugins reach into internals.
- **Preserve today's user-facing behavior and error quality** — same model selection by data, same friendly "install the X extra" messages, same execution modes.

### Non-goals

- **Not** splitting every vendor backend into its own dist. In-tree-but-registerable is the default; externalize only where dependency weight or release cadence justifies it (Temporal qualifies; vendor inference dists do not, yet).
- **Not** a third-party-defined execution-mode space. Plugins supply orchestrators for the *existing* `PipelexExecutionMode` values; inventing new modes is an open string-keyed space we defer until something needs it.
- **Not** a generic typed-config-contribution mechanism in v1. First-party plugin config (Temporal's) stays typed in core; a generic per-plugin config namespace is a documented future extension, built when a third party needs it.
- **Not** backward compatibility shims. Per repo policy, breaks are noted in changelogs and made loud, not smoothed over.

---

## 3. Concepts and vocabulary

| Term | Meaning |
|---|---|
| **Plugin** | An installable, discoverable unit that registers extensions into core at boot. May ship in-repo (built-in) or as a separate dist (external). Implements the plugin contract (§5). |
| **Driver plugin** | A plugin that *supplies an implementation* for a backend core asked for. Many, homogeneous, selected by data (a model's `sdk` handle). The inference backends. |
| **Orchestrator** | A strategy that decides *where/how a whole pipe job runs* (in-process, on a Temporal fleet, on Mistral Workflows). Distinct from a *pipe controller*, which sequences sub-pipes within one run. |
| **Orchestrator plugin** | A plugin that *replaces core orchestration behavior* for one or more execution modes. Few, heterogeneous. |
| **SPI** (Service Provider Interface) | The published, versioned surface of core that plugins are allowed to import. Two of them: an inference SPI and an orchestrator SPI. |
| **`ModelHandle`** | The renamed value object (was `Plugin`): `sdk` + `backend` + `variant`, with `sdk_handle`. Selects which driver runs a model. |
| **`SdkClientRegistry` / `SdkClientManager`** | The renamed runtime cache (was `PluginSdkRegistry` / `PluginManager`): instantiated SDK clients keyed by `sdk_handle`, with lifecycle teardown. |

"Plugin" and "ships as a separate dist" are **orthogonal axes**. Being a plugin means *registering through the seam* instead of being a hardcoded special case. Shipping separately is a packaging decision. A built-in plugin that lives in this repo is the default, not a contradiction.

|  | In-repo | Separate dist |
|---|---|---|
| **Through the seam** | built-in plugins (the default for every backend) | external plugins (`pipelex-temporal`, `pipelex-mistralai-workflows`, future vendor dists) |
| **Hardcoded in core** | the wart we are deleting | n/a |

---

## 4. Architecture overview

One discovery pass produces a list of plugin objects. Each plugin is handed a **registrar** and fills whichever of three registry shapes it serves. Core then consults those registries at the points where it used to name an integration. Plugins import only the published **SPIs**.

```
boot
 └─ discover plugins ─── built-in static list  (in-repo: openai, gateway, anthropic, …, temporal)
                    └─── pipelex.plugins entry points  (external dists)
        │
        ▼  for each plugin (after API-version check): plugin.register(registrar)
   registrar fans contributions into three shapes:
        ├─ keyed registries (lookup by data)
        │     ├─ InferenceBackendRegistry  — keyed by (family, sdk handle)   ← driver plugins
        │     └─ OrchestratorRegistry      — keyed by PipelexExecutionMode   ← orchestrator plugins (per-call)
        ├─ exclusive hub slots (boot-global swap, at most one claimant)
        │     └─ content_generator / pipe_router / pipe_run / task_manager   ← orchestrator plugins (boot-global)
        └─ additive contributions
              ├─ CLI commands (Typer)
              └─ teardown callbacks (run LIFO at shutdown)
        │
        ▼  core consults the registries where it used to name an integration:
   worker factories → InferenceBackendRegistry.lookup(family, sdk)
   bridge dispatch  → OrchestratorRegistry.get(execution_mode)
   hub defaults     → whatever claimed each exclusive slot, else core default
```

The three registry shapes are deliberate — they match the three ways an integration plugs in:

- **Keyed registries** — looked up by runtime data. Inference backends keyed by `(family, sdk)`; orchestrators keyed by `PipelexExecutionMode`. Many entries, additive.
- **Exclusive hub slots** — a boot-global *swap* of a singleton (the default content generator / pipe router / pipe run / task manager). At most one plugin may claim each slot; two claimants is a loud conflict. Only Temporal uses these today.
- **Additive contributions** — CLI commands and teardown callbacks. Appended, never exclusive.

Two SPIs sit underneath:

- **Inference SPI** — the contracts a driver plugin compiles against (the `*WorkerAbstract` hierarchy, `ModelHandle`, `MissingDependencyError`, the `SdkClientRegistry`, the registration factory contract, and the OpenAI-compat substrate).
- **Orchestrator SPI** — the contracts an orchestrator plugin compiles against (the execution protocols, the boundary/core payload types, library-crate access, tracing hooks). Sized to what the existing orchestrators actually import (§9).

---

## 5. Discovery and the plugin contract

### 5.1 The registrar pattern

A plugin is an object exposing identity plus a single `register` method:

```python
@runtime_checkable
class PipelexPlugin(Protocol):
    name: str
    targets_api: int                 # the PLUGIN_API_VERSION it was built against
    def register(self, registrar: PluginRegistrar) -> None: ...
```

`register` is the *menu*: the plugin calls whichever registrar methods it needs and ignores the rest. This is preferred over a six-method "god protocol" (every plugin stubbing methods it doesn't use) or per-capability `isinstance` dispatch (reflection that ignores signatures): one method, one well-defined call point, no magic.

```python
class PluginRegistrar:
    # keyed registries
    def add_inference_backend(self, *, family: InferenceFamily, sdk: str, factory: InferenceBackendFactory) -> None: ...
    def add_orchestrator(self, *, mode: PipelexExecutionMode, orchestrator: OrchestratorProtocol) -> None: ...
    # exclusive boot-global slots (raise on a second claimant)
    def claim_content_generator(self, generator: ContentGeneratorProtocol) -> None: ...
    def claim_pipe_router(self, router: PipeRouterProtocol) -> None: ...
    def claim_pipe_run(self, pipe_run: PipeRunProtocol) -> None: ...
    def claim_task_manager(self, task_manager: TaskManagerProtocol) -> None: ...
    # additive
    def add_cli_command(self, *, name: str, help: str, command: Callable[..., object]) -> None: ...
    def add_teardown(self, callback: Callable[[], None]) -> None: ...
    # read access to the resolved config, so a plugin can gate its own contributions
    @property
    def config(self) -> ConfigRoot: ...
```

A plugin gates its own contributions on config. Temporal's `register` claims the exclusive hub slots **only when `config.temporal.is_enabled`**, but registers its per-call orchestrators and CLI **unconditionally** (so the bridge can dispatch a `TEMPORAL_*` run, and the worker CLI exists, regardless of whether *this* process boots as a Temporal-default runtime). This split is the heart of the two activation models — see §8.

### 5.2 Built-ins vs externals (one contract, two discovery paths)

- **Built-in plugins** are registered from a static list in core (`BUILTIN_PLUGINS = [OpenAIDriver(), GatewayDriver(), AnthropicDriver(), …, TemporalOrchestrator(), …]`). Explicit, fast, no self-scanning of dist metadata. One plugin per *externalizable unit* (per vendor for drivers; one for Temporal), so promoting a built-in to an external dist later is "move it out of the static list, add an entry point in its own dist."
- **External plugins** are discovered via `importlib.metadata.entry_points(group="pipelex.plugins")`, loaded once at boot. Installing a dist makes it discoverable — zero config.

Both paths produce `PipelexPlugin` objects fed through the identical `register(registrar)` pipeline. The seam is dogfooded by every built-in; entry-point discovery is exercised by every external (and by Mistral, which is already a separate repo).

Rationale for the hybrid over pure entry-point discovery for built-ins: declaring a dozen self-referential entry points in `pipelex`'s own `pyproject.toml` and having `pipelex` discover *itself* via `importlib.metadata` is needless ceremony. A static list is clearer and faster, and externalization stays a one-line move. (Alternative considered: pure entry points for built-ins too — rejected as over-engineered for the in-tree default.)

### 5.3 Ordering, timing, and safety

- Discovery and `register` run at one well-defined point in boot — after config is loaded (so plugins can gate on it), before the first worker or pipe run is built. Boot-global slot claims (§8) are *collected* at this point and *applied* at the existing ordered setup points in `Pipelex.setup()` (content generator, then task manager, then router, then run), each falling back to the core default when unclaimed.
- **Core defaults are unconditional.** The `DIRECT` orchestrator and every core-dependency inference backend (`openai`, `gateway`, `portkey`, `pypdfium2`, `azure_rest`) register from core's built-in list and can never be dropped by a misconfigured environment.
- **Registration is import-light** (the lazy-load contract — see §6.5). Building `BUILTIN_PLUGINS` and running every plugin's `register` happens at boot for *all* backends; it must not import any backend SDK. Heavy imports stay inside the factory's `make_worker` / the orchestrator's `run`, exactly where the `match` arms lazy-import today. A plugin object and its `register` therefore live in import-light modules; the SDK is touched only when the backend is actually selected.
- **Conflict policy: duplicate keys fail loud.** Registering a second factory for the same `(family, sdk)` or a second orchestrator for the same `execution_mode` is a startup error naming both contributors — never a silent shadow. Same for an exclusive hub slot claimed twice (§8). This is consistent with the repo's "make breaks visible" stance and guards the transition window where an externalized backend could collide with a still-present built-in. *Deliberately overriding* a built-in (a third party replacing core's OpenAI driver) is a separate, explicit feature — deferred until something needs it, never an accident.
- **Teardown** runs registered callbacks LIFO at shutdown, replacing the Temporal teardown currently inlined in `pipelex.py`.

### 5.4 Versioning the contract

Core exposes `PLUGIN_API_VERSION: int`. Each plugin declares `targets_api`. On load, an incompatible pairing fails loud at startup (naming the plugin, its target, and the core version) — never mysteriously at runtime. A single integer, bumped on any breaking change to the contract or either SPI; "no backward compatibility" means we make the break *visible*, not that we tolerate silent skew.

The single integer is deliberately coarse: a change to *either* SPI bumps it, forcing *every* plugin to re-declare even if its own surface was untouched. With the small set of external plugins we control (Temporal, Mistral), that friction is acceptable and the simplicity wins. Per-SPI versions or semver-range matching are deferred until there are external plugins on independent release trains.

### 5.5 Fail-loud, and "not installed" vs "broken"

- **Not installed** is expected and friendly: a requested backend/mode whose plugin isn't present yields a typed error naming the package *and* the extra *and*, where one exists, an alternative (e.g. "use Anthropic via Bedrock instead"). This is preserved verbatim from today's `MissingDependencyError` quality. Today's typed orchestrator errors (`MissingPipelexTemporalExtraError`, `MissingMistralWorkflowsPluginError`) map onto the registry-miss path — the bridge's `MissingOrchestratorError` carries the same "install `pipelex-temporal`" guidance instead of an `ImportError` caught inline.
- **Installed but broken** is loud: a discovered entry point that fails to import or whose `register` raises is surfaced with context — never silently skipped (a silently-missing backend reads to the user as a config bug).
- The **taxonomy enums stay in core** (`PipelexExecutionMode`, the `requires_*` properties). Core knows the *names* of strategies without their *implementations* — that is what lets a missing orchestrator produce "install pipelex-temporal" instead of a `None` dereference, and keeps the gates statically typed.

### 5.6 Developer experience for plugin authors

The plugin author *is* the user of this system, and the SPI + contract *is* the product they touch. Treat that surface with the same care as a public API.

- **Progressive disclosure — learn only your slice.** The registrar menu means a backend author calls only `add_inference_backend` and implements one `InferenceBackendFactory`; an orchestrator author calls only `add_orchestrator` (plus, for the boot-global case, the `claim_*` slots). Neither has to learn the other family, the hub, or the parts of the SPI they don't use. The minimal backend plugin is: a `PipelexPlugin` (name + `targets_api` + `register`), one factory with `make_worker`, and (if external) one entry-point line. That short path is the time-to-first-plugin we optimize for.
- **Author-facing error empathy.** Errors caused by a plugin's *own* mistake must name the offending plugin and the fix, never surface as an opaque core failure: a factory whose `make_worker` returns the wrong `*WorkerAbstract` for its family, a registration under the wrong `(family, sdk)`, a duplicate key (§5.3), or a missing required identity field. Validate at registration where it's cheap (identity present, `targets_api` set), and at first use where it isn't (worker type matches family) — each error names the plugin.
- **Actionable upgrades (fight upgrade fear).** A `targets_api` mismatch fails loud with the *remedy* in the message: "plugin `pipelex-foo` targets plugin API N, this `pipelex` is API M — upgrade `pipelex-foo`, or pin `pipelex<X`." Any `PLUGIN_API_VERSION` bump or SPI change ships with a migration note in the changelog so an external author knows what moved and why.
- **A getting-started guide and a minimal example are part of the deliverable** (§16), not a follow-up — an SPI without an authoring guide has no real time-to-first-plugin. The example is the canonical "hello world" plugin authors copy from.

---

## 6. Inference (driver) plugins

### 6.1 The seam today

Four worker factories, each a centralized `match plugin.sdk:` that, per arm, does the same three things: optionally `importlib.util.find_spec(...)` to raise a friendly `MissingDependencyError`, lazily import the backend's factory + worker, then build the worker (reusing a cached SDK client from `SdkClientRegistry`). The lazy import inside each arm is already "don't touch the SDK until selected" — it just needs to become "ask the registry for the selected backend's factory."

| Family | File | Selected by |
|---|---|---|
| LLM | `cogt/llm/llm_worker_factory.py` | `plugin.sdk` (gateway/portkey/openai/anthropic/mistral/bedrock/google variants) |
| ImgGen | `cogt/img_gen/img_gen_worker_factory.py` | `plugin.sdk` (gateway/fal/huggingface/openai/blackboxai/azure_rest/google/openrouter variants) |
| Extract | `cogt/extract/extract_worker_factory.py` | `plugin.sdk` (gateway/mistral/pypdfium2/docling/linkup variants) |
| Search | `cogt/search/search_worker_factory.py` | `plugin.sdk` (linkup/gateway variants) |

### 6.2 The registry and the factory contract

One `InferenceBackendRegistry`, keyed by `(family, sdk)`, mapping to an `InferenceBackendFactory`. Core owns the registry and the abstract contracts; driver plugins own the entries.

```python
class InferenceFamily(StrEnum):
    LLM = "llm"
    IMG_GEN = "img_gen"
    EXTRACT = "extract"
    SEARCH = "search"

class InferenceBackendFactory(Protocol):
    def make_worker(
        self,
        *,
        inference_model: InferenceModelSpec,
        backend: InferenceBackend,
        sdk_clients: SdkClientRegistry,
        reporting_delegate: ReportingProtocol | None,
    ) -> InferenceWorkerAbstract: ...
```

Each worker factory collapses to a lookup:

```python
factory = inference_backend_registry.lookup(family=InferenceFamily.LLM, sdk=model_handle.sdk)
return factory.make_worker(inference_model=…, backend=…, sdk_clients=…, reporting_delegate=…)
```

The `find_spec` guard and its friendly `MissingDependencyError` move **into the factory's `make_worker`**, preserving today's semantics: a model needing an absent extra fails *when used*, with the same helpful message — not at boot. A registry *miss* (backend not registered at all) is a distinct, equally-loud error ("backend `<sdk>` is not registered; is its plugin installed?").

Inconsistent factory shapes today (some have a factory class, some instantiate the worker inline) are normalized onto this one `InferenceBackendFactory` contract so every entry looks the same.

**The refactor is a DRY win, not just a relocation.** Every `match` arm today repeats the same `sdk_clients.get(...) or sdk_clients.set(...)` client-cache dance and the same `find_spec → MissingDependencyError(lib, extra, msg)` shape. Lift both into the shared surface: the client-memoization belongs in a small base (`make_worker` asks `sdk_clients.get_or_create(handle, build_client)`), and the extra-guard becomes one helper (`require_sdk(spec="anthropic", extra="anthropic", msg=…)`). Each backend factory then carries only its genuinely-unique parts: which client to build and which worker to wrap. This collapses the largest block of duplication in the current factories.

### 6.3 Cross-family vendors

`mistral` appears in LLM and Extract; `google` in LLM and ImgGen; `linkup` in Extract and Search; `gateway_*` in all four. A vendor's driver plugin simply calls `add_inference_backend` once per `(family, sdk)` it serves. With `(family, sdk)` as the key this is natural — no special handling, and a future per-vendor dist registers into multiple families from its one `register`.

### 6.4 OpenAI: substrate vs driver

The OpenAI SDK is two concerns with opposite fates:

- **Substrate** — the OpenAI-compatible client (`AsyncOpenAI(base_url=…)`), the shared `ChatCompletion*` types, and the completions/responses plumbing that `gateway`, `portkey`, `openrouter`, `blackboxai`, `azure_rest` reuse (and that `anthropic`/`mistral`/`google` import for shared types). This is **infrastructure other backends import**, not a backend. It belongs in **core as an always-on library** (`openai` is already a core dependency). If it were an optional dist, a dozen backends would diamond-depend on it.
- **Driver** — the `openai` / `azure_openai` / `openai_img_gen` registrations. An **always-on built-in plugin, through the seam** — no extra, registered unconditionally, but with no privileged `match` arm. The seam's whole value is that core names no backend; a surviving special case is a two-tier system the next "important" backend will want to join.

**Decision:** the OpenAI driver is an always-on built-in plugin in v1. Promoting the substrate into a deliberately-named core module (e.g. `pipelex.openai_compat`) with a stable signature is **deferred to the externalization phase** — it only becomes a *contract* problem when an out-of-tree dist imports it, and in-tree backends importing each other's modules is acceptable. Doing it earlier is churn with no in-tree payoff. (Captured as the first step of any future "externalize an OpenAI-compatible backend" work.)

### 6.5 Preserving lazy loading (import-light registration)

The current lazy-load behavior — never touch a backend's SDK until a model selects it — is load-bearing for boot time across the CLI, the API, the workers, and the test suite. The registry must preserve it exactly, and that imposes one hard constraint: **registration is import-light**.

- The built-in plugin objects and their `register` methods live in modules that import no backend SDK. `BUILTIN_PLUGINS = [AnthropicDriver(), …]` must be constructible without importing `anthropic`.
- `add_inference_backend(family, sdk, factory)` receives a factory whose construction is also SDK-free. The backend's worker/client modules are imported *inside* `make_worker`, mirroring today's per-arm lazy import.
- The `find_spec` guard runs inside `make_worker` too, so an absent extra fails at use with the friendly message — never at boot.

A boot-time test asserts the invariant (booting with the built-ins registered imports no optional SDK; see §14.3). This is the one place where a careless refactor would silently regress performance, so it gets an explicit guard.

### 6.6 Packaging granularity

In-tree-but-registerable is the v1 destination for all inference backends: third parties can add a backend in their own dist without a core PR, the `match` statements die, and there is no distribution split to maintain. Per-vendor or bundle dists (`pipelex-anthropic`, `pipelex-aws` = bedrock+s3+dynamodb, …) are **deferred** — split a backend out only when its dependency weight or release cadence actually justifies it. The seam makes that a packaging move.

---

## 7. Orchestration (strategy) plugins — the category

An orchestrator answers *"where/how does this pipe run?"*. Pipelex already models the choice as `PipelexExecutionMode`:

- **`DIRECT`** — in-process async. The trivial orchestrator. **Ships in core**, registered through the seam like everything else.
- **`TEMPORAL_BLOCKING` / `TEMPORAL_FIRE_AND_FORGET`** — distributed via Temporal. Today in `pipelex/temporal/`; destined for `pipelex-temporal`.
- **`MISTRAL_NATIVE`** — distributed via Mistral Workflows. Already in the external `pipelex-mistralai-workflows` repo.

`DIRECT` is the only mode that belongs in core. The other two are **peers** — optional, discovered, neither privileged. Mistral is the proof that "orchestrator" is a category with more than one member, so the seam must be generic and N-ary, not "Temporal plus a special case." Core today fails this test: it names *both* external orchestrators by string.

---

## 8. Orchestration — the two activation models

The single most important subtlety: an orchestrator plugs into **two distinct execution entry points**, and a complete plugin serves both.

- **Per-call dispatch (the bridge).** Host runtimes call `run_pipe_via_bridge(...)` and pick an orchestrator by `execution_mode` for each run. This is the `OrchestratorRegistry`, keyed by mode. Both Temporal modes *and* Mistral use this. Registrar hook: `add_orchestrator(mode=…, orchestrator=…)`.
- **Boot-global default (the hub).** A normal (non-bridge) pipe run resolves `get_pipe_run()` / `get_pipe_router()` / `get_content_generator()` from the hub. Inside a Temporal worker these defaults must *be* the Temporal implementations, because the content generator has to dispatch each operation as an activity. This is the **exclusive hub-slot swap**, claimed only when the plugin's config slice is enabled. Registrar hooks: `claim_content_generator/pipe_router/pipe_run/task_manager`.

These are orthogonal and both necessary:

| | Per-call (bridge) | Boot-global (hub default) |
|---|---|---|
| Entry point | `run_pipe_via_bridge`, by `execution_mode` | `get_pipe_run()` / `get_pipe_router()` / `get_content_generator()` |
| Shape | keyed `OrchestratorRegistry` | exclusive hub slots |
| Used by | host runtimes selecting a mode per call | this process running as a Temporal-default runtime |
| Temporal | registers both modes, unconditionally | claims slots only when `temporal.is_enabled` |
| Mistral | registers `MISTRAL_NATIVE`, unconditionally | claims nothing — installs its router *inside* the child workflow at runtime |

Mistral is the counter-example that keeps the contract honest: it uses only `add_orchestrator` and nothing at boot. Temporal is the heaviest instance — it exercises per-call orchestrators, the boot-global swap, CLI commands, lifecycle teardown, and a config slice. Designing the registrar against *both* keeps it from over-fitting Temporal.

### 8.1 The bridge collapse

`bridge.py`'s `match input_payload.execution_mode:` — whose arms hard-code Mistral and lazy-import Temporal — collapses to a registry lookup:

```python
orchestrator = orchestrator_registry.get(input_payload.execution_mode)
if orchestrator is None:
    raise MissingOrchestratorError(
        mode=input_payload.execution_mode,
        hint="install pipelex-temporal / pipelex-mistralai-workflows",
    )
return await orchestrator.run(pipe_job=pipe_job, delivery_assignment=delivery_assignment)
```

After this, `bridge.py` names no integration. `DIRECT` registers from core and flows through the same lookup. The `requires_pipelex_temporal` / `requires_mistral_workflows_extra` properties on the enum stay as the typed source of truth for *which modes need what*.

**Correctness watch — the DIRECT orchestrator must keep its router scoping.** Today `_run_direct` wraps the run in `scoped_pipe_router(PipeRouter())` so that, inside a Temporal-enabled worker (whose hub-default router is the Temporal one), a `DIRECT` call's nested controller sub-pipes resolve the in-process router instead of leaking to Temporal. The extracted `DirectOrchestrator.run` must preserve this scope verbatim — dropping it is a silent correctness bug that only surfaces for DIRECT-inside-a-Temporal-worker (a real configuration). A regression test pins it (§14.3).

### 8.2 Boot/teardown collapse

The four `if get_config().temporal.is_enabled: from pipelex.temporal…` blocks in `Pipelex.setup()` (content generator, task manager, pipe router, pipe run) and the matching teardown become: core consults the exclusive hub slots at the same ordered points, using whatever a plugin claimed, else the core default. The Temporal plugin's `register` populates those slots (gated on its config). The teardown inlined in `pipelex.py` becomes a registered teardown callback. CLI registration in `_cli.py` (today two hard imports) becomes plugin-contributed commands.

---

## 9. The published SPIs

What an out-of-tree plugin imports *is* a contract. We publish two SPIs deliberately rather than letting plugins reach into internals, and we size them to what the orchestrators **actually import today** — measured, not guessed.

### 9.1 Inference SPI

The surface a driver plugin compiles against:

- the worker contracts: `InferenceWorkerAbstract` → `{LLM,ImgGen,Extract,Search}WorkerAbstract`;
- `InferenceModelSpec`, `ModelHandle`, `InferenceBackend` (the backend config record);
- `MissingDependencyError` and the inference error base;
- `SdkClientRegistry` (client memoization + teardown);
- the `InferenceBackendFactory` / `InferenceFamily` registration contract;
- *(deferred)* the `openai_compat` substrate, once extracted (§6.4).

### 9.2 Orchestrator SPI

A measurement of `pipelex-mistralai-workflows`'s actual imports shows the real surface an out-of-process orchestrator needs — far beyond the honor-system "`runtime_bridge.*` only" rule it already breaches:

- **`runtime_bridge.*`** — `bridge`, `bootstrap`, `execution_mode`, `exceptions`, **and `runtime_bridge.primitives.*`** (`delivery`, `hydration`, `pipe_classification`, `submitter_hydration`, `trace_flush`). The primitives live under `runtime_bridge` and are clearly the intended host-runtime helper surface; sanction them explicitly.
- **execution protocols** — `PipeRouterProtocol`, `PipeRunProtocol`, `ContentGeneratorProtocol`, and the task-manager protocol.
- **boundary/core payload types** — `PipeJob`, `PipeOutput`, `DeliveryAssignment`, `WorkingMemory` (+ factory), `JobMetadata`, the `LibraryCrate`.
- **library-crate access + hub scoping** — `set/get_current_library`, `scoped_pipe_router`, `get_class_registry` (per-call library hydration; Mistral already does this via `library_crate_dump`).
- **tracing/graph hooks** — `trace_events`, `graph_tracer_manager`, `tracing_assembly` — an orchestrator must integrate with these to emit per-step trace/usage events across the boundary.

Anything an orchestrator imports *outside* the SPI is a design bug to resolve — promote it into the SPI or remove the need. This is the same theme as the OpenAI substrate becoming a deliberate contract: once an out-of-tree consumer depends on you, the dependency surface must be designed, not accidental.

**Mistral boundary resolution.** `pipelex-mistralai-workflows` documents (its `wip/boundary-violation-mistral-native.md`) that the native tier imports `pipelex.hub`, `pipelex.pipe_run.*`, `pipelex.core.*`, `pipelex.graph.*`, `pipelex.tracing.*` — outside its declared surface. The resolution is **(A) widen the published surface to the SPI above**, then re-point the plugin at it — *not* keep an honor-system rule that's already broken. Until the SPI lands, the plugin's pinned-rev coupling to `pipelex` is the pragmatic interim (already in place).

### 9.3 SPI shape

The SPI is a **documented, versioned set of modules and symbols** — not an `__init__.py` re-export shim (the repo bans re-exports). It is gated by `PLUGIN_API_VERSION` (§5.4). The plan decides whether to additionally provide a thin curated import surface; the contract itself is the documented module/symbol list plus the version marker.

---

## 10. Configuration

Temporal is the only integration with a config slice today (`temporal: Temporal` on `PipelexConfig`, the one hard import of the package in `configs.py`). The `Temporal` schema is pure data with **no `temporalio` runtime dependency** (it uses the `if TYPE_CHECKING: from temporalio.common import RetryPolicy / else: RetryPolicy = Any` placeholder), so it is importable on installs that skipped the extra.

**Decision: keep first-party plugin config schemas typed in core.** The `Temporal` schema stays in `pipelex`; only the *implementation* moves to `pipelex-temporal`. This keeps the root config statically typed, keeps boot's config-load test (`make tb`) meaningful, and makes the config seam a near-no-op — the implementation move does not drag config plumbing with it.

A **generic per-plugin config namespace** for *third-party* plugins (which cannot add typed fields to core's model) is a documented future extension, not built in v1 — there are no third-party plugins yet, and building the mechanism now is speculative. When one needs config, add a `plugins: dict[str, dict[str, Any]]` namespace each plugin parses its own slice of. (Alternative considered: move Temporal config out to the plugin via a pluggable section now — rejected: loses static typing on that subtree and adds validation plumbing for no present benefit.)

---

## 11. Packaging and distribution

| Integration | v1 home | Externalization |
|---|---|---|
| Core (`DIRECT`, openai/gateway/portkey/pypdfium2/azure_rest drivers, openai-compat substrate) | in `pipelex`, always-on | never leaves core |
| Vendor inference drivers (anthropic, google, mistral, bedrock, fal, docling, linkup, huggingface) | in `pipelex`, through the seam | deferred — split only when dep weight / cadence justifies |
| Temporal | in `pipelex/temporal/`, through the seam (Phase: wire first) | **→ `pipelex-temporal`** (depends on `pipelex` + `temporalio`, declares the entry point). High value: independent cadence, heavy SDK, already ~90% separable, and downstream (`pipelex-worker`, `pipelex-api-hosted`) already pin temporal separately. |
| Mistral Workflows | already `pipelex-mistralai-workflows` (external repo) | flip the **hard import** to **entry-point discovery**; resolve its boundary against the SPI; flip its dev path-pin to a published `pipelex` once the SPI lands |

### 11.1 Tests, markers, and CLI travel with the plugin

When an integration is externalized, its tests move with it. The `temporal` pytest marker and the `--temporal-server` CLI option (in `conftest.py`) relocate to `pipelex-temporal`; backend tests move with their dist. **Protocol-level conformance tests stay in core** so any plugin — built-in or external — can be checked against the contract. Downstream pins flip from `pipelex[temporal]==X` to `pipelex-temporal==Y` (which itself pins a compatible `pipelex`).

### 11.2 One repo, two hosts (the adapter shape)

`pipelex-mistralai-workflows` depends on **both** `pipelex` and `mistralai-workflows`: a Pipelex orchestrator plugin on one side, a Mistral Workflows activity/workflow library on the other. The two directions use **different mechanisms** and must not be conflated:

- **→ Pipelex: entry-point discovery.** `[project.entry-points."pipelex.plugins"]` makes `MISTRAL_NATIVE` available; core stops hard-coding the import.
- **→ Mistral: registration-by-import.** Mistral has no plugin registry; the user (or the package's `register_pipelex_primitives(...)` helper) hands workflow/activity classes to their worker. No entry point. (Temporal is identical on *its* host — you always register workflows/activities with a worker explicitly.)

This is the natural shape for an adapter — do not split it.

---

## 12. Worked examples

**A driver plugin (built-in, e.g. Anthropic).** Implements `PipelexPlugin`; its `register` calls `add_inference_backend(family=LLM, sdk="anthropic", factory=AnthropicLLMBackendFactory())` (and `bedrock_anthropic` likewise). The factory's `make_worker` runs the `find_spec("anthropic")` guard → friendly error, builds/caches the client via `sdk_clients`, returns an `AnthropicLLMWorker`. Lives in core's `BUILTIN_PLUGINS`. Externalizing later = move to `pipelex-anthropic` + add an entry point.

**The Temporal orchestrator plugin (heaviest).** Its `register`: always `add_orchestrator(TEMPORAL_BLOCKING, …)` and `add_orchestrator(TEMPORAL_FIRE_AND_FORGET, …)`; always `add_cli_command("worker", …)` and `add_cli_command("setup-temporal-namespace", …)`; **if `config.temporal.is_enabled`**, `claim_content_generator(ContentGeneratorInWorkflow())`, `claim_pipe_router(make_temporal_pipe_router())`, `claim_pipe_run(make_temporal_pipe_run())`, `claim_task_manager(TemporalTaskManager())` and `add_teardown(...)` for the task manager. Config schema stays in core; implementation moves to `pipelex-temporal`.

**The Mistral orchestrator plugin (per-call only).** Its `register`: `add_orchestrator(MISTRAL_NATIVE, MistralWorkflowsOrchestrator())`. Nothing at boot. Installs its own router inside the child workflow at runtime. Discovered via its entry point.

**An out-of-tree third-party backend.** A dist declaring `[project.entry-points."pipelex.plugins"] my-backend = "my_pkg.plugin:MyBackendPlugin"`, depending on `pipelex>=X` and its own SDK. Installing it makes its `sdk` selectable from model TOML — no core change.

---

## 13. Key decisions

| # | Decision | Choice | Why / alternative |
|---|---|---|---|
| D1 | Naming | `Plugin`→`ModelHandle`; `PluginManager`/`PluginSdkRegistry`→`SdkClientManager`/`SdkClientRegistry`; "plugin" reserved for the new concept | Kills the three-way overload (and the `PluginManager2` artifact). Pure rename, lands first. Alt name `BackendSelector` noted. |
| D2 | Discovery | Hybrid: static built-in list + `pipelex.plugins` entry points for externals | Avoids self-referential entry points / self-metadata-scan; externalization stays a one-line move. Alt: pure entry points everywhere — over-engineered for the in-tree default. |
| D3 | Plugin contract | One `PipelexPlugin.register(registrar)` method; registrar is the menu | Idiomatic, no god-protocol, no `isinstance`-reflection. Alts: capability protocols / six optional hooks — more magic or more boilerplate. |
| D4 | Registry shapes | Keyed registries (inference, orchestrators) + exclusive hub slots + additive (CLI, teardown) | Matches the three real ways integrations plug in; exclusive slots fail loud on conflict. |
| D5 | Execution-mode space | Closed; enum stays in core; plugins supply orchestrators for existing modes | Enables "install X" errors and typed gates. Open string-keyed modes deferred until needed. |
| D6 | OpenAI | Substrate → core library (always-on); driver → always-on built-in plugin, no special case | Substrate is shared infra (diamond-dep otherwise). Substrate *extraction into a named module* deferred to externalization (no in-tree payoff). |
| D7 | Temporal config | Schema stays typed in core; only implementation moves | Keeps static typing + `make tb`; config seam becomes a near-no-op. Generic third-party config namespace deferred. |
| D8 | SPI | Two published, versioned SPIs sized to measured imports; sanction `runtime_bridge.primitives.*`; widen to cover Mistral's real needs | A designed surface beats an honor rule that's already breached. |
| D9 | Versioning | `PLUGIN_API_VERSION: int`, plugins declare `targets_api`, mismatch fails loud | Make breaks visible (repo policy). Semver ranges deferred. |
| D10 | Packaging | In-tree-but-registerable default; externalize Temporal; flip Mistral to discovery; vendor inference dists deferred | Most value from the seam alone; split only where cadence/weight justifies. |

---

## 14. Test strategy

Each rollout phase lands green; tests are written with the change (red-green), not after. Most of the suite already exists (the integrations work today) — the new tests target the *seam* and the *invariants the seam must not break*. Trivial pass-throughs (a factory that just wraps a client) are not worth bespoke tests; the contract and the invariants are.

### 14.1 Contract conformance (core, protocol-level)

Kept in core so any plugin — built-in or external — can be checked against the contract:

- every `BUILTIN_PLUGINS` entry satisfies the `PipelexPlugin` protocol and declares a compatible `targets_api`;
- a plugin declaring an incompatible `targets_api` fails loud at load (named);
- duplicate `(family, sdk)` / duplicate `execution_mode` / double-claimed hub slot each raise, naming both contributors (§5.3 conflict policy);
- a discovered entry point that fails to import or whose `register` raises is surfaced with context, not skipped (§5.5).

### 14.2 Registry round-trip and DIRECT parity

- each worker family: register → `lookup(family, sdk)` → `make_worker` returns the right `*WorkerAbstract`, for a representative built-in;
- the bridge dispatches by `execution_mode` to a fake registered orchestrator (proves the lookup replaced the `match` with no behavior change);
- `DIRECT` routed through the registry produces byte-identical output to the pre-refactor `_run_direct` for a sample pipe.

### 14.3 Correctness invariants (the silent-bug guards)

- **Import-light boot** (§6.5): booting with the built-ins registered imports no optional SDK — assert `anthropic`, `mistralai`, `google.genai`, `boto3`, … are absent from `sys.modules` after boot. This is the guard against a careless refactor regressing lazy-load.
- **DIRECT router scoping** (§8.1): a `DIRECT` run inside a Temporal-enabled hub keeps nested controller sub-pipes in-process (they resolve the scoped `PipeRouter`, not the Temporal default). Pins the one correctness landmine in the orchestrator extraction.
- **Core defaults unconditional** (§5.3): boot in a stripped environment still resolves `DIRECT` and every core-dep backend (extends the existing `make tb` boot test).

### 14.4 Error parity

A representative missing-extra path (e.g. an Anthropic model with the `anthropic` extra absent) raises the *same* friendly `MissingDependencyError` text — lib + extra + alternative — proving the message survived the move into `make_worker` (preserves the security-perimeter habit of asserting the user-facing message, not just the type).

### 14.5 Temporal: green in-tree before extraction

The full Temporal suite (unit + integration, with the `temporal` marker and `--temporal-server`) must pass with Temporal **wired through the seam but still in-repo** before the package is lifted. Extraction then re-runs the relocated suite against the published base. This is the checkpoint that proves the seam before the packaging move.

## 15. Risks and mitigations

- **Registration timing** — anything used before it's registered breaks. Mitigation: single ordered discovery point after config, before first use; core defaults unconditional; a boot test (`make tb`) that asserts `DIRECT` + every core-dep backend resolve.
- **Silently dropping a core backend** — a misconfigured env must not lose openai/gateway/etc. Mitigation: built-in static list (not entry-point-discovered), registered unconditionally; conformance test asserting presence.
- **Over-fitting the contract to Temporal** — Temporal exercises every hook; tempting to model the protocol on it. Mitigation: design the registrar against *both* Temporal (heaviest) and Mistral (per-call only); Mistral is the standing counter-example.
- **SPI under-sizing** — if the orchestrator SPI omits something Mistral genuinely needs, the boundary stays breached. Mitigation: size it to the *measured* import set (§9.2), not a guess; treat any out-of-SPI import as a tracked design bug.
- **Cross-plugin coupling on extraction** — `pipelex-mistralai-workflows`'s `temporal` extra imports `pipelex.temporal.*`; extracting Temporal to `pipelex-temporal` breaks those imports. Mitigation: in the Temporal-extraction phase, repoint Mistral's temporal extra/imports from `pipelex[temporal]` / `pipelex.temporal.*` to `pipelex-temporal`; this is the known downstream-consumer breakage already tracked.
- **Error-quality regression** — moving the `find_spec` guard into factories could dull today's helpful messages. Mitigation: move the messages verbatim; a test asserts the friendly text (lib + extra + alternative) for a representative missing extra.

---

## 16. Rollout shape (detail belongs to the plan)

A natural ordering, each step provable by a green suite before the next. The implementation plan expands these into phases with checkpoints.

1. **Rename** (D1) — `Plugin`/`PluginManager`/`PluginSdkRegistry` → new names. Pure rename, unblocks clear vocabulary.
2. **The seam** — `PipelexPlugin` protocol, `PluginRegistrar`, the three registry shapes, discovery (static + entry points), version check, fail-loud. No behavior change.
3. **Inference through the seam** (in-tree) — `InferenceBackendRegistry` + `InferenceBackendFactory`; every `match` arm (OpenAI driver included, no special case) becomes a registration + factory; built-in drivers in the static list. Suite green with all backends in-repo but selected via the registry.
4. **Orchestrators through the seam** (in-tree) — `OrchestratorRegistry` + exclusive hub slots; `DIRECT` registered in core; the bridge `match` collapses to a lookup; Temporal's boot/teardown/CLI/modes move behind its plugin (still in-repo); Mistral's hard import becomes entry-point discovery. Publish the orchestrator SPI; resolve Mistral's boundary against it.
5. **Externalize Temporal** — move `pipelex/temporal/` + tests + marker + CLI option to `pipelex-temporal`; entry point; flip downstream pins; repoint Mistral's temporal extra. Keep config schema in core.

Vendor inference dists and the OpenAI-substrate extraction are out of this rollout — they happen if/when a specific externalization is justified.

**Cross-cutting deliverables.** The published SPI reference (module/symbol list with import examples, §9) lands with the phase that publishes each SPI. A plugin-authoring guide and a minimal example plugin — the "hello world" for plugin authors (§5.6) — land once the seam exists (after the inference phase, since a backend plugin is the simplest example) and are kept current as orchestrators land. These are deliverables, not follow-ups.

---

## 17. Open questions for the plan

- **SPI delivery shape** (§9.3): documented module/symbol list only, or also a thin curated import surface? Resolve without violating the no-re-export rule.
- **Registrar config access timing**: confirm the single `register` call point sees a fully-resolved `ConfigRoot` for every plugin's gating needs (Temporal's `is_enabled`, and the `temporal_enabled` boot override in `Pipelex.make`).
- **`InferenceBackendFactory` granularity**: one factory object per `(family, sdk)`, or one per vendor that switches on family internally? (Leaning per-`(family, sdk)` for uniform entries — confirm against the messier arms like huggingface's provider-literal handling.)
- **Where the committed docs land** (§5.6, §16): the plugin-authoring guide + SPI reference are deliverables — the open question is placement (a dedicated user-facing `docs/.../plugins/` section vs `docs/under-the-hood/`), given the authoring guide is user-facing while the seam internals are under-the-hood.
