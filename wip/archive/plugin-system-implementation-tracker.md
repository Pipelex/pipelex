> **ARCHIVED 2026-06-21.** This tracked the in-`pipelex` plugin-system work (Phases 0–5: invert every core↔integration seam, then externalize Temporal to the private `pipelex-temporal` plugin). Phases 0–4 are complete and committed; Phase 5's local cut-over is done, with only the publish/release-gated downstream pin-flips outstanding. The active tracker is now [`../../TODOS.md`](../../TODOS.md) — the **consumer-side** migration (orchestrator-agnostic `pipelex-api` base + deployment flavors). Kept here for the as-built history and the decision log (D1–D9).

# Pipelex plugin system — implementation TODOS

**Branch:** `refactor/Plugins-2` (worktree `_plugins`) · **Status:** Phases 0–3 complete + **Option A landed** (post-Phase-3). Phase 3 (orchestrators through the seam) = `5f61db323`. **Option A** — drop the CLI-command harvest entirely; Temporal `worker`/`setup-namespace` → standalone `pipelex-temporal` console script — = commit **`989c9beed`**; all gates green (`make agent-check`, `make tb`, `make agent-test` "All tests passed", Temporal suite **156 passed / 4 xpassed**, both `--help` smokes). The former **D3 is superseded** (see D1–D7). Full as-built + open follow-ups: [`wip/plugins/option-a-drop-cli-command-seam.md`](wip/plugins/option-a-drop-cli-command-seam.md) and the **Option A — as-built** note in the log below. **Phase 4 done** (model_lists, the 5th seam, per D6 — full record in `### Phase 4 — as-built` below; all gates green, committing at this checkpoint). With it, **core names no integration across every enumerated seam**; three pre-existing *unenumerated* core→vendor couplings remain, dispositioned in [`wip/plugins/phase-4-residual-core-vendor-couplings.md`](wip/plugins/phase-4-residual-core-vendor-couplings.md). **Phase 5 Step 0b (C6) DONE** — the Temporal config *schema* relocated out of `pipelex.temporal` into core (`pipelex/system/configuration/config_temporal.py` + its two exceptions in `…/exceptions.py`); `configs.py` no longer imports `pipelex.temporal` (**the last hard core→temporal import is gone**). In-`pipelex`, behavior-neutral (byte-equivalent exception semantics), zero cross-repo blast radius; all gates green (`make tb` · `make agent-check` · `make agent-test` "All tests passed"). Record in `### Phase 5 — Step 0b (C6) as-built` below. **Phase 5 LOCAL cut-over DONE = 2026-06-20** (user go/no-go for the reversible local work only): `pipelex-temporal` scaffolded + populated (top-level `pipelex_temporal`, D8) + **green** (`agent-check` 0/0, `agent-test` "All tests passed"); **core green without temporal** (`agent-check` clean, `tb` green, full `agent-test` 7678 passed); Option-A config-loader dead code removed; docs hygiene (install instructions → `pipelex-temporal`). Downstream pin flips **DEFERRED — publish/release-gated** (cut-list in the `### Phase 5 — cross-repo cut-over as-built` note). Local commits both repos, **NOT pushed**. **Next = downstream wiring** — **CORRECTION 2026-06-21: `pipelex-temporal` is PRIVATE / not-open-source → NOT PyPI.** It's distributed by a pinned `git+ssh` ref (precedent: `pipelex-shared @ git+ssh://…/infra-python-tools.git@<ref>` in `pipelex-platform`). Forced split: public MIT consumers (`pipelex-api`, `pipelex-mistralai-workflows`) **DROP** the `temporal` extra; only **private** infra pins `pipelex-temporal` via git+ssh: `pipelex-worker` **and `pipelex-api-hosted`** (confirmed 2026-06-21 — the hosted runner enqueues Temporal, so its child image needs the client too). Core `pipelex` stays public → normal release. Gated on the **hosted-Temporal rollout**; **user chose to DEFER all wiring (docs-only)** 2026-06-21. **Finalize-local pass (session 2, 2026-06-20):** core cleaned of the moved Temporal dev-tooling (both `temporal-e2e-validate` *and* the not-previously-listed `temporal-test-crate` skills relocated to `pipelex-temporal`; dead Makefile temporal targets removed), `pipelex-temporal` additions-side `/code-review` → **SHIP/clean**, review NITs triaged (stray `.pipelex/traces` untracked+gitignored; `test_extras→tests` back-import deferred), all gates green both repos; **local, uncommitted, still paused before publish.** Record: [`wip/plugins/phase-5-cutover-review-followups.md`](wip/plugins/phase-5-cutover-review-followups.md) → *Finalize-local pass*.

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
| ~~Model listing (5th seam)~~ | `cogt/model_backends/model_lists.py` | **INVERTED — Phase 4.** `match sdk` → `get_model_lister_registry().get_optional(sdk=…)`; each backend plugin registers an optional `ListModelsFn` via `add_model_lister`. File names no integration. |
| Orchestrator dispatch | `runtime_bridge/bridge.py` (`match` ~`:147`, `_run_mistral_native` `:408`, `_run_direct` `:270`, `_run_temporal_*` `:297/:330`) | `match execution_mode:` → hard Mistral import + lazy Temporal + per-mode install messages |
| Boot/teardown hub swap | `pipelex.py` (~`:377-479`) | four `if get_config().temporal.is_enabled:` blocks + inlined teardown |
| ~~Config~~ | `system/configuration/configs.py:14` | **RELOCATED — Phase 5 Step 0b (C6).** Schema → `pipelex/system/configuration/config_temporal.py`; its two exceptions (`TemporalConfigError`, `WorkerTaskQueueUnknownError`) → `pipelex/system/configuration/exceptions.py` (re-based on `PipelexError`, byte-equivalent). `configs.py` imports from core — the one hard `pipelex.temporal` import in core config is gone. |
| ~~CLI~~ | `pipelex/temporal/temporal_cli.py` | **REMOVED — Option A.** No CLI-command seam/harvest at all; Temporal's `worker` + `setup-namespace` ship as the standalone `pipelex-temporal` console script ([doc](wip/plugins/option-a-drop-cli-command-seam.md)). |
| Naming overload | `plugins/{plugin,plugin_manager,plugin_sdk_registry,plugin_factory_abstract}.py`, `hub.py` `"PluginManager2 is not initialized"` | three-way "plugin" overload to kill |

**Locked decisions (D1–D7)** — do not re-litigate, see plan for full text:

- **D1** — inference factory = a typed callable `MakeWorkerFn`, not a one-method Protocol object (kills ~30 classes).
- **D2** — Phase 1 PR = seam machinery **merged** with the LLM family (contract meets a real backend before locking).
- **D3** — ~~plugin CLI commands harvested by running the pure `build_registrar` at CLI-build~~ **SUPERSEDED → Option A** ([`wip/plugins/option-a-drop-cli-command-seam.md`](wip/plugins/option-a-drop-cli-command-seam.md), landed post-Phase-3): the CLI-command *contribution path* was **removed**, not hardened. Temporal's `worker` + `setup-namespace` are now a standalone `pipelex-temporal` console script (`[project.scripts]`), so `pipelex --help` no longer loads config or scans entry points and a broken/colliding plugin can't brick the host CLI. The inference-backend / orchestrator / boot-slot seams and `pipelex plugins list` are **unchanged**; `add_cli_command` / `CliCommand` are gone from the registrar. Downstream `pipelex-worker` Dockerfile/Makefile flip is release-gated (see the plan's cross-repo section).
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

- [x] `DirectOrchestrator.run` from `_run_direct` → `runtime_bridge/direct_orchestrator.py`. **Landmine kept verbatim:** `with scoped_pipe_router(PipeRouter())`. Registered in core by `plugins/direct/direct_plugin.py` (`name="direct"`, in `CORE_UNCONDITIONAL_PLUGIN_NAMES`).
- [x] `TemporalBlockingOrchestrator` / `TemporalFireAndForgetOrchestrator` from `_run_temporal_*` → `temporal/temporal_orchestrators.py`, keeping the `WorkflowExecutionError` catch + `make_workflow_id` recompute. Each `run` first calls `_require_temporal_extra(mode=...)` (find_spec → `MissingOrchestratorError` if the extra is absent).
- [x] (`MistralWorkflowsOrchestrator` authored in `pipelex-mistralai-workflows` — Phase 5.)

**Bridge + Mistral:**

- [x] Collapsed the bridge `match` → `get_orchestrator_registry().get_optional(mode=...)` → `orchestrator.run`, else `MissingOrchestratorError(mode)`. `bridge.py` names no integration (only docstrings/comments mention temporal/mistral). Serialize helpers extracted to `runtime_bridge/serialization.py` (breaks the `bridge→bootstrap→pipelex` cycle that the orchestrators would otherwise re-form); `serialize_pipe_output` re-exported from bridge for back-compat.
- [x] **Per-mode error quality (C7):** `MissingOrchestratorError(*, mode)` maps mode→exact message via match/case (temporal modes → `pip install 'pipelex[temporal]'`; mistral → `pip install pipelex-mistralai-workflows`; direct → boot-problem msg). `_authors_caller_facing_message=True`.
- [x] **Mistral → discovery:** the `_run_mistral_native` hard import is gone. MISTRAL_NATIVE has no in-core orchestrator → registry miss → `MissingOrchestratorError(MISTRAL_NATIVE)`. Suite proves dispatch with a fake orchestrator (`test_orchestrator_dispatch.py`).

**The Temporal plugin (`temporal/temporal_plugin.py`), its `register`:**

- [x] **always** `add_orchestrator(TEMPORAL_BLOCKING|TEMPORAL_FIRE_AND_FORGET, …)` + `add_cli_command(worker|setup-temporal-namespace, import_path=…)`.
- [x] **if `config.temporal.is_enabled`:** `claim_content_generator|task_manager|pipe_router|pipe_run(thunk)` + `add_teardown(thunk)` — each a module-level zero-arg thunk that lazy-imports `temporalio`; `register` imports no temporalio (proven by the import-light guard with `is_enabled=True`).

**Boot/teardown collapse (C8 — explicit injection precedence):**

- [x] The four `if temporal.is_enabled:` boot blocks → `_resolve_hub_slot(slot, default)` (generic over `_HubSlotImplT`) at each ordered point. Precedence: explicit `setup()` param > slot-claim thunk > core default. TASK_MANAGER runs its thunk (full temporal-hub wiring); no core default/param. Pinned by `test_hub_slot_injection_precedence.py`.
- [x] The inlined teardown → registered teardown callbacks run **LIFO** (`for cb in reversed(self._plugin_registrar.teardown_callbacks)`). `pipelex.py` teardown names no integration. `temporal_hub.get_optional_task_manager()` added so the temporal teardown thunk re-fetches the tm.

**CLI collapse (C4 + D3):**

- [x] The two hard temporal-command imports + static registrations + hardcoded `list_commands` entries are gone. `_cli.py` harvests plugin commands at module load via `build_registrar` (`_register_discovered_cli_commands`), importing each `import_path` lazily; `list_commands` returns `_CORE_COMMAND_ORDER + _PLUGIN_COMMAND_NAMES`.
- [x] CLI-build config load is side-effect-free (`config_manager.load_config(ensure_global_if_missing=False)`, new param) with a bulletproof `load_base_config_dict()` fallback so a broken/absent user config can't brick `--help`/`init`. D5 thunks ⇒ harvest constructs no temporal impl (proven: `worker` harvested with temporalio import-blocked).

**SPI:**

- [x] Orchestrator SPI published: `docs/under-the-hood/orchestrator-plugins.md` (seam, contract, boot-orchestrator slot claims, injection precedence, CLI-by-import-path, the SPI module/symbol table from design §9.2, the Temporal worked example, out-of-tree authoring) — added to both mkdocs nav blocks. `MissingOrchestratorError` added to `runtime_bridge/exceptions.py`; `MissingPipelexTemporalExtraError` + `MissingMistralWorkflowsPluginError` removed (error pages regenerated).

**Tests:**

- [x] Bridge dispatch by mode (fake orchestrator) — `test_orchestrator_dispatch.py`.
- [x] **Per-mode error parity** — `test_orchestrator_dispatch.py` (per-mode miss) + `test_exceptions_disclosure.py` (per-mode hint survives STRICT).
- [x] DIRECT router scoping (`test_direct_router_scoping.py`, unchanged + green) + DIRECT parity (`test_dispatch.py`, `test_bridge_direct.py`).
- [x] **Injection-precedence** (explicit param wins over slot claim — C8) — `test_hub_slot_injection_precedence.py`.
- [x] Boot-via-slots (temporal-enabled → content-generator slot resolves to `ContentGeneratorInWorkflow`) — existing `test_keyless_boot_forced_dry.py::test_keyless_temporal_boot_*` (green through the new seam) + slot-claim arm in the precedence test; teardown LIFO pinned there.
- [x] **CLI-command contribution** (`worker`/`setup-temporal-namespace` harvested, in order) — `test_plugin_cli_command_harvest.py`. Import-light guard extended with `temporalio` + `is_enabled=True` slot-claim arm.
- [x] **Full Temporal suite green in-tree** (§14.5 — the extraction gate) — `.venv/bin/pytest tests/integration/pipelex/temporal/` → **156 passed, 4 xpassed** (the xpassed are pre-existing xdist class-registration flakiness markers, unrelated to this phase); also green inside the full `make agent-test`.

### 🛑 CHECKPOINT 3 — hard stop (THE gate before externalization)

- [x] **Verify:** `make agent-check` clean · `make agent-test` green ("All tests passed", exit 0) · **full Temporal suite green through the seam** (`.venv/bin/pytest tests/integration/pipelex/temporal/` → 156 passed, 4 xpassed). bridge + boot/teardown + CLI name **no** integration (only docstrings/comments mention temporal/mistral; dispatch/boot/teardown go via the registry + slot thunks + config).
- [x] **Capture cold-start context:** `### Phase 3 — as-built` note above — dispatch seam, verbatim extractions, the cycle-break (serialization.py + `import_path` CLI), injection-precedence ordering + where slot thunks apply, the CLI harvest mechanism, the orchestrator SPI doc, and the §14.5 green evidence.
- [x] **Fan-out `/code-review`:** `pr-review-toolkit:code-reviewer` reviewed the full Phase 3 diff against `HEAD` — **clean, no BLOCKERs**; byte-equivalence + all landmines verified. S1/N1/N2 applied, N3 deliberate (see the CHECKPOINT-3 `/code-review` note in the as-built).
- [x] **Commit:** checkpoint commit `19e6ca66b` on `refactor/Plugins-2` (one-commit-per-checkpoint delivery model). **Do NOT begin Phase 5** until this Temporal-green gate is recorded (it is, above). Phase 4 (model_lists) may start next.

---

## Phase 4 — Invert model listing (the 5th seam, per D6)

**Goal:** close the goal. `model_lists.py`'s `match sdk:` (the `list-models` CLI path) still hardcodes `pipelex.plugins.{openai,anthropic,mistral,google,bedrock}.*_list` imports. Invert it so core names no integration *anywhere*. Own PR.

- [x] Add a **model-listing capability** to the inference contract: `add_model_lister(*, sdk, lister: ListModelsFn)` (callable mirroring `MakeWorkerFn` — import-light, lazy). A backend plugin that lists models registers its lister alongside its worker factory.
- [x] Collapse `ModelLister.list_models` (`model_lists.py`) to a registry lookup keyed by `sdk`; a miss → the same friendly "is its plugin installed?" guidance. Move the `find_spec` guards (already in this file) into each lister.
- [x] The contract grows by one **optional** method — backends without listing simply don't register a lister (progressive disclosure preserved).

**Tests:**

- [x] Round-trip (a registered lister is invoked for its `sdk`).
- [x] A backend with no lister → the friendly miss.
- [x] Import-light subprocess guard still green (listers are lazy).

### 🛑 CHECKPOINT 4 — hard stop ("core names no integration" holds without an asterisk)

- [x] **Verify:** `make agent-check` clean (pyright 0 over 2243 files / mypy 0 / keyword-only pass) · `make agent-test` green ("All tests passed.") · targeted plugins+cogt suite 715 passed. `model_lists.py` names no integration; the final sweep returns only **pre-existing, out-of-scope** vendor refs (`config_cogt.py` typed config = by-design D7; `img_gen_args_factory.py` + `backend_factory.py` = genuine but unenumerated couplings) — captured in [`wip/plugins/phase-4-residual-core-vendor-couplings.md`](wip/plugins/phase-4-residual-core-vendor-couplings.md). No dispatch-path leak remains.
- [x] **Capture cold-start context:** `### Phase 4 — as-built` note below.
- [x] **Fan-out `/code-review`:** `pr-review-toolkit:code-reviewer` reviewed the Phase 4 working-tree diff against HEAD. **Verdict: byte-equivalent and clean — no BLOCKER / no SHOULD-FIX.** It walked all five correctness questions against `git show HEAD:…model_lists.py` and confirmed: each lister's kwargs match its old `match` arm (mistral's no-`backend` + sync `# noqa: RUF029`, bedrock sync, the rest async); the deleted `find_spec` guards survive **byte-for-byte** inside each `list_*_models` fn (same lib/extra/message; openai has none in old or new); the anthropic `AnthropicSDKUnsupportedError`→`ModelListingUnsupportedError` translation is correct and core imports no anthropic symbol; `any_listed` threads identically (not set on the unsupported `continue`); the registered sdk keys are exactly the old arms' set. Plus import-light, `get_optional`-vs-`lookup`, keyword-only, and the Case-2 boundary (with `except PipelexCLIError: raise` ordering preserved so internal auth `PipelexCLIError`s aren't re-wrapped). One **NIT** (doc recommended `require_sdk` while the built-in listers reuse their `list_*_models` inline `find_spec` guard) — **applied**: the "Listing models" doc section now tells one story (recommends `require_sdk`, notes the built-ins reuse the existing inline guard). The wip residual-couplings doc was confirmed accurate. A follow-up **xhigh workflow `/code-review`** (10 finder angles → adversarial verify) re-confirmed byte-equivalence and surfaced reuse/altitude follow-ups: the two cheap ones were **applied** (a shared `PluginRegistrar._add` helper mirroring `_claim`; the hardcoded item-counts removed from this as-built), the four design-tradeoffs **deferred** — all recorded in [`wip/plugins/phase-4-review-followups.md`](wip/plugins/phase-4-review-followups.md).
- [x] **PR:** checkpoint commit on `refactor/Plugins-2` (one-commit-per-checkpoint). Phases 0–4 complete — the in-`pipelex` work is done.

---

## Phase 5 — Externalize Temporal → `pipelex-temporal` (cross-repo, GATED on Checkpoint 3)

**Goal:** lift `pipelex/temporal/` into a separate dist. A *packaging* move — but only after a prerequisite the design missed. **Cross-repo; the only phase that can break downstream deploys. Separate effort.**

> **Destination repo exists.** The user created an **empty** `pipelex-temporal` repo (sibling dir at `../pipelex-temporal`, remote `git@github.com:Pipelex/pipelex-temporal.git`, branch `main`, **no commits / no scaffolding** yet) ahead of this phase, so the move has a target from the first commit. **Do this in a fresh session** (cross-repo; not a normal in-`pipelex` checkpoint).
>
> **Progress:** the in-`pipelex` prerequisite **Step 0b (C6) is DONE** (committed; behavior-neutral; gates green). What remains is the **cross-repo cut-over** — Step 0a (scaffold the empty repo), the breaking move of `pipelex/temporal/` out, the downstream pin flips, and publishing. Those are outward-facing/deploy-breaking and were intentionally **paused for user go/no-go** after Step 0b.

> **Cut-over in progress (local-only, paused before publish — user go/no-go given 2026-06-20 for the *reversible* local work; publish/merge/deploy still gated).** Two foundational decisions locked this session:
> - **D8 — package layout = top-level `pipelex_temporal`** (NOT a `pipelex.temporal` namespace stitch). Rationale: `pipelex` is a *regular* package (owns `pipelex/__init__.py`, hatchling `packages=["pipelex"]`), so two wheels can't cleanly co-own `pipelex/`; the family convention is top-level (`pipelex-api`→`api`, the existing plugin→`pipelex_mistralai_workflows`); and two *editable* installs both mapping into `pipelex/` is fragile, which would break the local cross-pin testing this scope needs. Cost: mechanical `pipelex.temporal.*` → `pipelex_temporal.*` rewrite across the moving code + its tests (which travel anyway) + ~9 import lines in `pipelex-mistralai-workflows` tests + the entry point. Supersedes the design's "keep the import path / lowest-churn" lean (written before the regular-package packaging reality was confronted).
> - **D9 — scaffold tool-configs are sourced from `pipelex`'s own `pyproject.toml`** (ruff/pyright/mypy/pytest/coverage — the moved code passes these verbatim today), while repo *shape* (Makefiles/, metadata, `.gitignore`, LICENSE, family feel) mirrors `pipelex-api`. Avoids lint churn on the moved code.
>
> **Recon facts (three agents, 2026-06-20):** core→temporal coupling is a *single* hard import (`pipelex/plugins/builtins.py:18,40` → `TemporalPlugin`); everything else core-side is config (`temporal: Temporal` field, `[temporal]` toml, `--temporal/--no-temporal` flags) that correctly stays. temporal→core spans ~46 modules (`cogt.*`, `core.*`, `runtime_bridge.*`, `pipe_run.*`, `pipeline.*`, `hub`, `tools.*`) ⇒ `pipelex-temporal` depends on base `pipelex`. Downstream: `pipelex-worker` = pin + `pipelex worker` CLI (no temporal imports); `pipelex-mistralai-workflows` = `temporal` extra + ~9 `pipelex.temporal.*` test imports; `pipelex-api-hosted` = config-only wrapper, **no Python pin** (temporal reaches it through the publish-gated `pipelex-api` image). `pipelex-api` itself pins `pipelex[…,temporal]==X` — a publish-gated flip, out of this local scope.
>
> **Local cross-pin strategy:** `pipelex-temporal` depends on editable `pipelex` via `[tool.uv.sources] pipelex = { path = "../_plugins", editable = true }` (mirrors how `pipelex-mistralai-workflows` pins `../_workflows`); downstream repos pin editable `../pipelex-temporal`. The published `==Y` pins are the publish-time flip (deferred). Order constraint: drop the `pipelex-temporal` console script from `_plugins/pyproject.toml` **before** any `uv sync` in the new repo (else two `pipelex-temporal` scripts collide).

- [x] **Step 0a — scaffold `pipelex-temporal` to match the sibling Python repos' conventions. ✅ DONE** (D9; see cut-over as-built). Don't invent a new toolchain — mirror the habits already used across the workspace's Python repos (`pipelex-platform` / `pipelex-admin-api` / `pipelex-api` are the references): same Makefile targets (`agent-check`, `agent-test`, `format`, `lint`), ruff (format + lint) + pyright + mypy strict, pytest layout, `uv` for deps, hatchling build backend, the standard `pyproject.toml` shape + CHANGELOG. The scaffold should feel like it belongs in the family before any Temporal code lands in it.
- [x] **Step 0b — relocate the Temporal config schema to a core-owned module (codex C6 — the prerequisite). ✅ DONE** (in-`pipelex`, behavior-neutral, committed at this checkpoint). Schema → `pipelex/system/configuration/config_temporal.py`; the two exceptions it needs (`TemporalConfigError`, `WorkerTaskQueueUnknownError`) → `pipelex/system/configuration/exceptions.py`, re-based on `PipelexError` (byte-equivalent: same `error_domain=None`, `ValueError` mixin intact, subclasses preserved). All importers repointed; `configs.py:14` imports from core; the `if TYPE_CHECKING: … RetryPolicy = Any` placeholder kept. Gates green (`make tb` · `make agent-check` pyright 0/mypy clean · `make agent-test` "All tests passed"); zero external importers of the moved symbols. Full record + the now-fixed `(ValueError, PipelexError)` `.message` latent bug (reordered to `(PipelexError, ValueError)` in an `xhigh`-review follow-up): `### Phase 5 — Step 0b (C6) as-built` below. *(Was: low-risk, could be pulled into Phase 3.)*
- [x] Move `pipelex/temporal/` (impl) + `temporal_plugin.py` + tests + the `temporal` marker + the `--temporal-server` conftest option into `pipelex-temporal`; declare `[project.entry-points."pipelex.plugins"]`. **✅ DONE** (top-level `pipelex_temporal`, D8).
- [x] Keep protocol-level conformance tests in core; Temporal's behavioral suite travels. **✅ DONE** (incl. the 5 mixed-test splits + 2 config tests kept in core — see cut-over as-built).
- [ ] **Flip downstream pins** (cross-repo blast radius): `pipelex-worker`, `pipelex-api-hosted` from `pipelex[temporal]==X` → `pipelex-temporal==Y`. **⏸ DEFERRED — publish/release-gated** (precise cut-list in the cut-over as-built; per Option-A the `pipelex-worker` flip lands in the same commit as the release pin bump).
- [ ] **Repoint `pipelex-mistralai-workflows`** (design §15): its `temporal` extra + `pipelex.temporal.*` imports → `pipelex-temporal`. **⏸ DEFERRED — publish-gated + coordinate with that repo's in-flight mistralai-2.x work.**

**Tests:**

- [ ] Re-run the relocated Temporal suite against published `pipelex`.
- [ ] Run downstream consumers' suites against the new pins **before** publishing.

### 🛑 CHECKPOINT 5 — hard stop (final)

- [ ] **Verify:** Temporal is an external plugin; core has no `temporal` extra; downstream pins flipped; consumer suites green.
- [ ] **Capture cold-start context:** `### Phase 5 — as-built` note — the published `pipelex-temporal` version, the pins flipped in each downstream repo, and the consumer-suite green evidence.
- [ ] **Fan-out `/code-review`:** core *deletion* side reviewed (session 1, on `a8382d1a1`); `pipelex-temporal` *additions* side reviewed (session 2) → **SHIP/clean** (no BLOCKER/SHOULD-FIX; wheel built offline, pin-no-leak + import-light proven at runtime). 2 NITs triaged (traces fixed; `test_extras→tests` back-import deferred). Remaining: re-review downstream pin-flip diffs at publish. Triage: [`wip/plugins/phase-5-cutover-review-followups.md`](wip/plugins/phase-5-cutover-review-followups.md).
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

### Phase 3 — as-built

**Status:** done, checkpoint commit `19e6ca66b` on `refactor/Plugins-2`. `make agent-check` clean (ruff/plxt, **pyright 0**, mypy 0 over 2239 files, keyword-only pass) · `make tb` green · **full `make agent-test` green** ("All tests passed", exit 0) · **Temporal integration suite green** (`tests/integration/pipelex/temporal/` → 156 passed) · `/code-review` clean (no BLOCKERs; S1/N1/N2 applied).

**The dispatch seam.** `bridge.py`'s `match execution_mode:` is gone. `run_pipe_via_bridge` now does `get_orchestrator_registry().get_optional(mode=…)` → `orchestrator.run(...)`, else `MissingOrchestratorError(mode=…)`. `bridge.py` names no integration (only docstrings/comments). `build_pipe_job_from_input`, `_validate_input`, `_decode_*` stay; `serialize_pipe_output` is re-exported (`# noqa: F401`/`TC001`) for host-runtime back-compat.

**Orchestrators (verbatim extraction):**

- `runtime_bridge/direct_orchestrator.py::DirectOrchestrator` — body of the old `_run_direct`, **`scoped_pipe_router(PipeRouter())` landmine kept verbatim**. Core, always-on.
- `temporal/temporal_orchestrators.py::TemporalBlockingOrchestrator` / `TemporalFireAndForgetOrchestrator` — bodies of `_run_temporal_*`, lazy `temporalio`/`make_temporal_pipe_run`/`WorkflowExecutionError` inside `run`; each `run` first calls `_require_temporal_extra(mode=…)` (`importlib.util.find_spec("temporalio")` → `MissingOrchestratorError` on absence — no relabelling of deeper import bugs).

**Cycle break (the one non-obvious structural move).** Two extractions were forced by `reportImportCycles` (pyright counts **function-level** imports too — verified empirically; lazy-import does NOT break a pyright cycle, only a runtime one):

1. `runtime_bridge/serialization.py` — `PIPE_DISPATCH_ERRORS`, `serialize_pipe_output`, `resolve_main_stuff_root_key`, `serialize_completed_output` (import-light: core memory + pipe/pipeline exceptions + payloads). Both DIRECT and Temporal orchestrators serialize through it, so they never import `bridge.py` (which would re-form `bridge→bootstrap→pipelex→discovery→builtins→orchestrator→bridge`).
2. **CLI commands declared by `import_path` string, not by importing the callable.** A builtin Temporal plugin contributing `worker`/`setup-temporal-namespace` (whose modules boot Pipelex) would cycle `builtins→temporal_plugin→worker_cmd→pipelex→discovery→builtins`. Fix: `CliCommand.command: Callable` → `CliCommand.import_path: str` (`"module:attr"`); `_cli.py` resolves it via `importlib.import_module` at harvest (dynamic ⇒ off pyright's static graph). The two command modules are unchanged from `main`. Temporal stays a **builtin** (not an entry point) — the plan's Phase-3 intent.

**Plugins:** `plugins/direct/direct_plugin.py::DirectOrchestratorPlugin` (`name="direct"`) + `temporal/temporal_plugin.py::TemporalPlugin` (`name="temporal"`) added to `BUILTIN_PLUGINS`; `CORE_UNCONDITIONAL_PLUGIN_NAMES = {"direct", "openai"}`. `TemporalPlugin.register`: always two `add_orchestrator` + two `add_cli_command(import_path=…)`; iff `registrar.config.temporal.is_enabled`, four `claim_*` thunks + `add_teardown` (all module-level zero-arg thunks lazy-importing temporalio).

**Boot/teardown (`pipelex.py`):** the four `temporal.is_enabled` blocks → injection-precedence at each ordered point via `_resolve_hub_slot(*, slot, default: Callable[[], _HubSlotImplT]) -> _HubSlotImplT` (explicit param > slot thunk > core default). TASK_MANAGER just runs its thunk (full temporal-hub wiring inside it). `teardown` runs `reversed(self._plugin_registrar.teardown_callbacks)` (LIFO) in place of the old temporal block. `_temporal_task_manager` attribute removed; `_plugin_registrar` now declared `PluginRegistrar | None` in `__init__` and assigned via a local in `setup` (narrowing). `temporal_hub.get_optional_task_manager()` added (+ `teardown()` promoted onto the `TaskManager` protocol with `@override` on the impl).

**CLI (`_cli.py`):** `_CORE_COMMAND_ORDER` (core block) + harvested `_PLUGIN_COMMAND_NAMES`; `list_commands` returns their concatenation. `_register_discovered_cli_commands()` runs `build_registrar(config=_config_for_cli_harvest())` at module load and `app.command(...)`-registers each resolved callable. `_config_for_cli_harvest` = `load_config(ensure_global_if_missing=False)` (new side-effect-free param) with `(TomlError, ValidationError)` → `load_base_config_dict()` fallback (new method; package-default only, always valid).

**Exceptions:** `MissingOrchestratorError(*, mode)` (mode→message match/case, `_authors_caller_facing_message=True`) replaces `MissingPipelexTemporalExtraError` + `MissingMistralWorkflowsPluginError` (both removed). `pipelex-dev generate-error-pages` regenerated `docs/errors/` (the two old pages removed, `missing-orchestrator-error.md` added; also picked up `inference-backend-not-found-error.md` from CP2).

**Tests:** new `test_orchestrator_dispatch.py` (fake-orchestrator dispatch + per-mode miss parity), `test_hub_slot_injection_precedence.py` (explicit>slot>default at content-generator/pipe-router + teardown LIFO, fake registrar via patched `build_registrar`), `test_plugin_cli_command_harvest.py` (worker/setup-temporal-namespace harvested, in order, after core). Updated: `test_dispatch.py` (mistral → `MissingOrchestratorError`), `test_exceptions_disclosure.py` (per-mode `MissingOrchestratorError`), `test_output_serialization.py` (import from `serialization`), `test_import_light_boot.py` (BLOCKED += `temporalio`; config stub gains `temporal.is_enabled=True` to exercise the slot-claim branch import-light), `test_inference_backend_coverage.py` + `test_plugin_discovery.py` (stub configs gain `temporal` so the now-builtin TemporalPlugin's `register` can read `config.temporal.is_enabled` — closes deferred-doc item 4 for these two tests). Boot-via-slots for the temporal content generator is already covered end-to-end by `test_keyless_boot_forced_dry.py` (green through the new seam).

**Deferred-doc items closed by Phase 3:** the three previously-unconsumed registrar menus are now wired — `cli_commands` (consumed by `_cli.py` harvest), `slot_claims` + `teardown_callbacks` (consumed by `pipelex.py` boot/teardown). So an external plugin contributing those is no longer silently inert.

**Notes for Phase 4/5:** Phase 4 (model_lists 5th seam) is independent. Phase 5 externalizes `pipelex/temporal/` → `pipelex-temporal`: the Temporal plugin + orchestrators + commands are already a self-contained unit behind the seam; the move is (a) relocate the Temporal config schema out of `pipelex.temporal` (codex C6 — `configs.py:14` still imports `pipelex.temporal.config_temporal`), then (b) ship `pipelex/temporal/` + declare the `pipelex.plugins` entry point in the new dist (today Temporal is an in-tree builtin, not yet an entry point). Gate: this CHECKPOINT-3 Temporal-green evidence.

**Post-checkpoint xhigh `/code-review` follow-ups (separate from the CHECKPOINT-3 reviewer pass above).** A later xhigh `/code-review` over the Phase 3 commit surfaced a dominant correctness cluster plus medium/low items, captured for triage:

- 🔴 **Critical — read before Phase 5 / before externalizing any plugin:** [`wip/plugins/phase-3-critical-cli-harvest-fragility.md`](wip/plugins/phase-3-critical-cli-harvest-fragility.md). The import-time CLI plugin-command harvest (D3) is an unguarded surface: a broken/incompatible/colliding **external** plugin or an unreadable user config can brick *every* `pipelex` command — including the `--help`/`doctor`/`plugins`/`init` recovery commands — and `add_cli_command` has no collision guard, so a plugin can silently shadow a core command (`run`, …). Latent for in-tree-only installs (suite green), live the moment Phase 5 ships an external dist. **Cold-start problem statement only — solution to be explored in a fresh session.**
- 🟡 **Medium/low deferred items → [`wip/plugins/phase-3-review-deferred.md`](wip/plugins/phase-3-review-deferred.md):** the misleading `MISTRAL_NATIVE` "install a package you already have" hint (dead mode until the Mistral plugin lands), the bridge dropping its orchestrator error-wrap (external-orchestrator contract), `teardown()` with no `try`/`finally`, `_teardown_temporal` re-fetching from the global hub, the wrong SPI doc about Temporal entry-point discovery, an enum identity comparison, double-discovery/import-time cost (coupled to the critical fix), a dead `serialize_pipe_output` re-export, and a hardcoded slot count.

#### CHECKPOINT-3 `/code-review` (pr-review-toolkit:code-reviewer, on the Phase 3 working-tree diff)

**Verdict: clean — no BLOCKERs.** The reviewer compared every extracted body against `git show HEAD:…bridge.py` and confirmed **byte-equivalence** of all four orchestrator bodies (modulo the `_PIPE_DISPATCH_ERRORS`→`PIPE_DISPATCH_ERRORS` rename + the added `_require_temporal_extra` guard) and verified all named landmines: DIRECT `scoped_pipe_router` preserved, temporal-blocking `make_workflow_id` recompute + `WorkflowExecutionError` catch verbatim, per-mode error parity (exact deleted hint strings, `_authors_caller_facing_message=True`), injection precedence (explicit>slot>default at all four points), import-light (no module-top temporalio; register reads only `config.temporal.is_enabled`), CLI determinism, teardown LIFO + no-integration.

Applied: **S1** (the one should-fix) — added `test_harvest_config_falls_back_to_base_on_broken_user_config` pinning the malformed-user-config fallback in `_config_for_cli_harvest` (named Phase-3 risk #6, previously untested); **N1** — fixed the two stale `runtime_bridge.bridge._run_direct` doc references in `bundle_validator.py` → `runtime_bridge.direct_orchestrator.DirectOrchestrator.run`; **N2** — re-anchored the harvest-order test on "plugin commands are the last registrations" (`names[-2:]`) rather than the brittle `which` positional. **N3** (unused `OrchestratorRegistry.has`/`.modes`) left as a deliberate read-API symmetry surface mirroring `InferenceBackendRegistry`. The reviewer also confirmed the `if pipe_router:`-truthy vs `if content_generator is None:` asymmetry is **pre-existing** (identical in HEAD), not a Phase-3 regression.

### Option A — as-built (post-Phase-3, commit `989c9beed`)

**Status:** done. `make agent-check` clean (pyright 0 / mypy 0 over 2240 files / keyword-only) · `make tb` green · `make agent-test` "All tests passed." · `pytest tests/integration/pipelex/temporal/` → **156 passed, 4 xpassed** (the 4 xpassed = pre-existing xdist class-registration flakiness markers, matching the Phase-3 baseline) · both `--help` smokes pass. Full record + rationale: [`wip/plugins/option-a-drop-cli-command-seam.md`](wip/plugins/option-a-drop-cli-command-seam.md).

**Why.** The post-Phase-3 xhigh review found a critical fragility: the Phase-3 CLI-command harvest (the former D3) ran `build_registrar` at *import* of `pipelex/cli/_cli.py` on **every** `pipelex` invocation, so a broken/colliding external plugin or an unreadable user config could brick every command — including the `--help`/`doctor`/`plugins`/`init` recovery commands — and `add_cli_command` had no collision guard, so a plugin could silently shadow a core command. **Option A resolves it by removing the surface, not hardening it.** CLI commands are not a plugin contribution type any more.

**What changed:**

- **New:** `pipelex/temporal/temporal_cli.py` — a grouped `typer.Typer()` app registering `worker` + `setup-namespace`; `pipelex-temporal = "pipelex.temporal.temporal_cli:app"` in `pyproject.toml` `[project.scripts]`. Import-light at module top (callables pull `temporalio` lazily).
- **Moved (git renames):** `pipelex/cli/commands/worker_cmd.py` → `pipelex/temporal/worker_cmd.py`; `…/setup_temporal_namespace_cmd.py` → `pipelex/temporal/setup_namespace_cmd.py` (callable `setup_temporal_namespace_cmd` → `setup_namespace_cmd`). They now travel with Temporal into Phase 5.
- **Removed:** the harvest in `_cli.py` (`_config_for_cli_harvest`, `_register_discovered_cli_commands`, `_PLUGIN_COMMAND_NAMES`; `list_commands` now returns `list(_CORE_COMMAND_ORDER)`); `add_cli_command` + `CliCommand` + `cli_commands` in `plugins/registrar.py`; the two `add_cli_command` calls in `temporal/temporal_plugin.py` (docstrings rewritten; the hardcoded "four hub slots" count also dropped while there).
- **Strings/docs:** `PIPELEX_SETUP_CLI_COMMAND` + all docstrings/examples → `pipelex-temporal setup-namespace` / `pipelex-temporal worker`; 5 distributed-execution docs swapped; `docs/under-the-hood/orchestrator-plugins.md` CLI section rewritten ("Operational commands ship as console scripts") + SPI table + worked-example + the factually-wrong "self-entry-point" claim fixed; `docs/errors/search-attribute-registration-error.md` regenerated (not hand-edited).
- **Tests:** deleted `test_plugin_cli_command_harvest.py`; added `tests/unit/pipelex/temporal/test_temporal_cli.py` (console-script smoke); updated `test_setup_temporal_namespace_cmd.py` (import + use-site mock targets + callable); fixed `test_cli_entrypoint_smoke.py` (dropped the now-invalid `pipelex worker --help` case) and `test_search_attribute_bootstrap_check.py` (assert the new string).

**Untouched (deliberately out of scope — do NOT unwind in later phases):** the four inference-family registry lookups, the bridge → `OrchestratorRegistry` dispatch, the `temporal.is_enabled` boot-slot claims + LIFO teardown, `build_registrar` / `BUILTIN_PLUGINS` / the `pipelex.plugins` entry-point group for *runtime* contributions, `pipelex plugins list`, the denylist.

**Decision lineage:** the former **D3** (harvest at CLI-build) is **superseded** by Option A (see the D1–D7 list). [`phase-3-critical-cli-harvest-fragility.md`](wip/plugins/phase-3-critical-cli-harvest-fragility.md) → RESOLVED-BY-REMOVAL; two items in [`phase-3-review-deferred.md`](wip/plugins/phase-3-review-deferred.md) (double-discovery/import-time cost; factually-wrong SPI doc) → resolved.

**Open follow-ups (NOT done):**

1. **Config-loader cleanup (flagged, low-risk):** `_config_for_cli_harvest` was the *sole* caller of `config_manager.load_base_config_dict()` and `load_config(ensure_global_if_missing=False)`. Both are now dead (the method has zero callers; the `False` branch is unreachable) in `pipelex/system/configuration/config_loader.py`. Left in place to keep Option A surgical — a follow-up should delete `load_base_config_dict()` and simplify `load_config` to always-ensure-global.
2. **Cross-repo, RELEASE-GATED (do NOT do ahead of the pipelex release shipping `pipelex-temporal`):** flip `pipelex-worker/Dockerfile` (`CMD ["pipelex","worker","--no-sandbox"]` → `["pipelex-temporal","worker","--no-sandbox"]`) and `pipelex-worker/Makefile` (`pipelex worker …` → `pipelex-temporal worker …`) in the **same** commit that bumps `pipelex-worker`'s `pipelex` pin to that release. `pipelex-api-hosted` / `sandbox` / `pipelex-api` were checked — they do **not** invoke the worker. Until that bump, the old pinned pipelex still has `pipelex worker`, so nothing breaks. (Mirror this into the Phase-5 downstream-pin step.)
3. **Legacy `pipelex/temporal/worker_cli.py`** (the `python -m pipelex.temporal.worker_cli` / `configure` entrypoint) is a unification candidate with the new `temporal_cli.py` — noted, not addressed.

**Env gotchas for the next session:** (a) `uv sync --all-extras` materializes the `pipelex-temporal` console script into `.venv/bin/`; it also brings the venv up to the already-committed `uv.lock` (which had drifted on `cryptography`/`mthds`) — `uv.lock` itself unchanged. (b) `make cleanderived` deletes the gitignored `tests/integration/pipelex/fixtures/_generated_model_sets.py`; run `make regenerate-test-models-quiet` (alias `rtm`) before `make agent-check` or pyright fails on the missing import.

### Phase 4 — as-built (the 5th seam: model listing)

**Status:** done (working-tree, pre-commit at time of writing). `make agent-check` clean (ruff/plxt, **pyright 0 over 2243 files**, mypy 0, keyword-only pass) · `make tb` green · **full `make agent-test` green** ("All tests passed.") · targeted `tests/unit/pipelex/plugins/` + `tests/unit/pipelex/cogt/model_backends/` → 715 passed. `model_lists.py`'s `match sdk:` is gone — `pipelex show models <backend>` now dispatches through a registry on the hub.

**The seam.** `cogt/model_backends/model_lists.py` `ModelLister.list_models` no longer branches on `match sdk:` with per-arm hardcoded `from pipelex.plugins.{openai,anthropic,mistral,google,bedrock}.*_list import …`. It now does `get_model_lister_registry().get_optional(sdk=sdk)` → `await lister(...)`, else (miss) → `unsupported_sdks`. The file names **no integration** (imports only `ModelListingUnsupportedError`/`ModelManagerError` from `cogt.exceptions`, `PipelexCLIError`, and the three hub getters).

**New module** `plugins/model_lister_registry.py` (mirrors `inference_backend_registry.py` / `orchestrator_registry.py`, dependency-free):
- `ListModelsFn: TypeAlias = Callable[..., Awaitable[None]]` — the uniform lister callable. Always `async` (the loop awaits it); import-light to reference, lazy inside. Call shape: `await lister(*, sdk, backend_name, backend, flat, any_listed)`.
- `ModelListerRegistry` keyed by `sdk` alone (listing is per-SDK, not per-`(family, sdk)`). `get_optional(*, sdk) -> ListModelsFn | None` (a miss is a **soft** "unsupported-for-listing" outcome, mirroring `OrchestratorRegistry.get_optional` — **not** the inference registry's raising `lookup`), `has`, `sdks`.

**Registrar** (`plugins/registrar.py`): new `add_model_lister(*, sdk, lister)` menu method + `model_listers: dict[str, ListModelsFn]` accumulator + `_model_lister_sources`. Duplicate `sdk` → `DuplicateModelListerError` naming both plugins. Contributions line `f"model lister {sdk}"` (so `pipelex plugins list` shows listers automatically).

**Exceptions:** `DuplicateModelListerError(PluginError)` in `plugins/exceptions.py`; **`ModelListingUnsupportedError(CogtError)`** in `cogt/exceptions.py` — the core soft signal the loop catches (carries `sdk`). `pipelex-dev generate-error-pages` wrote new pages (`duplicate-model-lister-error.md`, `model-listing-unsupported-error.md`) + the `inference-and-providers.md` index; the rest unchanged.

**Hub + boot:** `_model_lister_registry` field + `set_/get_model_lister_registry` + module-level `get_model_lister_registry()`. `pipelex.py setup()` builds `ModelListerRegistry(plugin_registrar.model_listers)` and sets it on the hub, right after the inference-backend registry. The `show models` CLI path boots Pipelex via `make_pipelex_for_cli(needs_inference=True)`, so the registry is always set before `list_models` runs.

**Vendor listers** — each of the 5 plugins grew one `async` lister closure that lazy-imports its `list_*_models` fn (`# noqa: PLC0415`) and registers it:
- `openai` → `_list_openai_models` for sdks `openai`, `azure_openai`, `openai_responses`, `azure_openai_responses` (one closure across those keys; async underlying).
- `anthropic` → `_list_anthropic_models` for `anthropic`. **The one non-trivial case:** the closure catches the vendor `AnthropicSDKUnsupportedError` and re-raises core `ModelListingUnsupportedError(sdk=…)` — so core names no Anthropic-specific symbol while preserving the old "bedrock-backed Anthropic client can't list → unsupported_sdks" behavior.
- `mistral` → `_list_mistral_models` for `mistral`. Underlying fn is **sync and takes no `backend`** → closure is `async def` with `# noqa: RUF029` and `backend: … # noqa: ARG001`.
- `google` → `_list_google_models` for `google` (async underlying).
- `bedrock` → `_list_bedrock_models` for `bedrock`, `bedrock_aioboto3` (**sync** underlying → `# noqa: RUF029`).

**Behavior preserved byte-for-byte** (verified against `git show HEAD:…model_lists.py`): the per-sdk `find_spec` guards removed from `model_lists.py` were **already duplicated inside each `list_*_models` fn** (same lib/extra/message for anthropic/mistral/google/bedrock; openai has none — always installed), so a missing extra still raises `MissingDependencyError` inside the lister and is wrapped by the loop's Case-2 `except Exception → PipelexCLIError` exactly as before. The `list_*_models` fns themselves are **unchanged**. `any_listed` threads identically (set `True` only after a successful `await`; not reached when the lister raises `ModelListingUnsupportedError`, matching the old `continue`). The unsupported-SDK display path is untouched.

**Tests:** `tests/unit/pipelex/plugins/test_model_lister_coverage.py` (registry built from `BUILTIN_PLUGINS`: every expected sdk key resolves to a lister + exact-set assertion + soft-miss cases) · `tests/unit/pipelex/cogt/model_backends/test_model_lister_dispatch.py` (behavioral: lister invoked with expected kwargs; `any_listed` progresses False→True across two SDKs; unknown sdk → unsupported message + lister not invoked; `ModelListingUnsupportedError` translate path → unsupported; generic lister failure → wrapped `PipelexCLIError`). `test_import_light_boot.py` grew an `assert registrar.model_listers` (proves listers register import-light).

**Docs:** `docs/under-the-hood/inference-backend-plugins.md` gained a "Listing models — an optional capability" section (the `add_model_lister` call, the `ListModelsFn` shape, import-light/fail-at-use rules, the `ModelListingUnsupportedError` soft-signal); SPI table += `ListModelsFn` / `ModelListingUnsupportedError`; fail-loud table += `DuplicateModelListerError` (and fixed the adjacent stale `NotImplementedError` row → `InferenceBackendNotFoundError`).

**CHECKPOINT-4 sweep result — "core names no integration" now holds for every enumerated seam.** The broad grep surfaces three **pre-existing, unchanged** `pipelex.plugins.<vendor>` refs that were never in the Phase 0–4 seam list: `cogt/config_cogt.py` (vendor typed-config models — **by design**, design D7), `cogt/img_gen/img_gen_args_factory.py` (`OpenAIImgGenFactory`) and `cogt/model_backends/backend_factory.py` (`VertexAIFactory`, lazy, vertexai auth) — the latter two genuine but **unenumerated** couplings (each would need its own contract capability to invert). Recorded with disposition in [`wip/plugins/phase-4-residual-core-vendor-couplings.md`](wip/plugins/phase-4-residual-core-vendor-couplings.md). **No dispatch-path integration remains.**

**Notes for Phase 5:** Phase 4 is independent of the Temporal externalization. No new cross-repo surface. The model-lister registry is a pure additive capability — an external backend plugin can now contribute a lister via the same `register` it uses for `add_inference_backend`.

### Phase 5 — Step 0b (C6) as-built (the config-schema relocation prerequisite)

**Status:** done, committed at this checkpoint on `refactor/Plugins-2`. **In-`pipelex` only, behavior-neutral, zero cross-repo blast radius.** Gates: `make tb` green · `make agent-check` clean (ruff/plxt, **pyright 0/0**, mypy 0 over 2244 source files, keyword-only pass) · targeted `tests/unit/pipelex/{temporal,system,errors}/` → 463 passed · **full `make agent-test` "All tests passed."** This is the prerequisite that makes the rest of Phase 5 a packaging move: **core config no longer imports `pipelex.temporal`.**

**What moved.**

- `git mv pipelex/temporal/config_temporal.py → pipelex/system/configuration/config_temporal.py` (history preserved; the whole schema module — it was already import-light via the `if TYPE_CHECKING: from temporalio.common import RetryPolicy / else: RetryPolicy = Any` placeholder, kept verbatim). Its internal `from pipelex.temporal.exceptions import …` → `from pipelex.system.configuration.exceptions import …`.
- **New** `pipelex/system/configuration/exceptions.py` holds the two exceptions the schema raises: `TemporalConfigError(ValueError, PipelexError)` + `WorkerTaskQueueUnknownError(TemporalConfigError)` *(base order later corrected to `(PipelexError, ValueError)` by the `.message` fix — see the flagged-bug note below)*. **Re-based** from `TemporalFlowError` to `PipelexError` directly — deliberate: `TemporalFlowError` is the base of the *runtime/workflow* errors that stay with (and externalize with) `pipelex/temporal/`, so dragging it into core would be wrong for the end-state. `TemporalFlowError` is **never imported/caught anywhere** (only mentioned in comments — verified), so dropping it from these two classes' ancestry is invisible. `error_domain` stays `None` (both old `TemporalFlowError` and new `PipelexError` leave it unset — chose `PipelexError` over the domain-setting `PipelexConfigError` to preserve exact behavior).

**What stayed (in `pipelex/temporal/exceptions.py`, travels external in the cut-over).** `TemporalFlowError` + the runtime errors (`WorkflowExecutionError`, `UnrecoverableWorkflowFailureError`, `WorkflowInputError`, `ContentGenerationError`, `TemporalServerError`) + the worker-boot config subclasses (`WorkerScopeConfigError`, `WorkerProfileConfigError`, `SearchAttributeRegistrationError`), which now subclass the **core** `TemporalConfigError` (imported at the module top).

**Importers repointed** (mechanical `perl` rename `pipelex.temporal.config_temporal` → `pipelex.system.configuration.config_temporal` across `pipelex/` + `tests/`, then hand-split the lines that mixed a moved exception with a staying symbol): source = `configs.py:14`, `temporal_tasks.py`, `temporal_connect.py`, `temporal_manager.py`, `temporal_task_manager.py`, `task_manager.py` (TYPE_CHECKING), `codec/codec_server_cli.py`, and the `namespace_check.py` docstring; tests = the ~20 temporal config/exception test modules. The two regression tests got their hardcoded source path / import updated: `test_config_temporal_optional_dep.py` (now AST-scans `pipelex/system/configuration/config_temporal.py`) and `test_dispatch_options_no_temporalio.py`. The `temporal-e2e-validate` skill doc's `BUILTIN_SEARCH_ATTRIBUTES` reference was updated. `pipelex-dev generate-error-pages` rewrote 4 pages (the two moved errors' `Defined in`/`Parent` rows + the `execution-and-runtime`/`platform-and-tooling` macro listings, which correctly regroup the two from "Temporal execution" → "System & configuration").

**Behavior preserved byte-for-byte** (the relocation is a pure move): the schema's validators/methods (`resolve_dispatch`, `make_retry_policy`, `validate_task_queue_known`, the orphan-queue validators) are unchanged; the exception MRO/`error_domain`/`isinstance(_, ValueError)`/`str()`/`.args` are identical to pre-move (verified empirically). The error-class-location convention test passes (new module is a proper `exceptions.py` importing only `PipelexError`).

**Flagged at C6, FIXED in follow-up (`xhigh` review action):** the `(ValueError, PipelexError)` MRO meant `ValueError.__init__` won, so `.message` was never set and `to_error_report()` raised `AttributeError`. Fixed by reordering bases so the message-setting `PipelexError` base resolves first — `TemporalConfigError(PipelexError, ValueError)` and `ConfigModelError(FatalError, ValueError)` (the `Worker*` / `SearchAttribute*` subclasses inherit the fix transitively; the two `(PipeComposeError, ValueError/TypeError)` compose mixins already had the safe order). `isinstance(_, ValueError)` is unaffected by base order, so Pydantic still wraps validator raises; `str()`/`.args` unchanged. Behavior change at one site: `ConfigModelError` now runs the restored `TracebackMessageError.__init__`, so it logs at its single misuse raise site (`ConfigModel.transform_dict_str_to_enum`) — appropriate fatal-error behavior, matching its `ConfigValidationError` / `FatalError` siblings. Guard + regression locked in by `tests/unit/pipelex/test_pipelex_error_message_init.py` (MRO sweep over every loaded `PipelexError` subclass asserting `PipelexError` precedes `ValueError`/`TypeError`, plus `.message` / `to_error_report()` assertions on the reordered classes). `make agent-check` clean, full `make agent-test` green.

**Cross-repo readiness for the cut-over:** scanned `pipelex-worker` / `pipelex-mistralai-workflows` / `pipelex-api` / `pipelex-api-hosted` / `pipelex-platform` / `pipelex-admin-api` / `sandbox` / `cocode` — **none** import the moved config schema or the two moved exceptions (the only external `pipelex.temporal.*` import is `pipelex-api` pulling the *runtime* `WorkflowExecutionError`, which stays in `pipelex/temporal/` and is a normal cut-over pin concern, not a C6 concern). So Step 0b ships with no downstream coordination.

**Remaining Phase 5 (cross-repo, paused for go/no-go):** Step 0a scaffold `../pipelex-temporal` (empty repo, remote `Pipelex/pipelex-temporal`, mirror `pipelex-api`/`pipelex-platform` conventions) → move `pipelex/temporal/` + `temporal_plugin.py` + temporal tests + the `temporal` marker + `--temporal-server` conftest option out, declare the `pipelex.plugins` entry point → flip `pipelex-worker` / `pipelex-api-hosted` pins → repoint `pipelex-mistralai-workflows` → run consumer suites before publishing. Also fold in the Option-A follow-up (delete the now-dead `load_base_config_dict()` / `ensure_global_if_missing=False` in `config_loader.py`).

### Phase 5 — cross-repo cut-over as-built (LOCAL work, pre-publish; 2026-06-20)

**Status: the reversible local cut-over is DONE and green on both sides.** User gave go/no-go for the *reversible local work only* (scaffold + move + flip-to-editable + suites green), explicitly **stopping before any PyPI publish / merge / deploy**. Nothing pushed. Two decisions locked this session: **D8** (package layout = top-level `pipelex_temporal`, not a `pipelex.temporal` namespace stitch — see the header note) and **D9** (scaffold tool-configs sourced from `pipelex`, repo shape from `pipelex-api`).

**Green evidence.**
- Core (`_plugins`): **`make agent-check` clean** (pyright 0 / mypy 0 over 2077 src / keyword-only ✓), **`make tb` green**, **full `make agent-test` = 7678 passed** (after fixing 2 error-handling bundle couplings, below; 4 xfailed + 2 skipped are pre-existing/expected).
- `pipelex-temporal`: **`make agent-check` clean** (ruff/pyright **0** / mypy 0/208), **`make agent-test` "All tests passed"** (≈509 pass, 4 xpassed = the same pre-existing xdist class-registration flake markers as pipelex's baseline). Entry point, `pipelex-temporal` console script (`worker`/`setup-namespace`), and import smokes verified.

**The new dist (`/Users/lchoquel/repos/Pipelex/pipelex-temporal`, branch `main`, NO commits yet at time of writing — local only).** Top-level package `pipelex_temporal/` (64 modules, `pipelex.temporal.*`→`pipelex_temporal.*` rewrite). `pyproject.toml`: deps `pipelex>=0.35.0` + `temporalio==1.24.0` + `aiohttp>=3.14.0`; **`[tool.uv.sources] pipelex = { path = "../_plugins", editable = true }`** (local-dev cross-pin → flips to a published `pipelex==Y` pin at release); `[project.scripts] pipelex-temporal = "pipelex_temporal.temporal_cli:app"`; `[project.entry-points."pipelex.plugins"] temporal = "pipelex_temporal.temporal_plugin:TemporalPlugin"`; tool-configs copied from pipelex; **`[tool.ruff.lint.isort] known-first-party = ["pipelex","pipelex_temporal"]`** so the workflow modules' deliberate `# noqa: TC001` on passed-through `pipelex.*` imports keep working (without it `pipelex` is third-party → TC002 → noqa stripped). `Makefile`+`Makefiles/Makefile_basics.mk` (trimmed from pipelex-api: env/install/lock/format/lint/pyright/mypy/agent-check/agent-test/clean*). README, CHANGELOG (`[Unreleased]`), LICENSE, `.gitignore`, `pipelex_temporal/py.typed`.

**Core (`_plugins`) cut.** `TemporalPlugin` removed from `BUILTIN_PLUGINS` (+ comment that temporal is now an external entry-point dist); `CORE_UNCONDITIONAL_PLUGIN_NAMES` unchanged (`{direct, openai}`). `pyproject.toml`: dropped the `temporal` extra, the `pipelex-temporal` console script (so the new repo's editable install doesn't collide), and the `temporal` pytest marker. `git rm`'d `pipelex/temporal/` + `tests/{unit,integration}/pipelex/temporal/` + 2 scattered moved tests. Core source names no integration (only doc-comments, repointed to `pipelex_temporal`). **`MissingOrchestratorError` install hint changed** `pip install 'pipelex[temporal]'` → `pip install pipelex-temporal` (+ docstring; + the 2 asserting tests `test_exceptions_disclosure.py`/`test_orchestrator_dispatch.py`). Stale `pipelex[temporal]` docstrings in `reporting_manager.py`/`execution_mode.py`/`test_temporal_activity_gate_lazy_import.py` → `pipelex-temporal`. **Option-A fold-in done:** deleted dead `load_base_config_dict()` + the `ensure_global_if_missing` param/branch in `config_loader.py`.

**Test reconciliation (the fiddly part).** Temporal behavioral suite (~110 files) + shared fixtures (`tests/integration/fixtures/` + `tests/integration/conftest.py`), root `tests/conftest.py`, and shared `error_handling/test_data.py` copied into `pipelex-temporal/tests/` (layout `tests/{unit,integration}/pipelex_temporal/`; the blanket rewrite maps both `pipelex.temporal`→`pipelex_temporal` and the test path `tests.integration.pipelex.temporal`→`tests.integration.pipelex_temporal`). **5 mixed core bridge/boot tests split** (core keeps the DIRECT/core-mode methods, the temporal-mode methods move to new pipelex-temporal files): `test_dispatch.py` (3 methods → `test_bridge_temporal_dispatch.py`), `test_temporal_blocking_workflow_id.py` (wholesale), `test_trace_context_contract.py` (→ `test_trace_context_temporal.py`), `test_keyless_boot_forced_dry.py` (→ `test_keyless_temporal_boot.py` under `tests/integration/system/` to escape the temporal conftest's autouse `boot_temporal`), `test_error_type_uri.py` (wholesale). **`test_cv_batch_screening.py` stayed** (DIRECT e2e) — decoupled from the temporal tree via a local `test_data.py` + its own `cv_batch_screening.mthds`. **`test_config_temporal_optional_dep` + `test_non_retryable_baseline_pins` relocated BACK to core** `tests/unit/pipelex/system/` (they validate the core-relocated `config_temporal.py` / `pipelex.toml`, were mis-swept). **2 shared bundles restored to core** `tests/integration/pipelex/error_handling/bundles/{native_text_sequence,native_search}.mthds` (the core local-parity error tests read them; they were mislocated under the temporal tree). `test_import_light_boot.py` reworded (temporalio stays BLOCKED; the temporal slot-claim arm moved to the pipelex-temporal suite — core guarantee "boot imports no temporalio even with is_enabled=True" preserved). pipelex-temporal needed its own `tests/__init__.py` rootdir anchor + a `.pipelex/` project config + a rootdir `conftest.py` (`pytest_plugins` + placeholder creds) for hermetic standalone boot.

**Docs hygiene done:** `tests/CLAUDE.md` temporal row removed; all `pipelex[temporal]` install instructions in `docs/` → `pipelex-temporal`; the stale `MissingPipelexTemporalExtraError`/`MissingMistralWorkflowsPluginError` doc refs → `MissingOrchestratorError`.

> **⚠ CORRECTION 2026-06-21 — read before using this cut-list.** `pipelex-temporal` is **PRIVATE / not-open-source → NOT PyPI.** The `pipelex-temporal==Y` pins written below are the wrong (public-PyPI) form. The correct form is a **`git+ssh` pin** (`pipelex-temporal @ git+ssh://git@github.com/Pipelex/pipelex-temporal.git@<tag>`), matching `pipelex-shared` in `pipelex-platform`. And only **private** repos may pin it: `pipelex-worker` and (newly) `pipelex-api-hosted`'s child image (confirmed 2026-06-21: the hosted runner enqueues Temporal) — the "`pipelex-api-hosted` = no-op" line below is now WRONG. The **public MIT** repos `pipelex-api` and `pipelex-mistralai-workflows` must **DROP** the `temporal` extra instead of repinning it. Reconcile the bullets below to git+ssh when the wiring is actually done.

**DEFERRED — publish/release-gated downstream cut-list (do NOT execute ahead of the pipelex release that ships `pipelex-temporal`):**
- **`pipelex-worker`** — `pyproject.toml:8` `pipelex[dynamodb,s3,temporal]==0.34.0` → `pipelex[dynamodb,s3]==X` + `pipelex-temporal==Y`; **Dockerfile:25** `CMD ["pipelex","worker","--no-sandbox"]` → `["pipelex-temporal","worker","--no-sandbox"]`; **Makefile:37** `$(PIPELEX) worker …` → `pipelex-temporal worker …`; **Makefile:52** editable install `-e "$(PIPELEX_REPO)[dynamodb,s3,temporal]"` → drop `temporal`, add `pipelex-temporal`. Per the Option-A note this MUST land in the same commit as the `pipelex` pin bump (until then the old pinned pipelex still has `pipelex worker`, so nothing breaks).
- **`pipelex-mistralai-workflows`** — `pyproject.toml:41` `temporal = ["pipelex[temporal]>=0.27.0"]` → `temporal = ["pipelex-temporal>=Y"]`; rewrite the ~9 `pipelex.temporal.*` imports in `tests/integration/test_bridge_temporal_{blocking,fire_and_forget}.py` → `pipelex_temporal.*`. Gated on published `pipelex-temporal` AND coordinate with that repo's in-flight mistralai-2.x work (don't disrupt it).
- **`pipelex-api`** pins `pipelex[…,temporal]==0.35.0` (PyPI) → drop `temporal`, add `pipelex-temporal` — publish-gated. **`pipelex-api-hosted`** = config-only wrapper, no Python pin (temporal reaches it through the `pipelex-api` image) — no-op.

**DEFERRED — other follow-ups:**
- `docs/errors/` temporal error pages (`unrecoverable-workflow-failure-error.md`, `workflow-execution-error.md`, `temporal-flow-error.md`, etc.) left in core ON PURPOSE: they are the `type_uri` dereference targets on `docs.pipelex.com`; deleting them before pipelex-temporal's docs exist would 404 those URLs. Moving them (and repointing/aggregating the type_uris) is a docs-deploy task for the publish phase. Do NOT `generate-error-pages` to prune them yet. (`temporal-config-error.md` stays — that error is core.)
- Deeper `docs/under-the-hood/` internal-path references (`temporal-integration.md`, `orchestrator-plugins.md`, `distributed-content-generation.md`, `pipe-routing-and-execution.md`, `error-model.md`) still say `pipelex.temporal` in prose — accurate-keeping pass deferred (the system behaves identically; coupled to the docs-deploy story). `orchestrator-plugins.md` should eventually present temporal as the worked **external** plugin example.
- Cross-repo `error_handling/test_data.py` parity constants are now duplicated in core + pipelex-temporal (can drift; inherent to externalization — no shared-file enforcement across repos).
- Local commits made on both sides (NOT pushed): `_plugins` = Phase 5 checkpoint commit on `refactor/Plugins-2`; `pipelex-temporal` = initial commit on `main`.
- **Post-local-cut-over `/code-review` triage (2026-06-20)** → [`wip/plugins/phase-5-cutover-review-followups.md`](wip/plugins/phase-5-cutover-review-followups.md). xhigh review of the core-side cut-over commit. **Fixed this session** (reachable/core-hygiene that stays in core): kit `commands.md` temporal-test section removed + `CLAUDE.md` regen; `uv.lock` temporal-extra drop; `bridge.py` + `test_config_temporal_optional_dep` docstrings; 5 plugin/cogt test stubs (dropped vestigial `temporal` stub field); **restored two core-coverage tests** — `test_trace_context_contract::test_non_direct_mode_nulls_host_trace_context` (core-side guard for the bridge's non-DIRECT trace_context nulling — distinct from the temporal-mode test that moved to pipelex-temporal) + `test_dispatch_options_no_temporalio.py` (DispatchOptions constructible without temporalio — the `RetryPolicy = Any` forward-ref contract the AST scan can't catch). **Still deferred** (in the wip doc): skill `temporal-e2e-validate` relocation, Makefile temporal targets (`tw`/`ttm`/…, CI-isolated), `debugging-hanging-pytest-runs.md`, boot eager-validation design call, `non_retryable_error_types` cross-repo class-name desync, dead `cv_batch_screening_inputs.json` mirror.
- **Finalize-local pass (session 2, 2026-06-20)** → same wip doc, *Finalize-local pass* section. Closed two of the prior bullet's "Still deferred" items: **both** Temporal skills relocated to `pipelex-temporal` (`temporal-e2e-validate` *and* `temporal-test-crate` — the latter was never on the list, also dead in core) + removed from core, and the **core** Makefile temporal targets deleted (help + `.PHONY` + `test-temporal`/`ttm` + `temporal-server`/`-stop`/`-worker`/`-run`; the `pipelex-temporal` Makefile *add* stays open — unverifiable without a running server). Plus the `pipelex-temporal` *additions*-side `/code-review` → **SHIP/clean**; NITs: stray `.pipelex/traces/*.ndjson` untracked+gitignored, shipped `test_extras→tests` back-import deferred (pre-existing/dormant). Gates: core `make tb` + full `make agent-test` green (HEAD `27da150a5`); pipelex-temporal `make agent-check` clean. **Local, uncommitted; still paused before publish.**
