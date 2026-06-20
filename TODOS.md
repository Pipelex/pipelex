# Pipelex plugin system — implementation TODOS

**Branch:** `refactor/Plugins` (worktree `_plugins`) · **Status:** Phase 0 + Phase 1 complete (committed). Phase 2 (ImgGen / Extract / Search) code + tests + docs done, uncommitted. Next: commit Phase 2, then Phase 3 (orchestrators).

> **Delivery model for this branch.** Per the driving goal, all phases land on `refactor/Plugins` as **one commit per checkpoint** (not one PR per phase), and a **single PR to `dev`** opens once the tracker is done. Each phase's "PR: …" box below is satisfied by its checkpoint commit; the standalone-PR-per-phase wording in the original plan is superseded.

This is the **execution tracker**. The *why* and *how* live in [`wip/plugins/implementation-plan.md`](wip/plugins/implementation-plan.md) (the reviewed, decision-locked plan), built from [`wip/plugins/design.md`](wip/plugins/design.md) (the single decided design). **Read the implementation-plan before starting any phase** — this file tracks progress against it, it does not replace it. Background assessment: [`wip/plugins/README.md`](wip/plugins/README.md), plus the per-area notes (`inference-backends-as-plugins.md`, `orchestrators-as-plugins.md`, `temporal-as-plugin.md`).

> **How to use this file.** Tick boxes as you land work. **Do not skip a `🛑 CHECKPOINT`** — each one is a hard stop with three mandatory actions (verify · capture cold-start context · fan-out `/code-review`). The plan is one PR per phase; each phase lands green on its own.

---

## Cold-start primer (read this first if you're new to the session)

**Goal of the whole effort:** invert the *last* coupling between core and its optional integrations so **core names no integration — not by import, not by string — anywhere**. Two families ride one shared seam: inference *driver* plugins (the SDK `match` statements) and orchestrator *strategy* plugins (Temporal, Mistral).

**The seams to invert** (verified present; line numbers drift, locations hold):

| Seam | File | Today |
|---|---|---|
| Inference dispatch (×4) | `cogt/{llm,img_gen,extract,search}/*_worker_factory.py` | `match plugin.sdk:` → lazy import + `find_spec` guard + client cache + build worker |
| Model listing (5th seam) | `cogt/model_backends/model_lists.py` (`match sdk` ~`:58`) | hardcoded `pipelex.plugins.{openai,…}.*_list` imports (the `list-models` path) |
| Orchestrator dispatch | `runtime_bridge/bridge.py` (`match` ~`:147`, `_run_mistral_native` `:408`, `_run_direct` `:270`, `_run_temporal_*` `:297/:330`) | `match execution_mode:` → hard Mistral import + lazy Temporal + per-mode install messages |
| Boot/teardown hub swap | `pipelex.py` (~`:377-479`) | four `if get_config().temporal.is_enabled:` blocks + inlined teardown |
| Config | `system/configuration/configs.py:14` | the one hard `from pipelex.temporal.config_temporal import Temporal` |
| CLI | `cli/_cli.py:15,20` + `list_commands` | two hard imports register `worker` + `setup-temporal-namespace`; order hardcoded |
| Naming overload | `plugins/{plugin,plugin_manager,plugin_sdk_registry,plugin_factory_abstract}.py`, `hub.py` `"PluginManager2 is not initialized"` | three-way "plugin" overload to kill |

**Locked decisions (D1–D7)** — do not re-litigate, see plan for full text:

- **D1** — inference factory = a typed callable `MakeWorkerFn`, not a one-method Protocol object (kills ~30 classes).
- **D2** — Phase 1 PR = seam machinery **merged** with the LLM family (contract meets a real backend before locking).
- **D3** — plugin CLI commands harvested by running the **pure `build_registrar`** at CLI-build (after config load); same fn runs again at boot.
- **D4** — Phase 0 keeps `SdkClientManager` a **pure rename**; collapsing it into the registry is a **P3 follow-up commit**, not bundled.
- **D5** — hub slot claims are **deferred thunks** (`claim_*(factory: Callable[[], Impl])`), invoked only at the setup apply-point → `register` stays import-light (never imports `temporalio`).
- **D6** — the 5th seam (`model_lists.py`) is **inverted too**, as Phase 4, via a model-listing capability on the inference contract.
- **D7** — control surface: discovery is the source of truth for *presence*; add `pipelex plugins list` (observability) + a narrow `plugins.disabled` denylist; **no** redundant allowlist.

**Enablement model** (so you don't add a flag that shouldn't exist): *presence* = in `BUILTIN_PLUGINS` or an installed dist with the `pipelex.plugins` entry point (zero config). *Activation* is decomposed by registry shape — inference backends activate by **data** (a model names the `sdk`); orchestrators select per-call by `execution_mode`; boot-global orchestrators are claimed only when the plugin's own config slice says so (`temporal.is_enabled` = "boot *this process* as a Temporal runtime", a per-process gate, **not** a generic plugin on/off).

**Invariants that must survive every phase:**

- `register(registrar)` is **side-effect-free** — may only call registrar menu methods (no hub touch, no I/O, no client/SDK construction). This is what makes `build_registrar` safely repeatable (D3 runs it at CLI-build *and* boot).
- **Import-light boot** — booting with built-ins registered must not import any optional SDK (`anthropic`, `mistralai`, `google.genai`, `boto3`, `fal_client`, …) or `temporalio`. Enforced by the subprocess import-blocker guard (lands Phase 1).
- **Fail loud** — duplicate `(family, sdk)` / duplicate mode / double-claimed slot / version mismatch / broken entry point each raise a named, contextual error. A missing backend says "install X", never derefs `None`.

**Commands** (from `_plugins/CLAUDE.md`): `make agent-check` (lint/types — always after changes) · `make agent-test` (full suite, silent on success — at end of every phase) · `make tb` (boot/config sanity — fast, run after config or seam edits) · `make agent-test-debug` / `make atd` (when the suite hangs). Always use the venv: `.venv/bin/...`.

**PR boundaries:** Phase 0 · Phase 1 (merged seam+LLM) · Phase 2 (one sub-PR per family) · Phase 3 · Phase 4 — all `pipelex`-only, each lands green. Phase 5 is cross-repo, gated on Checkpoint 3.

---

## Phase 0 — Rename (free the word "plugin")

**Goal:** kill the three-way "plugin" overload. Pure rename, **no behavior change**. Own PR.

- [x] **Grep the blast radius first** (codex C11 — it's bigger than the four factories): `grep -rn 'import Plugin\b' pipelex/` and `grep -rn 'plugin_sdk_registry\|plugin_manager\|PluginManager\|PluginSdkRegistry\|PluginFactoryAbstract' pipelex/`. Note every adapter module (`openai`, `bedrock`, `anthropic`, `gateway`, `portkey` list+factory) and `search_worker_factory.py` (uses the *correct* `plugins.plugin` path while llm/img_gen/extract use the *wrong* `plugins.plugin_sdk_registry` path).
- [x] `Plugin` (`plugins/plugin.py`) → `ModelHandle` (`plugins/model_handle.py`). Keep `make_for_inference_model`. It's a backend *selector* (`sdk`+`backend`+`variant`+`sdk_handle`), not a plugin.
- [x] `PluginManager` (`plugins/plugin_manager.py`) → `SdkClientManager` (`plugins/sdk_client_manager.py`).
- [x] `PluginSdkRegistry` (`plugins/plugin_sdk_registry.py`) → `SdkClientRegistry` (`plugins/sdk_client_registry.py`). Rename `get_sdk_instance`/`set_sdk_instance` → `get`/`set` (the DRY `get_or_create` lands in Phase 1, **not here**).
- [x] `PluginFactoryAbstract` (`plugins/plugin_factory_abstract.py`, the `make_extras` helper — unrelated to the new system) → `BackendExtrasFactory` (`plugins/backend_extras_factory.py`). Name-hygiene; it collides with the new vocabulary.
- [x] `hub.py`: `get_plugin_manager`/`set_plugin_manager` → `get_sdk_client_manager`/`set_sdk_client_manager`; **fix the `"PluginManager2 is not initialized"` message** → `"SdkClientManager is not initialized"`.
- [x] `pipelex.py`: update setup/teardown call sites.
- [x] Fix the wrong-path imports (llm/img_gen/extract → corrected registry path) — free win during the rename.
- [x] **D4 guard:** `SdkClientManager` stays a thin wrapper holding one `SdkClientRegistry`. Do **not** collapse it here — that's a tracked P3 follow-up (see "Deferred / out of scope").

**Tests:** no new tests. Existing suite + `make tb` stay green.

### 🛑 CHECKPOINT 0 — hard stop

- [x] **Verify:** `make agent-check` clean · `make tb` green · `make agent-test` green. Confirm `PluginManager2` artifact gone (`grep -rn PluginManager2 pipelex/` → empty) and wrong-path `Plugin` imports fixed.
- [x] **Capture cold-start context:** see `### Phase 0 — as-built` in the As-built log.
- [x] **Fan-out `/code-review`:** sub-agent ran `/code-review --fix` on the Phase 0 diff (pure-rename scope). Findings triaged in the as-built note.
- [x] **PR:** superseded — committed on `refactor/Plugins` (single PR to `dev` opens after the tracker is done).

---

## Phase 1 — Seam machinery + LLM family (merged, per D2)

**Goal:** build discovery + contract + registry machinery **and** migrate the LLM family through it in one PR, so the contract is proven against a real, messy family before it locks. No behavior change. Own PR.

> ✅ **DONE — committed on `refactor/Plugins`.** Full record in **`### Phase 1 — as-built`** (As-built log). The unchecked boxes below are the original plan items; all are delivered (or noted as deferred to Phase 2/3) in the as-built.

**New modules (all import-light — must not import any backend SDK or `temporalio`):**

- [ ] `plugins/contract.py` — `PipelexPlugin` (`@runtime_checkable Protocol`: `name: str`, `targets_api: int`, `register(self, registrar) -> None`) + `PLUGIN_API_VERSION: int = 1`. Document the **side-effect-free `register`** invariant here.
- [ ] `plugins/registrar.py` — `PluginRegistrar` accumulator: inference registry, orchestrator registry, **deferred** hub-slot-claim thunks, CLI-command list, teardown-callback list, read-only `config: ConfigRoot`. Menu methods:
  - [ ] `add_inference_backend(*, family, sdk, make_worker: MakeWorkerFn)` (D1 — callable).
  - [ ] `add_orchestrator(*, mode, orchestrator)`.
  - [ ] `claim_content_generator | pipe_router | pipe_run | task_manager(factory: Callable[[], Impl])` (D5 — **thunk, not instance**).
  - [ ] `add_cli_command(*, name, help, command)`, `add_teardown(callback)`.
- [ ] `plugins/inference_backend_registry.py` — `InferenceFamily` (StrEnum: `LLM`/`IMG_GEN`/`EXTRACT`/`SEARCH`), `MakeWorkerFn` TypeAlias, `InferenceBackendRegistry` keyed by `(family, sdk)`. Signature: `make_worker(*, inference_model, backend, sdk_clients, reporting_delegate)`.
- [ ] `plugins/orchestrator_registry.py` — `OrchestratorProtocol` (`async def run(self, *, pipe_job, delivery_assignment) -> PipelexPipeRunOutput`), `OrchestratorRegistry` keyed by `PipelexExecutionMode`.
- [ ] `plugins/discovery.py` — `build_registrar(*, config) -> PluginRegistrar`: **pure function** iterating `BUILTIN_PLUGINS` + `importlib.metadata.entry_points(group="pipelex.plugins")`, version-checking each, calling `plugin.register(registrar)`, skipping any `name` in `config.plugins.disabled` (logged; raise if a core-unconditional plugin is denylisted), fail-loud. Pure ⇒ safe at CLI-build and boot.
- [ ] `plugins/builtins.py` — `BUILTIN_PLUGINS`. Phase 1 fills it with the LLM drivers.
- [ ] `plugins/exceptions.py` — `PluginApiVersionMismatchError`, `DuplicateInferenceBackendError`, `DuplicateOrchestratorError`, `HubSlotAlreadyClaimedError`, `BrokenPluginError`. (`MissingOrchestratorError` lives in `runtime_bridge/exceptions.py` — added in Phase 3.)

**DRY the two repeated blocks (design §6.2):**

- [ ] `SdkClientRegistry.get_or_create(*, handle, build)` replaces the `get_sdk_instance(...) or set_sdk_instance(...)` dance in every arm.
- [ ] `require_sdk(*, spec, extra, msg)` (raises `MissingDependencyError` if `find_spec(spec) is None`) replaces the repeated guard — moved **into** `make_worker` so a missing extra fails at use, not boot.

**LLM family migration:**

- [ ] Collapse `llm_worker_factory.py`'s `match` to `get_inference_backend_registry().lookup(family=LLM, sdk=model_handle.sdk)(...)`. A registry miss → distinct "backend `<sdk>` not registered; is its plugin installed?" error.
- [ ] Each LLM driver plugin's `register` calls `add_inference_backend(family=LLM, sdk="anthropic", make_worker=<closure>)`. Add them to `BUILTIN_PLUGINS`.

**Boot wiring:**

- [ ] In `Pipelex.setup()`, after config is fully resolved (incl. the `temporal_enabled` override at `pipelex.py:193-196`) and before the hub setup points, call `build_registrar(config=get_config())`. Store the two keyed registries on the hub (`set_inference_backend_registry` / `set_orchestrator_registry`). Hold slot-claim thunks, CLI commands, teardown callbacks for their apply-points.
- [ ] **Conflict & version policy (fail loud):** duplicate `(family, sdk)` / duplicate mode / double-claimed slot each raise naming **both** contributors; `targets_api != PLUGIN_API_VERSION` → `PluginApiVersionMismatchError` with the remedy; a broken entry point → `BrokenPluginError` (the one sanctioned `except Exception` site — annotate it).

**Control surface (D7):**

- [ ] Add a core-owned `plugins: PluginsConfig` section (`disabled: list[str]`) to `configs.py`; default `[]` in `pipelex/pipelex.toml` **and** `.pipelex/pipelex.toml` (never a class-def default — repo rule). Apply the denylist in `build_registrar` (skip + log; error on a core-unconditional name).
- [ ] Add the core `pipelex plugins list` command — lists discovered plugins (built-in vs external), what each registered, denylist state.

**Tests (red-green):**

- [ ] Contract conformance (synthetic plugins): protocol satisfaction; `targets_api` mismatch fails loud; duplicate `(family, sdk)` / mode / slot each raise naming both; broken entry point → `BrokenPluginError`; **`build_registrar` idempotent** (two calls, no side effect — pins the side-effect-free invariant).
- [ ] Denylist (D7): a discovered non-core plugin in `plugins.disabled` is skipped + logged; denylisting a core-unconditional plugin raises at startup; `pipelex plugins list` shows built-ins + synthetic externals with contributions + denylist state.
- [ ] **Import-light boot** (codex C12): subprocess with a `sys.meta_path` finder that *raises* on `anthropic`/`mistralai`/`google.genai`/`boto3`/`fal_client`/… → boot with built-ins → assert no raise.
- [ ] Registry round-trip (LLM): register → `lookup(LLM, sdk)` → right `LLMWorkerAbstract`.
- [ ] Error parity: an Anthropic model with the `anthropic` extra absent raises the *same* `MissingDependencyError` text (lib + extra + alternative).

### 🛑 CHECKPOINT 1 — hard stop (contract locks here)

- [x] **Verify:** `make agent-check` clean · `make tb` green · `make agent-test` green. Import-light subprocess guard green; the LLM `match` is gone (replaced by a registry lookup).
- [x] **Capture cold-start context:** see `### Phase 1 — as-built` in the As-built log.
- [x] **Fan-out `/code-review`:** sub-agent ran `/code-review --fix` on the Phase 1 diff (see as-built for triage).
- [x] **PR:** superseded — committed on `refactor/Plugins` (single PR to `dev` opens after the tracker is done).

---

## Phase 2 — Remaining inference families (ImgGen / Extract / Search)

**Goal:** migrate the other three families onto the proven contract. **One family per sub-PR** (lanes A/B/C are independent — can run in parallel worktrees).

> **Pre-work analysis (done — read this before starting; the three factories were already audited so you don't have to re-read them).** Each closure follows the Phase 1 LLM shape: `def _make_x(*, inference_model, backend, sdk_clients, reporting_delegate) -> InferenceWorkerAbstract`, derives `model_handle` from `inference_model`, lazy-imports its factory/worker (`# noqa: PLC0415`), guards optional SDKs with `require_sdk(...)` inside the closure, and caches via `sdk_clients.get_or_create(handle=model_handle, build=lambda: ...)`. Then the family factory (`ImgGen/Extract/Search WorkerFactory`) collapses its `match` to `get_inference_backend_registry().lookup(family=<FAM>, sdk=model_handle.sdk)(...)` exactly like `llm_worker_factory.py` already does, passing `sdk_clients=get_sdk_client_manager().sdk_client_registry` and `cast`ing the result to the family worker abstract. Registry-miss `NotImplementedError` message comes from `InferenceBackendRegistry.lookup` (the per-family "is not supported" / "for image generation" / "for search" wording in the old `case _:` arms goes away — update those families' `test_*_worker_factory.py` unknown-sdk asserts to the new "Is its plugin installed?" wording, as was done for LLM).
>
> **SDK → (vendor plugin · worker · client build) map:**
>
> *IMG_GEN* (`img_gen_worker_factory.py`):
>
> - `gateway_img_gen` → **gateway** plugin · `GatewayImgGenWorker` · `GatewayFactory.make_portkey_client(backend=backend)`
> - `gateway_completions` → **gateway** · `OpenAICompletionsImgGenWorker(openai_completions_factory=GatewayCompletionsFactory(is_http_url_enabled=False))` · `GatewayCompletionsFactory.make_portkey_openai_client_for_completions(model_handle, backend)`
> - `openai_img_gen` → **openai** · `OpenAIImgGenWorker` · `OpenAIClientFactory.make_openai_client(model_handle, backend)`
> - `google` → **google** · `GoogleImgGenWorker` · `GoogleFactory.make_google_client(backend)` · `require_sdk(spec="google.genai", dependency_name="google-genai", extra="google", msg="The google-genai SDK is required in order to use Google Gemini Image models.")`
> - `fal` → **NEW `fal` plugin** · `FalImgGenWorker` · `fal_client.AsyncClient(key=backend.api_key)` (import `from fal_client import AsyncClient`) · `require_sdk(spec="fal_client", dependency_name="fal-client", extra="fal", msg="The fal-client SDK is required in order to use FAL models (generation of images).")`
> - `huggingface_img_gen` → **NEW `huggingface` plugin** · `HuggingFaceImgGenWorker` · `AsyncInferenceClient(provider=provider_literal, token=backend.api_key)` where `provider_literal = HuggingFaceFactory.make_huggingface_inference_provider(provider_str=model_handle.variant)` if `model_handle.variant` else `"auto"` · **C10 BUG FIX: add `require_sdk(spec="huggingface_hub", extra="huggingface", msg="The huggingface_hub SDK is required in order to use HuggingFace image generation models.")`** (the old arm had no guard) — and add the huggingface error-parity test.
> - `blackboxai_img_gen` → **NEW `blackboxai` plugin** · `OpenAICompletionsImgGenWorker(openai_completions_factory=BlackboxaiCompletionsFactory(is_http_url_enabled=True))` · `OpenAIClientFactory.make_openai_client(model_handle, backend)`
> - `openrouter_img_gen` → **NEW `openrouter` plugin** · `OpenAICompletionsImgGenWorker(openai_completions_factory=OpenRouterCompletionsFactory(is_http_url_enabled=True))` · `OpenAIClientFactory.make_openai_client(model_handle, backend)`
> - `azure_rest_img_gen` → **NEW `azure_rest` plugin** · `AzureImgGenWorker(model_handle=model_handle, inference_model=..., reporting_delegate=...)` — **DIRECT construction: no `sdk_clients`/`get_or_create`** (its `test_img_gen_worker_factory.py` asserts `registry.root == {}`).
>
> *EXTRACT* (`extract_worker_factory.py`) — workers take `extra_config=backend.extra_config`:
>
> - `gateway_extract` → **gateway** · `GatewayExtractWorker` · `GatewayFactory.make_portkey_client(backend)`
> - `mistral` → **mistral** · `MistralExtractWorker` · `MistralFactory.make_mistral_client(backend)` · `require_sdk(spec="mistralai", extra="mistral", msg="The mistralai SDK is required in order to use Mistral OCR models through the mistralai client.")`
> - `docling_sdk` → **NEW `docling` plugin** · `DoclingExtractWorker` · `DoclingFactory.make_docling_sdk()` · `require_sdk(spec="docling", extra="docling", msg="The docling library is required in order to use Docling for PDF and image text extraction.")`
> - `pypdfium2` → **NEW `pypdfium2` plugin** · `Pypdfium2Worker(extra_config=..., inference_model=..., reporting_delegate=...)` — **STATELESS: no `get_or_create`, no `require_sdk`** (built directly).
> - `linkup_fetch` → **`linkup` plugin** · `LinkupExtractWorker(extra_config=...)` — **STATELESS (no `get_or_create`)** · `require_sdk(spec="linkup", extra="linkup", msg="The linkup SDK is required in order to use Linkup Fetch extraction models.")`
>
> *SEARCH* (`search_worker_factory.py`) — **C9 normalization: `make_search_worker` currently takes NO `reporting_delegate` and pulls `get_report_delegate()` from the hub twice. Change its signature to accept `reporting_delegate` and pass it through (drop the hub coupling); update its callers.** Closures then receive `reporting_delegate` like every family.
>
> - `linkup` → **`linkup` plugin** · `LinkupSearchWorker(inference_model=..., reporting_delegate=...)` — STATELESS (no client/`get_or_create`).
> - `gateway_search` → **gateway** · `GatewaySearchWorker` · `GatewayFactory.make_portkey_client(backend)`
>
> **NEW vendor plugin modules to create:** `fal`, `huggingface`, `blackboxai`, `openrouter`, `azure_rest`, `docling`, `pypdfium2`, `linkup` (each `pipelex/plugins/<vendor>/<vendor>_plugin.py`, added to `BUILTIN_PLUGINS`). **EXTEND existing plugins** (one `register` adds across families — the cross-family-vendor coordination point): `openai` (+IMG_GEN), `gateway` (+IMG_GEN ×2, +EXTRACT, +SEARCH), `google` (+IMG_GEN), `mistral` (+EXTRACT), `linkup` (EXTRACT + SEARCH — one new plugin serving two families). None of these new SDKs are core-unconditional (only `openai` is). **Build-time check:** `azure_rest`/`pypdfium2`/`linkup`/blackboxai/openrouter closures must stay import-light at module load (lazy factory/worker imports), and the import-light subprocess guard's BLOCKED set should grow to cover `fal_client`, `huggingface_hub`, `docling`, `linkup` so the guard actually proves it.

- [x] **ImgGen (Lane A).** Collapse the `match`. **Fix the pre-existing huggingface bug (codex C10):** `img_gen_worker_factory.py` imports `huggingface_hub` with **no `find_spec` guard` → a missing extra raises raw `ImportError` instead of `MissingDependencyError`. Add `require_sdk(spec="huggingface_hub", extra="huggingface", …)` during migration. Provider-literal handling (`model_handle.variant` → provider) goes inside the closure. Substrate-reuse workers (`blackboxai`/`gateway_completions`/`openrouter` → `OpenAICompletionsImgGenWorker`) become closures capturing the per-vendor completions factory.
- [x] **Extract (Lane B).** Collapse the `match`. Stateless arms (`pypdfium2`, `linkup_fetch`) skip `get_or_create`.
- [x] **Search (Lane C) — normalize the call surface (codex C9).** `search_worker_factory.py` takes **no `reporting_delegate` param** and pulls `get_report_delegate()` from the hub; the uniform `MakeWorkerFn` passes it explicitly. Normalize `make_search_worker` + callers to accept `reporting_delegate` (removes search's hidden hub coupling — a strict improvement), so search fits the uniform signature.
- [x] Add each migrated driver to `BUILTIN_PLUGINS`. OpenAI is an always-on built-in driver, no privileged arm. The OpenAI-compat *substrate* stays an in-tree library the gateway/portkey/openrouter/blackboxai closures import (substrate extraction into a named module is deferred).

**Tests:**

- [x] Registry round-trip per family.
- [x] Import-light subprocess guard now covers all optional SDKs.
- [x] **huggingface error-parity** (missing `huggingface` extra now raises `MissingDependencyError` — proves the bug fix).
- [x] **Cross-family vendor** (e.g. `mistral` registers into both LLM and Extract from one `register`).

**Cross-cutting deliverable (ships with this phase):**

- [x] **Inference SPI reference** (design §9.1) + **plugin-authoring guide** + **minimal example backend plugin** — delivered as one comprehensive page `docs/under-the-hood/inference-backend-plugins.md` (seam walkthrough + SPI module/symbol table + authoring guide with a copy-pasteable `acme` example, the entry-point declaration, the denylist, and the fail-loud table), added to both mkdocs nav blocks under "Under the Hood". A standalone runnable example *package* was judged disproportionate for this checkpoint (the embedded example is complete and copy-pasteable) — flag as a follow-up if a separate example repo is wanted.

### 🛑 CHECKPOINT 2 — hard stop (natural session handoff — inference done)

- [x] **Verify:** `make agent-check` clean · `make agent-test` green (exit 0). All four worker-factory `match` statements gone, every backend goes via the registry, the huggingface guard bug is fixed (require_sdk added), and search's hub coupling is removed (factory takes `reporting_delegate`, caller supplies `get_report_delegate()`).
- [x] **Capture cold-start context:** `### Phase 2 — as-built` note below — vendor plugins created/extended, cross-family coordination points, the search C9 normalization, test + docs locations.
- [x] **Fan-out `/code-review`:** `pr-review-toolkit:code-reviewer` sub-agent reviewed the full Phase 2 working-tree diff, comparing every new closure against the pre-Phase-2 `match` arm via `git show HEAD:…`. **Verdict: clean — no blockers, no should-fix, no nits.** It confirmed byte-equivalent parity (worker classes, ctor kwargs, `is_http_url_enabled` flags), the C10 require_sdk fix + TYPE_CHECKING-only `PROVIDER_OR_POLICY_T`, import-light (no SDK at any plugin module top), every `# noqa: ARG001` justified by the old arm, C9 production-safety (real caller still supplies the delegate; the two integration tests assert on results not reporting so `None` is harmless), and cross-family non-collision (distinct `(family, sdk)` keys + distinct closure names).
- [x] **Commit:** single checkpoint commit on `refactor/Plugins` (per the branch's one-commit-per-checkpoint delivery model). **Good point to end the session** before opening the orchestrator phase.

---

## Phase 3 — Orchestrators through the seam (in-tree) — HIGHEST RISK

**Goal:** collapse the bridge `match` + the four `temporal.is_enabled` boot blocks into registry/slot lookups; move Temporal's modes/CLI/boot-swap/teardown behind its (still-in-repo) plugin; flip Mistral's hard import to discovery; publish the orchestrator SPI. No behavior change. Own PR.

> **Spike the CLI-timing + thunk integration (D3+D5) FIRST** — it's the one genuinely novel integration point. Prove `build_registrar` at CLI-build harvests `worker` into `--help` without constructing a Temporal impl, before doing the rest.

**Extract orchestrators (verbatim bodies):**

- [ ] `DirectOrchestrator.run` from `_run_direct` (`bridge.py:270-294`). **Correctness landmine (design §8.1): keep `with scoped_pipe_router(PipeRouter())` verbatim** — dropping it leaks DIRECT-mode nested sub-pipes to Temporal inside a Temporal worker. Registered in core, always-on.
- [ ] `TemporalBlockingOrchestrator` / `TemporalFireAndForgetOrchestrator` from `_run_temporal_*` (`:297-355`), keeping the `WorkflowExecutionError` catch and `make_workflow_id` recompute.
- [ ] (`MistralWorkflowsOrchestrator` is authored in `pipelex-mistralai-workflows`, **not here** — Phase 5 cross-repo.)

**Bridge + Mistral:**

- [ ] Collapse the bridge `match` (design §8.1) to a registry lookup. After it, `bridge.py` names no integration.
- [ ] **Preserve per-mode error quality (codex C7 — a generic hint is a regression):** today `bridge.py:399/:417` carry exact per-mode install messages ("install `pipelex[temporal]`" vs "install `pipelex-mistralai-workflows`"). `MissingOrchestratorError` takes the `mode` and maps it to its exact message via `PipelexExecutionMode.requires_*` properties. One message per mode, verbatim.
- [ ] **Mistral → entry-point discovery (this repo's side):** remove the `_run_mistral_native` hard import (`bridge.py:408/:414`). Uninstalled (CI default) → `MISTRAL_NATIVE` absent → `MissingOrchestratorError` with the exact Mistral message. pipelex's suite proves dispatch with a *fake* registered orchestrator.

**The Temporal plugin (`TemporalOrchestrator`), its `register`:**

- [ ] **always** `add_orchestrator(TEMPORAL_BLOCKING|TEMPORAL_FIRE_AND_FORGET, …)` + `add_cli_command("worker"|"setup-temporal-namespace", …)`.
- [ ] **if `config.temporal.is_enabled`:** `claim_content_generator | pipe_router | pipe_run | task_manager(factory)` + `add_teardown(...)` — **D5: each `claim_*` gets a thunk** (e.g. `claim_content_generator(lambda: ContentGeneratorInWorkflowFactory.make_content_generator_in_workflow())`), so `register` never imports `temporalio`. The thunk runs at the setup apply-point.

**Boot/teardown collapse (codex C8 — explicit injection precedence):**

- [ ] The four `if get_config().temporal.is_enabled:` blocks (`pipelex.py:377-466`) become, at each ordered point (content generator → task manager → router → run): **explicit `setup()` param (`:376/:450`) > plugin slot-claim thunk > core default.** The slot claim must **not** silently override an explicit injection — pin in a test.
- [ ] The inlined teardown (`:471-479`) becomes a registered teardown callback run **LIFO**.

**CLI collapse (codex C4 + D3):**

- [ ] The two hard imports in `_cli.py:15,20` become plugin-contributed commands. Rework `PipelexCLI.list_commands` (hardcodes order) to merge core commands with `registrar.cli_commands` deterministically (stable order, clean `--help`, unknown-command behavior intact).
- [ ] CLI entry point loads config then runs the pure `build_registrar` once to harvest `registrar.cli_commands`; D5's thunks mean this never constructs a Temporal impl even when `temporal.is_enabled`.

**SPI:**

- [ ] **Publish the orchestrator SPI** (design §9.2, sized to Mistral's *measured* imports): `runtime_bridge.*` incl. `runtime_bridge.primitives.*`; execution protocols; boundary/core payload types; library-crate access + hub scoping; tracing hooks. Documented module/symbol list. Add `MissingOrchestratorError` to `runtime_bridge/exceptions.py` (replaces the two old typed errors).

**Tests:**

- [ ] Bridge dispatch by mode (fake orchestrator).
- [ ] **Per-mode error parity** (each missing mode → its exact message — C7).
- [ ] DIRECT router scoping (the landmine) + DIRECT parity (byte-identical).
- [ ] **Injection-precedence** (explicit param wins over a slot claim — C8).
- [ ] Boot-via-slots (stripped env → DIRECT + core backends; temporal-enabled → four slots resolve to Temporal impls via thunks) + teardown LIFO order.
- [ ] **CLI-command contribution** (`worker` in `--help` when plugin discoverable, absent otherwise — pins D3).
- [ ] **Full Temporal suite green in-tree** (§14.5 — the extraction gate; Phase 5 does not start until this is green).

### 🛑 CHECKPOINT 3 — hard stop (THE gate before externalization)

- [ ] **Verify:** `make agent-check` clean · `make agent-test` green · **full Temporal suite green through the seam** (`.venv/bin/pytest tests/integration/pipelex/temporal/`, see `_plugins/CLAUDE.md` for `--temporal-server` options). Confirm bridge + boot/teardown + CLI name **no** integration (`grep` for `temporal`/`mistral` in those files → only via registry/config).
- [ ] **Capture cold-start context:** `### Phase 3 — as-built` note — the final injection-precedence ordering, where slot thunks apply in `setup()`, the CLI-merge mechanism, the orchestrator SPI module/symbol list, and the exact §14.5 green-state evidence. This is the externalization gate; the next session must trust this record.
- [ ] **Fan-out `/code-review`:** sub-agent runs `/code-review` on the Phase 3 diff. This is the riskiest phase — emphasize the DIRECT `scoped_pipe_router` landmine, per-mode error parity, injection precedence, thunk import-light preservation, and CLI determinism. Triage carefully here.
- [ ] **PR:** land green. **Do NOT begin Phase 5** until this checkpoint's Temporal-green gate is recorded as passed.

---

## Phase 4 — Invert model listing (the 5th seam, per D6)

**Goal:** close the goal. `model_lists.py`'s `match sdk:` (the `list-models` CLI path) still hardcodes `pipelex.plugins.{openai,anthropic,mistral,google,bedrock}.*_list` imports. Invert it so core names no integration *anywhere*. Own PR.

- [ ] Add a **model-listing capability** to the inference contract: `add_model_lister(*, sdk, lister: ListModelsFn)` (callable mirroring `MakeWorkerFn` — import-light, lazy). A backend plugin that lists models registers its lister alongside its worker factory.
- [ ] Collapse `ModelLister.list_models` (`model_lists.py`) to a registry lookup keyed by `sdk`; a miss → the same friendly "is its plugin installed?" guidance. Move the `find_spec` guards (already in this file) into each lister.
- [ ] The contract grows by one **optional** method — backends without listing simply don't register a lister (progressive disclosure preserved).

**Tests:**

- [ ] Round-trip (a registered lister is invoked for its `sdk`).
- [ ] A backend with no lister → the friendly miss.
- [ ] Import-light subprocess guard still green (listers are lazy).

### 🛑 CHECKPOINT 4 — hard stop ("core names no integration" holds without an asterisk)

- [ ] **Verify:** `make agent-check` clean · `make agent-test` green. Confirm `model_lists.py` names no integration; run a final sweep — `grep -rn 'pipelex.plugins.\(openai\|anthropic\|mistral\|google\|bedrock\)' pipelex/cogt pipelex/runtime_bridge pipelex/cli pipelex/pipelex.py pipelex/system` → only registry/contract code.
- [ ] **Capture cold-start context:** `### Phase 4 — as-built` note — the `ListModelsFn` shape, which backends registered a lister, and a statement that the "no integration by import or string in core" invariant now holds.
- [ ] **Fan-out `/code-review`:** sub-agent runs `/code-review` on the Phase 4 diff. Emphasize the optional-capability progressive-disclosure pattern and import-light preservation. Triage here.
- [ ] **PR:** land green. Phases 0–4 complete — the in-`pipelex` work is done.

---

## Phase 5 — Externalize Temporal → `pipelex-temporal` (cross-repo, GATED on Checkpoint 3)

**Goal:** lift `pipelex/temporal/` into a separate dist. A *packaging* move — but only after a prerequisite the design missed. **Cross-repo; the only phase that can break downstream deploys. Separate effort.**

- [ ] **Step 0 — relocate the Temporal config schema to a core-owned module (codex C6 — the prerequisite).** `config_temporal.py` lives at `pipelex.temporal.config_temporal` and imports `pipelex.temporal.exceptions` (`TemporalConfigError`, `WorkerTaskQueueUnknownError`). "Keep config in core, move `pipelex/temporal/` out" is impossible while the schema sits under `pipelex.temporal`. Relocate the schema **and the two exceptions it needs** to a core-owned module (e.g. `pipelex/system/configuration/config_temporal.py` + the exceptions into a core `exceptions.py`). Update `configs.py:14`. Keep the `if TYPE_CHECKING: … RetryPolicy = Any` placeholder. `make tb` stays meaningful. *(Low-risk; could be pulled into Phase 3.)*
- [ ] Move `pipelex/temporal/` (impl) + `temporal_plugin.py` + tests + the `temporal` marker + the `--temporal-server` conftest option into `pipelex-temporal`; declare `[project.entry-points."pipelex.plugins"]`.
- [ ] Keep protocol-level conformance tests in core; Temporal's behavioral suite travels.
- [ ] **Flip downstream pins** (cross-repo blast radius): `pipelex-worker`, `pipelex-api-hosted` from `pipelex[temporal]==X` → `pipelex-temporal==Y`.
- [ ] **Repoint `pipelex-mistralai-workflows`** (design §15): its `temporal` extra + `pipelex.temporal.*` imports → `pipelex-temporal`.

**Tests:**

- [ ] Re-run the relocated Temporal suite against published `pipelex`.
- [ ] Run downstream consumers' suites against the new pins **before** publishing.

### 🛑 CHECKPOINT 5 — hard stop (final)

- [ ] **Verify:** Temporal is an external plugin; core has no `temporal` extra; downstream pins flipped; consumer suites green.
- [ ] **Capture cold-start context:** `### Phase 5 — as-built` note — the published `pipelex-temporal` version, the pins flipped in each downstream repo, and the consumer-suite green evidence.
- [ ] **Fan-out `/code-review`:** sub-agent runs `/code-review` per repo touched (cross-repo). Triage here.
- [ ] **Ship:** coordinate the cross-repo release. Effort complete.

---

## Deferred / out of scope (considered, parked — do NOT do these in 0–5)

- [ ] **P3 follow-up commit:** collapse `SdkClientManager` into `SdkClientRegistry` (hub holds the registry directly) — D4 keeps it out of the Phase 0 rename. Land as its own commit after Phase 0.
- Third-party-defined execution modes (open string-keyed space) — enum stays closed (design D5).
- Generic per-plugin typed-config namespace — Temporal config stays typed in core (design D7).
- Deliberately *overriding* a built-in (third party replacing core's OpenAI driver) — design §5.3.
- Per-SPI versions / semver-range matching — single coarse `int` (design §5.4).
- Vendor inference dists + OpenAI-substrate extraction into a named module — design §6.4/§6.6/§11.
- Distribution/CI for `pipelex-temporal` — part of Phase 5's cross-repo effort.

---

## Sequencing

Phase 0 (rename) → Phase 1 (seam + LLM, merged) → Phase 2 (ImgGen/Extract/Search, parallel sub-PRs) → Phase 3 (orchestrators) → Phase 4 (model_lists) → **[gate: Checkpoint 3 §14.5 Temporal-green]** → Phase 5 (externalize Temporal, cross-repo). Phases 0–4 are independent PRs in `pipelex`; each lands green. Inference SPI + authoring guide ship with Phase 2; orchestrator SPI with Phase 3. Phases 0 and 1 are strictly sequential; after Phase 1 lands, lanes A (ImgGen) / B (Extract) / C (Search) / D (Phase 3) / E (Phase 4) can run in parallel worktrees — **conflict flag:** lanes A/B/C and E both touch `plugins/<vendor>/` for multi-family vendors; coordinate the per-vendor plugin object.

---

## As-built log (append per phase at each checkpoint — keep this current for cold starts)

> Each checkpoint appends an `### Phase N — as-built` subsection here with: final names/signatures, divergences from plan, test evidence, and anything a cold resume needs.

### Phase 0 — as-built

**Status:** done, committed on `refactor/Plugins`. `make agent-check` clean (ruff/plxt/pyright 0/mypy 0/keyword-only pass) · `make tb` green · `make agent-test` green.

**Final module → class map** (`pipelex/plugins/`):

| Old module / symbol | New module / symbol |
|---|---|
| `plugin.py` · `Plugin` | `model_handle.py` · `ModelHandle` |
| `plugin_sdk_registry.py` · `PluginSdkRegistry` (`PluginSdkRegistryRoot`) | `sdk_client_registry.py` · `SdkClientRegistry` (`SdkClientRegistryRoot`) |
| `plugin_manager.py` · `PluginManager` | `sdk_client_manager.py` · `SdkClientManager` |
| `plugin_factory_abstract.py` · `PluginFactoryAbstract` | `backend_extras_factory.py` · `BackendExtrasFactory` |

- `SdkClientRegistry.get_sdk_instance`/`set_sdk_instance` → **`get(self, model_handle)`** / **`set(self, *, model_handle, sdk_instance)`** (subject `model_handle` positional; the DRY `get_or_create` is still Phase 1, not added here).
- `SdkClientManager.plugin_sdk_registry` attribute → **`sdk_client_registry`** (the D4 thin-wrapper shape preserved; collapse into the registry remains the deferred P3 commit).
- `hub.py`: `get_plugin_manager`/`set_plugin_manager` → `get_sdk_client_manager`/`set_sdk_client_manager` (both the `PipelexHub` methods and the module-level functions); field `_plugin_manager` → `_sdk_client_manager`; the `"PluginManager2 is not initialized"` message is now `"SdkClientManager is not initialized"`.
- `pipelex.py`: `self.plugin_manager` → `self.sdk_client_manager` at construction/setup/teardown call sites.

**Scope beyond the literal rename (kept it a clean "free the word plugin"):** the `Plugin` *type* rename was carried through to the variables/params that held it — `plugin` → `model_handle` — across the four worker factories and every in-tree adapter (`openai`, `bedrock`, `anthropic`, `gateway`, `portkey`, `azure_rest`). The four wrong-path imports (`llm`/`img_gen`/`extract` imported `Plugin` from `plugin_sdk_registry`; `search` used the correct path) are all now `from pipelex.plugins.model_handle import ModelHandle`. Adapter error messages `f"Plugin '{...}'…"` → `f"ModelHandle '{...}'…"`. Prose/comment uses of "plugin" that mean the *future plugin concept* (e.g. `pipe_llm.py`, `provider_name.py`, `model_deck.py`, `cogt/exceptions.py`, `error_pages_generator.py`) were left untouched (one capital-P comment in `pipe_llm.py` was lowercased to read as the concept, not the type).

**Tests touched:** symbol/kwarg renames in the worker-factory routing tests, the gateway/transport/azure error-handling tests, and the temporal teardown call sites. The `plugin=`→`model_handle=` kwarg flip and `client_kwargs["plugin"]`→`["model_handle"]` assertions track the renamed param. Fixtures `plugin_for_openai`/`plugin_for_anthropic` → `model_handle_for_openai`/`model_handle_for_anthropic`, and `tests/integration/pipelex/fixtures/plugin_fixtures.py` → `model_handle_fixtures.py` (conftest import + `__all__` updated). The `tests/integration/pipelex/plugins/` dir name was kept — it reads correctly as backend tests under the new vocabulary.

**No behavior change.** Pure rename; the dispatch `match` statements, caching dance, and error surfaces are byte-equivalent modulo identifiers.

**Deferred (still open):** P3 follow-up — collapse `SdkClientManager` into `SdkClientRegistry` (hub holds the registry directly), own commit after Phase 0. Not done here by D4.

### Phase 1 — as-built

**Status:** done, committed on `refactor/Plugins`. `make agent-check` clean (pyright 0 / mypy 0 over 2219 files / keyword-only pass) · `make tb` green · `make agent-test` fully green. `/code-review --fix` ran clean. This is the locked contract Phases 2–4 build against.

**New seam modules** (all in `pipelex/plugins/`, all import-light — importing them imports no backend SDK or `temporalio`):

- `contract.py` — `PipelexPlugin` (`@runtime_checkable Protocol`: `name: str`, `targets_api: int`, `register(self, registrar) -> None`) + `PLUGIN_API_VERSION: int = 1`. Docstring states the **side-effect-free `register`** invariant.
- `inference_backend_registry.py` — `InferenceFamily(StrEnum)` = LLM/IMG_GEN/EXTRACT/SEARCH; `MakeWorkerFn: TypeAlias = Callable[..., InferenceWorkerAbstract]`; `InferenceBackendRegistry` keyed by `(family, sdk)` with `.lookup(*, family, sdk)` (miss → `NotImplementedError` "No inference backend registered for sdk '<sdk>' in the <family> family. Is its plugin installed?"), `.has(...)`, `.keys`. Also hosts **`require_sdk(*, spec, extra, msg, dependency_name=None)`** — `spec` accepts a `str` or a `Sequence[str]` (bedrock needs both `boto3`+`aioboto3`); `dependency_name` overrides the displayed package when it differs from the import name (google: spec `google.genai` / dep `google-genai`); raises `MissingDependencyError`.
- `orchestrator_registry.py` — `OrchestratorProtocol` (`async def run(self, *, pipe_job, delivery_assignment) -> PipelexPipeRunOutput`) + `OrchestratorRegistry` keyed by `PipelexExecutionMode` (`.get_optional`, `.has`, `.modes`). **Skeleton only — not consumed until Phase 3.**
- `registrar.py` — `PluginRegistrar` accumulator + `PluginDiscovery` (mutable BaseModel: name/origin/status/targets_api/contributions/detail), `HubSlot`/`PluginOrigin`/`PluginStatus` StrEnums, `CliCommand` NamedTuple. Menu surface: `add_inference_backend(*, family, sdk, make_worker)`, `add_orchestrator(*, mode, orchestrator)`, `claim_content_generator|pipe_router|pipe_run|task_manager(factory)` (D5 thunks), `add_cli_command(*, name, help, command)`, `add_teardown(callback)`. `begin_plugin(...)` (driven by `build_registrar`) sets the "active" discovery so contributions are attributed and **duplicate errors name both contributors**. Duplicate `(family,sdk)`/mode/slot each raise their fail-loud error.
- `discovery.py` — **`build_registrar(*, config: PipelexConfig) -> PluginRegistrar`** (pure, idempotent, D3-safe). Iterates `BUILTIN_PLUGINS` then `importlib.metadata.entry_points(group="pipelex.plugins")` (external entry points resolve to a plugin instance or a zero-arg factory); version-checks each (`targets_api != PLUGIN_API_VERSION` → `PluginApiVersionMismatchError`); skips + logs names in `config.plugins.disabled` (raises `CoreUnconditionalPluginDisabledError` if the name is in `CORE_UNCONDITIONAL_PLUGIN_NAMES`); wraps any other failure in `BrokenPluginError` (the two sanctioned `except Exception` sites, annotated "Case 2"). The `_external_entry_points()` helper is the monkeypatch seam for tests.
- `builtins.py` — `BUILTIN_PLUGINS` = the seven LLM driver plugin instances (OpenAI, Gateway, Portkey, Anthropic, Mistral, Bedrock, Google); `CORE_UNCONDITIONAL_PLUGIN_NAMES = frozenset({"openai"})`.
- `exceptions.py` — `PluginError` base (CONFIG domain) + `PluginApiVersionMismatchError`, `DuplicateInferenceBackendError`, `DuplicateOrchestratorError`, `HubSlotAlreadyClaimedError`, `CoreUnconditionalPluginDisabledError`, `BrokenPluginError`. (`MissingOrchestratorError` is Phase 3, in `runtime_bridge/exceptions.py`.)

**Driver plugins** (one per vendor, in `pipelex/plugins/<vendor>/<vendor>_plugin.py`): each is a tiny class (`name`, `targets_api`, `register`) whose `register` calls `add_inference_backend(family=LLM, sdk=..., make_worker=<module-level closure>)`. The closures do the lazy SDK imports (`# noqa: PLC0415`), the `require_sdk` guard (anthropic/mistral/bedrock/google), and `sdk_clients.get_or_create(handle=model_handle, build=lambda: ...)`. They are byte-equivalent to the old `match` arms. **Phase 2 extends these same vendor plugins** to register IMG_GEN/EXTRACT/SEARCH backends (the cross-family-vendor coordination point).

**DRY helpers (design §6.2):** `SdkClientRegistry.get_or_create(*, handle, build)` (uses `is not None`, not truthiness) replaced the `get(...) or set(...)` dance; `require_sdk(...)` replaced the per-arm `find_spec` guard, moved **into** the closures so a missing extra fails at use.

**`MakeWorkerFn` call shape (the locked contract):** `make_worker(*, inference_model, backend, sdk_clients, reporting_delegate)` → `InferenceWorkerAbstract`. The closure derives its own `model_handle` from `inference_model`. The dispatcher (`LLMWorkerFactory.make_llm_worker`) builds `model_handle`, resolves `backend` via the models manager, `lookup`s the registry, calls the closure with `sdk_clients=get_sdk_client_manager().sdk_client_registry`, and `cast`s the result to `LLMWorkerInternalAbstract`.

**Boot wiring (`pipelex.py:setup()`):** `build_registrar(config=get_config())` is called **after** the gateway/model-setup checks (so `Pipelex.__new__(...).setup()` tests that expect `InferenceSetupRequiredError`/`GatewayTermsNotAcceptedError` still raise first) and **before** the content-generator/router/run hub setup points (right before `set_dry_run_forced`). The two registries are stored on the hub via `set_inference_backend_registry` / `set_orchestrator_registry`; the registrar is held on `self._plugin_registrar` for Phase 3's slot-thunk/CLI/teardown apply-points (empty in Phase 1).

**Hub:** added `_inference_backend_registry` / `_orchestrator_registry` fields, `set_/get_inference_backend_registry`, `set_/get_orchestrator_registry` (raise if unset), and module-level `get_inference_backend_registry()` / `get_orchestrator_registry()`. Registry types imported under `TYPE_CHECKING` (hub is imported everywhere — avoids cycles).

**Import-cycle break (not in the original plan, required):** `PipelexPipeRunInput` / `PipelexPipeRunOutput` were extracted from `runtime_bridge/bridge.py` into a new import-light **`runtime_bridge/payloads.py`**; `bridge.py` re-imports them (so `from ...bridge import PipelexPipeRunInput` still works for the existing tests). Without this, `orchestrator_registry → bridge → bootstrap → pipelex` was a `reportImportCycles` error.

**Control surface (D7):** core-owned `PluginsConfig` (`disabled: list[str]`) added to `configs.py` as `PipelexConfig.plugins`; `[plugins] disabled = []` added to **both** `pipelex/pipelex.toml` and `.pipelex/pipelex.toml` (real default, not commented). New `pipelex plugins list` command (`cli/commands/plugins_cmd.py`, registered in `_cli.py` + `list_commands`) renders `build_registrar(...).discoveries` as a Rich table.

**Tests:** `tests/unit/pipelex/plugins/test_plugin_discovery.py` (protocol satisfaction, version mismatch, duplicate backend/mode/slot naming both, broken plugin + broken entry point, **idempotent `build_registrar`**, denylist skip + core-unconditional raise, discoveries describe built-ins) and `tests/unit/pipelex/plugins/test_import_light_boot.py` (subprocess `sys.meta_path` import-blocker). The existing `test_llm_worker_factory.py` was updated to build the real registry from `BUILTIN_PLUGINS` and patch `get_inference_backend_registry` — so it exercises the real closures through the real lookup (registry round-trip + caching + huggingface-style missing-dependency parity + the registry-miss `NotImplementedError`). New error classes → `pipelex-dev generate-error-pages` regenerated `docs/errors/`.

**Behavior unchanged** in LLM dispatch except the deliberate registry-miss error wording (was `"ModelHandle '<...>' is not supported"`, now `"No inference backend registered for sdk '<sdk>' ... Is its plugin installed?"`).

**Deferred / notes for later phases:** docs (Inference SPI reference + plugin-authoring guide + example backend plugin) ship with **Phase 2** per plan — not written in Phase 1. The orchestrator registry/protocol is a skeleton; Phase 3 wires the bridge `match` collapse, slot-thunk apply-points (with injection-precedence), CLI-command harvesting, and adds `MissingOrchestratorError`.

### Phase 2 — as-built

**Status:** done, uncommitted on `refactor/Plugins`. `make agent-check` clean (ruff/plxt, pyright **0 errors**, mypy 0 over 2228 files, keyword-only pass) · `make tb` green · targeted plugins+cogt unit suite green (977 passed) · **full `make agent-test` green (exit 0, "All tests passed.")**. All four worker-factory `match` statements are gone — every inference backend now resolves through `get_inference_backend_registry().lookup(family, sdk)`.

**Registry shape after Phase 2** — `BUILTIN_PLUGINS` now has 15 plugins contributing **30** `(family, sdk)` backends: LLM 14, IMG_GEN 9, EXTRACT 5, SEARCH 2.

**New vendor plugin modules** (`pipelex/plugins/<vendor>/<vendor>_plugin.py`, each added to `BUILTIN_PLUGINS`):

- `fal` → IMG_GEN `fal` (require_sdk `fal_client`/extra `fal`, dep name `fal-client`).
- `huggingface` → IMG_GEN `huggingface_img_gen`. **C10 bug fixed:** added `require_sdk(spec="huggingface_hub", extra="huggingface")` (the old arm imported `huggingface_hub` with no guard). The `PROVIDER_OR_POLICY_T` annotation is a module-level `if TYPE_CHECKING` import (import-light at runtime); the `model_handle.variant → provider` resolution lives in the closure.
- `blackboxai` → IMG_GEN `blackboxai_img_gen` (OpenAI-completions substrate, `BlackboxaiCompletionsFactory(is_http_url_enabled=True)`; no require_sdk — reuses OpenAI client).
- `openrouter` → IMG_GEN `openrouter_img_gen` (same substrate shape, `OpenRouterCompletionsFactory(is_http_url_enabled=True)`).
- `azure_rest` → IMG_GEN `azure_rest_img_gen`. **DIRECT construction** — `AzureImgGenWorker(model_handle=…)`, no `sdk_clients`/`get_or_create`; `backend` + `sdk_clients` params carry `# noqa: ARG001`.
- `docling` → EXTRACT `docling_sdk` (require_sdk `docling`; `get_or_create(build=DoclingFactory.make_docling_sdk)`).
- `pypdfium2` → EXTRACT `pypdfium2`. **STATELESS** — built directly, no `get_or_create`, no require_sdk; `sdk_clients` param `# noqa: ARG001`.
- `linkup` → EXTRACT `linkup_fetch` (require_sdk `linkup`, stateless) **and** SEARCH `linkup` (stateless, **no** require_sdk — matches the original search arm exactly; raw `ImportError` if linkup absent, a deliberate no-behavior-change choice). One plugin, two families.

**Extended existing vendor plugins** (one `register` now spans families — the cross-family coordination point):

- `openai` += IMG_GEN `openai_img_gen`.
- `gateway` += IMG_GEN `gateway_img_gen` + `gateway_completions`, EXTRACT `gateway_extract`, SEARCH `gateway_search` (now serves **all four** families). Closures named `_make_gateway_{img_gen,completions_img_gen,extract,search}_worker` (distinct from the existing LLM `_make_gateway_{completions,responses}_worker`).
- `google` += IMG_GEN `google` (own missing-msg constant `_GOOGLE_IMG_GEN_MISSING_MSG`, distinct from the LLM one).
- `mistral` += EXTRACT `mistral` (own `_MISTRAL_EXTRACT_MISSING_MSG`).

Note: `gateway_completions` and `google` are SDK strings registered in **two** families each — distinct `(family, sdk)` keys, no conflict. The OpenAI-compat substrate (`OpenAICompletionsImgGenWorker`, the per-vendor `*CompletionsFactory`) stays an in-tree library the substrate-reuse closures import; extraction into a named module remains deferred.

**Factory collapses** (`cogt/{img_gen,extract,search}/*_worker_factory.py`): each is now the LLM shape — derive `model_handle`, resolve `backend` via the models manager, `lookup(family=<FAM>, sdk=model_handle.sdk)`, call with `sdk_clients=get_sdk_client_manager().sdk_client_registry`, `cast` to the family worker abstract. Kept `@classmethod` (call sites unchanged). The per-family `case _:` wording ("is not supported …") is gone — registry miss now raises the uniform `NotImplementedError("… Is its plugin installed?")` from `InferenceBackendRegistry.lookup`.

**Search C9 normalization:** `make_search_worker` now takes `*, reporting_delegate: ReportingProtocol | None = None` (default `None`, so existing test callers that omit it still work) and passes it through — the factory no longer pulls `get_report_delegate()` from the hub. The hub coupling moved to the caller: `cogt/content_generation/search_generate.py::_make_search_worker` now passes `reporting_delegate=get_report_delegate()` (import added). No production behavior change (the real caller still supplies the delegate); integration tests that call the factory directly get `None`, which the workers already accept.

**Tests:** `tests/unit/pipelex/cogt/img_gen/test_img_gen_worker_factory.py` updated to build the real registry from `BUILTIN_PLUGINS` (new `build_builtin_inference_backend_registry` + patches `get_inference_backend_registry` in `patch_hub_getters`), the unknown-sdk assert switched to "Is its plugin installed?", and `huggingface_img_gen` added to the missing-dependency parametrize (proves the C10 fix). New `tests/unit/pipelex/plugins/test_inference_backend_coverage.py` pins the full 30-key `(family, sdk)` round-trip + the cross-family vendors (mistral LLM+EXTRACT, google/openai LLM+IMG_GEN, linkup EXTRACT+SEARCH, gateway all four). Import-light guard BLOCKED set grew `docling` + `linkup` (fal_client/huggingface_hub were already there) — proves the new vendor plugin modules import no optional SDK at boot.

**Docs:** `docs/under-the-hood/inference-backend-plugins.md` (added to both mkdocs nav blocks) — the seam walkthrough, the `PipelexPlugin` contract, `MakeWorkerFn` + import-light/fail-at-use invariants, a complete copy-pasteable `acme` example (built-in + `[project.entry-points."pipelex.plugins"]` form), the `plugins.disabled` denylist, the SPI module/symbol table, and the fail-loud table.

**No factory test modules for extract/search** existed before and none added — those families are covered by the new registry-coverage test + the integration suites (`test_search.py`, extract integration). Only img_gen had a routing test to update.

#### Post-checkpoint xhigh `/code-review` (2026-06-20, on PR #997 = the whole Phases 0–2 diff)

Beyond the per-phase CP reviews above, an **xhigh** whole-PR pass ran (10 finder angles → 35 candidates → independent verify → 13 kept). **No live correctness bug.** Three CONFIRMED pre-merge gaps fixed + committed as `94fa908df` (`make agent-check` green, 78 affected tests pass). These **supersede specifics in the CP2 record above**:

- **Lookup-miss error (supersedes the line about `NotImplementedError("… Is its plugin installed?")`):** `InferenceBackendRegistry.lookup` now raises a structured **`InferenceBackendNotFoundError(PluginError)`** (new in `plugins/exceptions.py`, carries `family`/`sdk`, message ends "Is its plugin installed **and enabled?**"). Both factory miss-tests assert the structured type + `.sdk`.
- **Import-light blocklist (supersedes "BLOCKED grew docling+linkup"):** added `openai`, `portkey_ai`, `pypdfium2` — the migrated plugins' deferred SDKs the guard wasn't covering. (The review said "openrouter," but that closure rides the `openai` SDK; verified by probe that none of the three are imported at registration time, so the invariant holds.) The guard docstring now says "any backend SDK (optional extra **or** heavy core dep)."
- **Multi-spec `require_sdk`:** on a partial miss it named ALL specs; now collects + names only the absent one(s) (so a user with `boto3` but not `aioboto3` isn't told to reinstall `boto3`). New `test_require_sdk` multi-spec case.

**Deferred follow-ups → `wip/plugins/phase-2-review-deferred.md`** (latent footguns reachable only via external entry-point plugins / future callers + quality cleanups). **Two bear on Phase 3 — read that doc before starting:**

- `build_registrar` accumulates `cli_commands` / `slot_claims` / `teardown_callbacks` but boot only consumes `inference_backends` + `orchestrators` — i.e. those three menus are **wired for the first time in Phase 3** (CLI collapse / Boot-teardown collapse). The doc frames the current state as a teardown-leak footgun for *external* plugins; closing it is literally Phase 3 work. Until then, an external plugin contributing those is silently inert.
- search `reporting_delegate` defaults to `None` (the C9 normalization above) — fine for the one real caller, but a future Temporal search-activity path that omits it gets silent zero-reporting. Relevant when Phase 3/5 routes search through a worker.

(The `ModelHandle` double-construction cleanup is cross-referenced there to the existing `phase-1-review-deferred.md`; it dissolves if Phase 3 threads `model_handle` through `MakeWorkerFn`.)
