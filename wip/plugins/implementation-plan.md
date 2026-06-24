# Pipelex plugin system — implementation plan

**Status:** plan (proposed, not started) — reviewed via `/plan-eng-review` + codex outside voice; decisions D1–D6 locked (see below).
**Built from:** [`design.md`](design.md) — the single decided design. This plan expands design §16's rollout into executable phases with grounded `file:line` references, per-phase red-green tests, and checkpoints, and resolves the §17 open questions. Read `design.md` first; this is the *how*. Where this plan diverges from the design (deferred slot-claim thunks; a fifth seam; config relocation), the divergence is a review finding folded in, called out inline.

## 0. Orientation

**Why now (not speculative generality).** Both families are already ~80–90% decoupled; this inverts the *last* coupling. The justification is present pain, not hypothetical third-party authors: `pipelex-mistralai-workflows` is *already* an external repo whose native tier *already* breaches its declared import boundary (it reaches into `pipelex.hub`, `pipe_run`, `core`, `graph`, `tracing`), held together by a pinned-rev coupling — the orchestrator SPI is the real fix. And Temporal's heavy SDK + independent release cadence + the fact that downstream (`pipelex-worker`, `pipelex-api-hosted`) *already* pin it separately mean externalization pays for itself. The third-party-author story is a bonus the seam enables for free.

**The seams, located.** The design names four inference seams; the review found a fifth (`model_lists.py`). Core still names integrations at each:

| Seam | File | What it does today |
|---|---|---|
| Inference dispatch (×4) | `cogt/{llm,img_gen,extract,search}/*_worker_factory.py` | `match plugin.sdk:` → per-arm lazy import + `find_spec` guard + SDK-client cache + build worker |
| **Model listing (the 5th seam)** | `cogt/model_backends/model_lists.py:58` | `match sdk:` → hardcoded imports of `pipelex.plugins.{openai,anthropic,…}.*_list` (the `list-models` CLI path) — **missed by the design; codex finding** |
| Orchestrator dispatch | `runtime_bridge/bridge.py:147-158` | `match execution_mode:` → hard-imports Mistral (`:414`), lazy-imports Temporal; per-mode install messages at `:399/:417` |
| Boot/teardown hub swap | `pipelex.py:377-479` | four `if get_config().temporal.is_enabled:` blocks + inlined teardown; explicit `content_generator`/`pipe_router` params override at `:376/:450` |
| Config | `system/configuration/configs.py:14,250` | the one hard import of `pipelex.temporal.config_temporal` |
| CLI | `cli/_cli.py:15,20,234,238` | two hard imports registering `worker` + `setup-temporal-namespace`; `PipelexCLI.list_commands` hardcodes order |
| Naming overload | `plugins/{plugin,plugin_manager,plugin_sdk_registry}.py`, `hub.py:289-293` | `Plugin` value object, `PluginManager`/`PluginSdkRegistry` cache, the `PluginManager2 is not initialized` artifact |

| Phase | Scope | PR |
|---|---|---|
| 0 — Rename | `pipelex` only | own PR |
| 1 — Seam + LLM family | `pipelex` only | own PR (merged per D2) |
| 2 — Remaining inference families | `pipelex` only | own PR(s) per family |
| 3 — Orchestrators through the seam | `pipelex` only | own PR |
| 4 — Invert model listing (5th seam) | `pipelex` only | own PR (D6) |
| 5 — Externalize Temporal | cross-repo | separate effort, gated |

## Decisions locked in this review

| # | Decision | Choice |
|---|---|---|
| D1 | Inference backend factory shape | **Typed callable** (`MakeWorkerFn` TypeAlias), not a single-method `Protocol` object — kills ~30 one-method classes |
| D2 | Phase 1 PR boundary | **Merge** the seam machinery with the LLM family so the contract meets a real backend before it locks |
| D3 | Plugin CLI command harvesting | **Run the pure `build_registrar` at CLI-build** (after loading config); same function runs again at boot |
| D4 | `SdkClientManager` wrapper | **Keep as pure rename**; collapse into the registry deferred to a P3 follow-up commit |
| D5 | Hub slot claims | **Deferred thunks** — `claim_*(factory: Callable[[], Impl])`, invoked only at the setup apply-point, so `register` stays import-light (codex finding) |
| D6 | The 5th seam (`model_lists.py`) | **Invert it too**, as a follow-on phase, with a model-listing capability on the inference contract (codex finding) |
| D7 | Plugin control surface | Discovery is the source of truth for *presence*; add `pipelex plugins list` (observability) + a narrow `plugins.disabled` denylist escape hatch; **no** redundant allowlist (model config already gates inference) |

## Plugin enablement model

No central "plugins on/off" list exists, by design. Enablement is two separate things:

- **Presence (is the plugin discovered?) — not config.** A plugin is present iff it is in the static `BUILTIN_PLUGINS` list (core) or is an installed dist declaring the `pipelex.plugins` entry point. Installing enables presence; uninstalling removes it. Zero config. `build_registrar` walks both sources at boot and calls each plugin's `register(registrar)` — that call *is* the plug.
- **Activation (is its contribution used?) — decomposed by registry shape, never a generic flag:**
    - *Inference backends* activate by **data**: a model in the backend config names the `sdk`. The plugin registers its `(family, sdk)` entry unconditionally and import-light; it runs only when a model selects it. The model/backend config (`get_models_manager()`) is the de-facto central enable surface for inference — a per-plugin toggle would duplicate it and drift.
    - *Orchestrators, per-call* select by `execution_mode` per run.
    - *Orchestrators, boot-global* are claimed only when the plugin's own config slice says so. **`temporal.is_enabled` is not a generic "Temporal plugin on" flag** — it means "boot *this process* as a Temporal-default runtime" (swap the hub content-generator/router/run to the Temporal ones). A worker process sets it; a runner does not. The name misleads; treat it as a per-process runtime-mode gate, not plugin enablement. Renaming it is out of scope (touches the live config) but flagged.

**Control surface (D7) — discovery stays the source of truth for presence; on top of it:**

- `pipelex plugins list` — a core (not plugin-contributed) command: prints every discovered plugin (built-in vs external), what each registered (backends / modes / slots / CLI), and whether it's denylisted. The answer to "what's plugged in?"
- `plugins.disabled: list[str]` — a denylist escape hatch in a core-owned `plugins` config section. A discovered plugin whose `name` is listed is skipped in `build_registrar`, **with a log line (never silent)**, without uninstalling it — for testing and quarantining a misbehaving external. A flat list of *names*, **not** the deferred *generic per-plugin typed-config namespace* (design §10), which stays out of scope.
- **The denylist cannot disable a core-unconditional plugin** (the DIRECT orchestrator, or a core-dependency backend: openai/gateway/portkey/pypdfium2/azure_rest). Listing one is a startup error — you cannot boot without DIRECT — preserving design §5.3's "core defaults unconditional" invariant.

---

## Phase 0 — Rename (free the word "plugin")

**Goal.** Kill the three-way "plugin" overload so the new vocabulary is unambiguous. Pure rename, no behavior change.

**Renames** (class → file):

- `Plugin` (`plugins/plugin.py`) → `ModelHandle` (`plugins/model_handle.py`). A backend *selector* (`sdk` + `backend` + `variant` + `sdk_handle`), not a plugin. Keep `make_for_inference_model`.
- `PluginManager` (`plugins/plugin_manager.py`) → `SdkClientManager` (`plugins/sdk_client_manager.py`).
- `PluginSdkRegistry` (`plugins/plugin_sdk_registry.py`) → `SdkClientRegistry` (`plugins/sdk_client_registry.py`). Rename `get_sdk_instance`/`set_sdk_instance` → `get`/`set` (the DRY `get_or_create` lands in Phase 1, not here).
- `PluginFactoryAbstract` (`plugins/plugin_factory_abstract.py`, the `make_extras` helper — *unrelated* to the new system) → `BackendExtrasFactory` (`plugins/backend_extras_factory.py`). Name-hygiene; it collides with the new contract vocabulary.

**Blast radius is bigger than "the four factories" (codex C11).** `Plugin` / `plugin_sdk_registry` is imported across the in-tree adapter modules — `openai`, `bedrock`, `anthropic`, `gateway`, `portkey` list+factory modules, plus `search_worker_factory.py:4` (which uses the *correct* `plugins.plugin` path while `llm/img_gen/extract` import from the *wrong* `plugins.plugin_sdk_registry` path). Grep `import Plugin\b` and `plugin_sdk_registry` across `pipelex/` before starting; the rename touches more than the dispatch sites. The wrong-path imports get fixed for free here.

- `hub.py`: `get_plugin_manager`/`set_plugin_manager` → `get_sdk_client_manager`/`set_sdk_client_manager`; **fix the `"PluginManager2 is not initialized"` message** (`hub.py:291`) to `"SdkClientManager is not initialized"`.
- `pipelex.py`: setup/teardown call sites.

**D4 — keep this a pure rename.** The `SdkClientManager` post-rename is still a thin wrapper holding one `SdkClientRegistry`. *Collapsing* it (hub holds the registry directly) is a separate structural change captured as a **P3 TODO** (own commit), not bundled here — rename and restructure don't mix.

**Tests.** No new tests; existing suite + `make tb` (boot/config) stay green.

**Checkpoint 0.** Green suite, clean vocabulary, `PluginManager2` artifact gone, wrong-path `Plugin` imports fixed. Standalone PR.

---

## Phase 1 — Seam machinery + LLM family (merged, per D2)

**Goal.** Build the discovery + contract + registry machinery *and* migrate the LLM family through it in one PR, so the contract is proven against a real, messy family before it locks. No behavior change.

**New modules** (all import-light — must not import any backend SDK or `temporalio`):

- `plugins/contract.py` — `PipelexPlugin` (`@runtime_checkable Protocol`: `name: str`, `targets_api: int`, `register(self, registrar) -> None`) and `PLUGIN_API_VERSION: int = 1`. **Contract invariant — `register` is side-effect-free:** it may *only* call registrar methods (no hub touch, no I/O, no client construction). This is what makes `build_registrar` safely repeatable (D3 runs it at CLI-build *and* boot).
- `plugins/registrar.py` — `PluginRegistrar`, the accumulator. Holds the inference registry, orchestrator registry, **deferred** hub-slot-claim thunks, CLI-command list, teardown-callback list, and a read-only `config: ConfigRoot`. Menu methods:
  - `add_inference_backend(*, family, sdk, make_worker: MakeWorkerFn)` — D1: a callable, not a factory object.
  - `add_orchestrator(*, mode, orchestrator)`.
  - `claim_content_generator | pipe_router | pipe_run | task_manager(factory: Callable[[], Impl])` — **D5: a thunk, not an instance.** `register` never constructs the impl, so it never imports `temporalio`.
  - `add_cli_command(*, name, help, command)`, `add_teardown(callback)`.
- `plugins/inference_backend_registry.py` — `InferenceFamily` (`StrEnum`: `LLM`/`IMG_GEN`/`EXTRACT`/`SEARCH`), `MakeWorkerFn` (TypeAlias for the callable signature), `InferenceBackendRegistry` keyed by `(family, sdk)`.
- `plugins/orchestrator_registry.py` — `OrchestratorProtocol` (`async def run(self, *, pipe_job, delivery_assignment) -> PipelexPipeRunOutput`), `OrchestratorRegistry` keyed by `PipelexExecutionMode`.
- `plugins/discovery.py` — `build_registrar(*, config) -> PluginRegistrar`: a **pure function** iterating `BUILTIN_PLUGINS` + `importlib.metadata.entry_points(group="pipelex.plugins")`, running the version check per plugin, calling `plugin.register(registrar)` (skipping any plugin whose `name` is in `config.plugins.disabled`, logged; raising if a core-unconditional plugin is denylisted — D7), applying fail-loud. Pure ⇒ safely called at CLI-build and at boot.
- `plugins/builtins.py` — `BUILTIN_PLUGINS`. Phase 1 fills it with the LLM drivers.
- `plugins/exceptions.py` — `PluginApiVersionMismatchError`, `DuplicateInferenceBackendError`, `DuplicateOrchestratorError`, `HubSlotAlreadyClaimedError`, `BrokenPluginError`. (`MissingOrchestratorError` lives in `runtime_bridge/exceptions.py` — near its domain — replacing the two old typed errors; see Phase 3.)

The `MakeWorkerFn` signature (D1 — callable, uniform across families):

```python
MakeWorkerFn = Callable[..., InferenceWorkerAbstract]
# called as: make_worker(*, inference_model, backend, sdk_clients, reporting_delegate)
```

**DRY the two repeated blocks** (design §6.2):

- **Client cache** — `SdkClientRegistry.get_or_create(*, handle, build)` replaces the `get_sdk_instance(...) or set_sdk_instance(...)` dance in every arm.
- **Extra guard** — `require_sdk(*, spec, extra, msg)` (raises `MissingDependencyError` if `find_spec(spec) is None`) replaces the repeated guard, moved **into** `make_worker` so a missing extra fails at use, not boot.

**LLM family migration.** `llm_worker_factory.py`'s `match` collapses to `get_inference_backend_registry().lookup(family=LLM, sdk=model_handle.sdk)(...)`. Each LLM driver plugin's `register` calls `add_inference_backend(family=LLM, sdk="anthropic", make_worker=<closure>)`. A registry *miss* raises a distinct "backend `<sdk>` not registered; is its plugin installed?" error.

**Boot wiring.** In `Pipelex.setup()`, after config is fully resolved (incl. the `temporal_enabled` override at `pipelex.py:193-196`) and before the hub setup points, call `build_registrar(config=get_config())`. Store the two keyed registries on the hub (`set_inference_backend_registry` / `set_orchestrator_registry`). Hold the slot-claim thunks, CLI commands, teardown callbacks for their apply-points.

**Conflict & version policy** (fail loud): duplicate `(family, sdk)` / duplicate `execution_mode` / double-claimed slot each raise naming both contributors; `targets_api != PLUGIN_API_VERSION` → `PluginApiVersionMismatchError` with the remedy; a broken entry point → `BrokenPluginError` with context (the one sanctioned `except Exception` site — wraps unbounded third-party plugin code; annotate it).

**Control-surface deliverables (D7).** Add a core-owned `plugins: PluginsConfig` section (`disabled: list[str]`, default `[]` in `pipelex.toml` and `.pipelex/pipelex.toml` — never a class-def default) to `configs.py`; apply the denylist in `build_registrar` (skip + log; error on a core-unconditional name). Add the core `pipelex plugins list` command (lists discovered plugins, their contributions, and denylist state). See the enablement-model section above.

**Tests:**

- Contract conformance (synthetic plugins): protocol satisfaction; `targets_api` mismatch fails loud; duplicate `(family, sdk)` / duplicate mode / double-claimed slot each raise naming both; broken entry point → `BrokenPluginError`; **`build_registrar` idempotent** (two calls, no side effect — pins the side-effect-free invariant).
- Denylist (D7): a discovered non-core plugin named in `plugins.disabled` is skipped and logged; denylisting a core-unconditional plugin (e.g. the OpenAI driver or DIRECT) raises at startup; `pipelex plugins list` shows discovered built-ins + (synthetic) externals with contributions and denylist state.
- **Import-light boot via subprocess + import-blocker (codex C12, replaces the weak `sys.modules` check):** spawn a subprocess with a `sys.meta_path` finder that *raises* on `anthropic`, `mistralai`, `google.genai`, `boto3`, `fal_client`, … then boot with built-ins registered and assert no raise. A `sys.modules`-absence assertion in-process is noisy (prior imports leak); the import-blocker is deterministic.
- Registry round-trip (LLM): register → `lookup(LLM, sdk)` → returns the right `LLMWorkerAbstract`.
- Error parity: an Anthropic model with the `anthropic` extra absent raises the *same* `MissingDependencyError` text (lib + extra + alternative).

**Checkpoint 1.** Seam exists, proven against the real LLM family; import-light enforced by the subprocess guard; conflict/version policy tested. The contract is now locked against a real consumer. Mergeable.

---

## Phase 2 — Remaining inference families (ImgGen, Extract, Search)

**Goal.** Migrate the other three families onto the proven contract. One family per sub-PR.

- **ImgGen.** Collapse the `match`. **Fix the pre-existing huggingface bug (codex C10):** `img_gen_worker_factory.py:64` imports `huggingface_hub` with **no `find_spec` guard** — unlike every other arm, a missing extra raises a raw `ImportError` instead of the friendly `MissingDependencyError`. Add the `require_sdk(spec="huggingface_hub", extra="huggingface", …)` guard during migration (flag-and-fix per repo policy). The provider-literal handling (`model_handle.variant` → provider) lives inside the closure. The substrate-reuse workers (`blackboxai`/`gateway_completions`/`openrouter` → `OpenAICompletionsImgGenWorker` with a per-vendor completions factory) become closures capturing that factory.
- **Extract.** Collapse the `match`. Stateless arms (`pypdfium2`, `linkup_fetch`) skip `get_or_create`.
- **Search — normalize the call surface (codex C9).** `search_worker_factory.py` takes **no `reporting_delegate` param** and pulls `get_report_delegate()` from the hub (`:31`, `:41`), and `make_search_worker` itself omits it. The uniform `MakeWorkerFn` passes `reporting_delegate` explicitly. Resolution: normalize `make_search_worker` and its callers to accept `reporting_delegate` (removing search's hidden hub coupling — a strict improvement), so search fits the uniform signature. This is a small call-surface change, not a special case.

Add each migrated driver to `BUILTIN_PLUGINS`. OpenAI is an always-on built-in driver, no privileged arm (design D6-design); the OpenAI-compat *substrate* stays an in-tree library the gateway/portkey/openrouter/blackboxai closures import — substrate *extraction into a named module* is deferred.

**Tests:** registry round-trip per family; the import-light subprocess guard now covers all optional SDKs; **huggingface error-parity** (missing `huggingface` extra now raises `MissingDependencyError`, proving the bug fix); a **cross-family vendor** test (e.g. `mistral` registers into both LLM and Extract from one `register`).

**Cross-cutting deliverable:** the **inference SPI reference** (design §9.1) + the **plugin-authoring guide and minimal example backend plugin** land here (a backend plugin is the simplest example). Placement: authoring guide + SPI reference in a user-facing `docs/.../plugins/` Guide section; seam internals in `docs/under-the-hood/`; the example as runnable in-repo code.

**Checkpoint 2.** All four `match` worker-factory statements gone; every backend via the registry while in-repo; the huggingface guard bug fixed; search's hub coupling removed; SPI + authoring guide shipped. **Natural session handoff** — inference side done, orchestrators open next.

---

## Phase 3 — Orchestrators through the seam (in-tree)

**Goal.** Collapse the bridge `match` and the four `temporal.is_enabled` boot blocks into registry/slot lookups; move Temporal's modes/CLI/boot-swap/teardown behind its (still-in-repo) plugin; flip Mistral's hard import to discovery; publish the orchestrator SPI. No behavior change.

**Extract the orchestrators** (verbatim bodies):

- `DirectOrchestrator.run` — from `_run_direct` (`bridge.py:270-294`). **Correctness landmine (design §8.1): keep `with scoped_pipe_router(PipeRouter())` verbatim** — dropping it leaks DIRECT-mode nested sub-pipes to Temporal inside a Temporal worker. Registered in core, always-on.
- `TemporalBlockingOrchestrator` / `TemporalFireAndForgetOrchestrator` — from `_run_temporal_*` (`:297-355`), keeping the `WorkflowExecutionError` catch and `make_workflow_id` recompute.
- `MistralWorkflowsOrchestrator` — **authored in the `pipelex-mistralai-workflows` repo**, not here.

**The bridge collapses** (design §8.1) to a registry lookup. After it, `bridge.py` names no integration.

**Preserve per-mode error quality (codex C7 — a generic hint is a regression).** Today `bridge.py:399/:417` carry exact, mode-specific install messages ("install `pipelex[temporal]`" vs "install `pipelex-mistralai-workflows`"). The registry-miss path must reproduce *those* messages, not a single generic hint. `MissingOrchestratorError` takes the `mode` and maps it to its exact message via the `PipelexExecutionMode.requires_*` properties (the typed source of truth for which mode needs what). One message per mode, preserved verbatim.

**The Temporal plugin** (`TemporalOrchestrator`). Its `register`:

- **always** `add_orchestrator(TEMPORAL_BLOCKING|TEMPORAL_FIRE_AND_FORGET, …)` and `add_cli_command("worker"|"setup-temporal-namespace", …)`;
- **if `config.temporal.is_enabled`**: `claim_content_generator(factory)`, `claim_pipe_router(factory)`, `claim_pipe_run(factory)`, `claim_task_manager(factory)`, `add_teardown(...)` — **D5: each `claim_*` is handed a thunk** (e.g. `claim_content_generator(lambda: ContentGeneratorInWorkflowFactory.make_content_generator_in_workflow())`), so `register` never imports `temporalio`. The thunk runs at the setup apply-point.

**Boot/teardown collapse with explicit injection precedence (codex C8).** The four `if get_config().temporal.is_enabled:` blocks (`pipelex.py:377-466`) become, at each existing ordered point (content generator → task manager → router → run): **explicit `setup()` param (test/user injection at `:376/:450`) > plugin slot-claim thunk > core default.** The slot claim must *not* silently override an explicit injection — pin this precedence in a test. The inlined teardown (`:471-479`) becomes a registered teardown callback run LIFO.

**CLI collapse (codex C4 + D3).** The two hard imports in `_cli.py:15,20,234,238` become plugin-contributed commands. `PipelexCLI.list_commands` (`:32`, which hardcodes command order) is reworked to merge core commands with `registrar.cli_commands` deterministically (stable order, clean `--help`, unknown-command behavior intact). Per D3, the CLI entry point loads config then runs the pure `build_registrar` once to harvest `registrar.cli_commands`; D5's thunks mean this harvest never constructs a Temporal impl even when `temporal.is_enabled`. **Spike this first in Phase 3** — it's the one genuinely novel integration point.

**Mistral → entry-point discovery** (this repo's side). Remove the `_run_mistral_native` hard import (`bridge.py:414`). Uninstalled (CI default) → `MISTRAL_NATIVE` absent → `MissingOrchestratorError` with the exact Mistral message. The real plugin (entry point + orchestrator re-pointed at the SPI) is a `pipelex-mistralai-workflows` change. pipelex's suite proves dispatch with a *fake* registered orchestrator.

**Publish the orchestrator SPI** (design §9.2, sized to Mistral's *measured* imports): `runtime_bridge.*` incl. `runtime_bridge.primitives.*`; the execution protocols; the boundary/core payload types; library-crate access + hub scoping; the tracing hooks. Documented module/symbol list. Mistral's boundary resolves against it.

**Tests:** bridge dispatch by mode (fake orchestrator); **per-mode error parity** (each missing mode → its exact message — C7); DIRECT router scoping (the landmine); DIRECT parity (byte-identical); **injection-precedence** (explicit param wins over a slot claim — C8); boot-via-slots (stripped env resolves DIRECT + core backends; temporal-enabled resolves the four slots to Temporal impls via thunks); teardown LIFO order; **CLI-command contribution** (`worker` appears in `--help` when the plugin is discoverable, absent otherwise — pins D3); **full Temporal suite green in-tree** (§14.5 — the extraction gate; Phase 5 does not start until this is green).

**Checkpoint 3.** Bridge + boot/teardown + CLI name no integration; Temporal fully behind its plugin in-repo (import-light preserved via thunks); per-mode errors preserved; injection precedence pinned; Mistral via discovery; orchestrator SPI published; Temporal suite green through the seam. **The** checkpoint before externalization.

---

## Phase 4 — Invert model listing (the 5th seam, per D6)

**Goal.** Close the goal: `model_lists.py:58`'s `match sdk:` (the `list-models` CLI path) still hardcodes `pipelex.plugins.{openai,anthropic,mistral,google,bedrock}.*_list` imports. Invert it onto the inference contract so core names no integration *anywhere*.

- Add a **model-listing capability** to the inference plugin contract: `add_model_lister(*, sdk, lister: ListModelsFn)` (a callable mirroring `MakeWorkerFn` — import-light, lazy). A backend plugin that lists models registers its lister alongside its worker factory.
- `ModelLister.list_models` (`model_lists.py`) collapses to a registry lookup keyed by `sdk`; a miss → the same friendly "is its plugin installed?" guidance. The `find_spec` guards (already present in this file's arms) move into each lister.
- The contract grows by one optional method — backends that don't support listing simply don't register a lister (progressive disclosure preserved).

**Tests:** round-trip (a registered lister is invoked for its `sdk`); a backend with no lister yields the friendly miss; import-light subprocess guard still green (listers are lazy).

**Checkpoint 4.** `model_lists.py` names no integration; "core names no integration by import or string" holds without an asterisk.

---

## Phase 5 — Externalize Temporal → `pipelex-temporal` (cross-repo, gated on Checkpoint 3)

**Goal.** Lift `pipelex/temporal/` into a separate dist. A *packaging* move — but only after a prerequisite the design missed.

**Step 0 — relocate the Temporal config schema to a core-owned module (codex C6 — the design's D7 is self-contradictory as written).** `config_temporal.py` currently *lives at* `pipelex.temporal.config_temporal` and imports `pipelex.temporal.exceptions` (`:10`: `TemporalConfigError`, `WorkerTaskQueueUnknownError`). "Keep config in core, move `pipelex/temporal/` out" is impossible while the schema sits under the `pipelex.temporal` namespace. Relocate the schema **and the specific exceptions it needs** to a core-owned module outside `pipelex.temporal` (e.g. `pipelex/system/configuration/config_temporal.py` + the two exceptions into a core `exceptions.py`). Update `configs.py:14`. The `if TYPE_CHECKING: … RetryPolicy = Any` placeholder keeps it importable without `temporalio`. This step is low-risk and could be pulled into Phase 3; it is the true prerequisite that makes the rest a packaging move. `make tb` stays meaningful.

**Then:**

- Move `pipelex/temporal/` (impl) + `temporal_plugin.py` + tests + the `temporal` marker + the `--temporal-server` conftest option into `pipelex-temporal`; declare `[project.entry-points."pipelex.plugins"]`.
- Protocol-level conformance tests stay in core; Temporal's behavioral suite travels.
- **Flip downstream pins** (cross-repo blast radius): `pipelex-worker`, `pipelex-api-hosted` from `pipelex[temporal]==X` → `pipelex-temporal==Y`.
- **Repoint `pipelex-mistralai-workflows`** (design §15): its `temporal` extra + `pipelex.temporal.*` imports → `pipelex-temporal`.

**Tests.** Re-run the relocated Temporal suite against the published `pipelex`; run downstream consumers' suites against the new pins before publishing.

**Checkpoint 5.** Temporal is an external plugin; core has no `temporal` extra; downstream pins flipped; consumer suites green.

> Vendor inference dists and OpenAI-substrate extraction are **out of this rollout** (design §6.6, §11) — one-line moves if/when justified.

---

## Resolved open questions (design §17)

- **SPI delivery shape →** documented module/symbol list only, no curated re-export surface (the repo bans `__init__.py` re-exports). The version marker `PLUGIN_API_VERSION` lives in `plugins/contract.py`.
- **Registrar config-access timing →** `build_registrar` runs after config resolution (incl. the `temporal_enabled` override) and before the hub-slot apply-points; every `register` sees a resolved `ConfigRoot`. The CLI-build second call is safe because D5's thunks make slot-claiming import-free and side-effect-free.
- **Factory granularity →** one **callable** per `(family, sdk)` (D1).
- **Where the committed docs land →** authoring guide + SPI reference in a user-facing `docs/.../plugins/` Guide section; seam internals in `docs/under-the-hood/`; minimal example as runnable in-repo code.

## NOT in scope (considered, deferred)

- Third-party-defined execution modes (open string-keyed space) — design D5; enum stays closed.
- Generic per-plugin typed-config namespace — design D7; Temporal config stays typed in core.
- Deliberately *overriding* a built-in (a third party replacing core's OpenAI driver) — design §5.3.
- Per-SPI versions / semver-range matching — design §5.4; single coarse `int`.
- Vendor inference dists + OpenAI-substrate extraction into a named module — design §6.4/§6.6/§11.
- **Collapsing `SdkClientManager` into `SdkClientRegistry`** — P3 follow-up commit after Phase 0 (D4), not bundled into the rename.
- Distribution/CI for `pipelex-temporal` — part of Phase 5's cross-repo effort, not Phases 0–4.

## What already exists (reused, not rebuilt)

The plan inverts the *last* coupling; it reuses, not rebuilds: the lazy-import pattern in every `match` arm; the optional extras (`pipelex[anthropic|temporal|…]`); the `*WorkerAbstract` hierarchy (`cogt/inference/inference_worker_abstract.py` + the four family abstracts); the `SdkClientRegistry` client cache (renamed); the `PipelexExecutionMode` enum + `requires_*` properties; the hub singletons + `scoped_pipe_router` ContextVar scoping; the `Temporal` config placeholder (`RetryPolicy = Any`). The seam + registries are the only genuinely new machinery; everything downstream of a lookup is existing code.

## Failure modes (new codepaths)

| Codepath | Realistic failure | Test? | Error handling? | User sees |
|---|---|---|---|---|
| `build_registrar` discovery | a broken external entry point | yes (conformance) | `BrokenPluginError` w/ context | clear, named |
| inference lookup | backend not registered (plugin absent) | yes (round-trip miss) | distinct "not registered" error | clear |
| `make_worker` closure | missing extra (incl. the fixed hf arm) | yes (error parity) | `MissingDependencyError` (lib+extra+alt) | clear, friendly |
| `register` at CLI-build | importing `temporalio` at CLI startup | yes (import-light subprocess + CLI-contribution) | D5 thunks prevent it | n/a (prevented) |
| DIRECT inside Temporal worker | nested sub-pipes leak to Temporal | yes (router-scoping) | `scoped_pipe_router` preserved | n/a (prevented) |
| slot claim vs explicit injection | slot silently overrides test/user inject | yes (injection-precedence) | explicit param wins | n/a (prevented) |
| orchestrator miss | wrong/absent mode | yes (per-mode parity) | per-mode `MissingOrchestratorError` | exact install message |

No critical gaps (no failure mode is simultaneously untested, unhandled, and silent).

## Worktree parallelization

| Step | Modules | Depends on |
|---|---|---|
| Phase 0 rename | `plugins/`, `hub.py`, `pipelex.py`, all adapter modules | — |
| Phase 1 seam+LLM | `plugins/`, `cogt/llm/` | Phase 0 |
| Phase 2 ImgGen / Extract / Search | `cogt/{img_gen,extract,search}/`, `plugins/<vendor>/` | Phase 1 (contract) |
| Phase 3 orchestrators | `runtime_bridge/`, `pipelex.py`, `cli/`, `temporal/` | Phase 1 |
| Phase 4 model_lists | `cogt/model_backends/`, `plugins/<vendor>/` | Phase 1 (contract) |

**Lanes after Phase 1 lands:** Phase 2's three families are independent of each other and of Phase 3/4 → `Lane A: ImgGen`, `Lane B: Extract`, `Lane C: Search`, `Lane D: Phase 3 orchestrators`, `Lane E: Phase 4 model_lists` can run in parallel worktrees. **Conflict flag:** Lanes A/B/C and E both touch `plugins/<vendor>/` modules (e.g. a vendor serving multiple families) — coordinate the per-vendor plugin object so two lanes don't both edit it. Phase 0 and Phase 1 are strictly sequential (everything depends on the rename then the contract).

## Execution risks

- **Phase 3 carries most risk** — bridge + boot + teardown + CLI at once, plus the DIRECT-router-scoping landmine and the per-mode-error and injection-precedence subtleties codex surfaced. Mitigation: verbatim orchestrator extraction; pin each subtlety with its own test; land the §14.5 Temporal-green checkpoint before externalizing.
- **CLI timing (D3) + thunks (D5)** are the novel integration point. Mitigation: spike first in Phase 3; the CLI-contribution test proves it.
- **Import-light regression** is invisible until profiled. Mitigation: the subprocess import-blocker guard (C12) lands with Phase 1.
- **Phase 5 is cross-repo** — the only phase that can break downstream deploys; gated, separate, with config relocation as its de-risking step-0.

## Sequencing summary

Phase 0 (rename) → Phase 1 (seam + LLM, merged) → Phase 2 (ImgGen/Extract/Search, parallel sub-PRs) → Phase 3 (orchestrators) → Phase 4 (model_lists) → **[gate: §14.5 green]** → Phase 5 (externalize Temporal, cross-repo). Phases 0–4 are independent PRs in `pipelex`; each lands green. Inference SPI + authoring guide ship with Phase 2; orchestrator SPI with Phase 3.

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | not run |
| Codex Review | outside voice | Independent 2nd opinion | 1 | issues_found | found 5th seam + import-light hole + Phase-4 config contradiction + hf bug — all folded |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | clean | 18 findings, 0 critical gaps, 0 unresolved |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | n/a (backend-only) |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | not run |

- **CODEX:** outside voice caught what the interactive review missed — the 5th seam (`model_lists.py`), the import-light-at-CLI-build hole (resolved via D5 deferred slot thunks), the Phase-5 config self-contradiction (resolved via core-owned config relocation), a pre-existing huggingface `find_spec` bug, and the per-mode-error / injection-precedence gaps. All folded into the plan.
- **CROSS-MODEL:** no standing tension — codex's findings were additive gaps, not disagreements with the review; all resolved by user decision (D5, D6) or clear fold.
- **VERDICT:** ENG CLEARED — ready to implement.

NO UNRESOLVED DECISIONS
