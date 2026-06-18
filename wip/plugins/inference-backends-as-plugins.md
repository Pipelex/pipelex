# Inference backends as Pipelex plugins

**Status:** assessment / proposed plan (not started)
**Scope:** turn the inference-SDK wrappers under `pipelex/plugins/` (OpenAI, Anthropic, Google, Mistral, Bedrock, Fal, Docling, Linkup, …) into *registerable plugins* — selected out of a registry the backends populate, rather than dispatched from hardcoded `match` statements in core. Optionally, package the heavier ones as separate installable dists.

> This is the **driver** half of the plugin story. Inference backends are homogeneous, many, and *selected by data* (a model's `sdk` handle). The **strategy** half — orchestrators (Temporal, Mistral Workflows) that swap core orchestration seams — is in [`orchestrators-as-plugins.md`](orchestrators-as-plugins.md). The cross-cutting best practices — and the shared discovery mechanism both halves use — are in [`README.md`](README.md).

## Verdict

Partially decoupled, and confusingly named. The wrappers already live in one place (`pipelex/plugins/<backend>/`), already share clean abstract base classes (`LLMWorkerAbstract`, `ImgGenWorkerAbstract`, `ExtractWorkerAbstract`, `SearchWorkerAbstract`, all under `InferenceWorkerAbstract`), already gate heavy SDKs behind optional extras + lazy `importlib.util.find_spec(...)` checks, and already cache instantiated SDK clients in a runtime registry (`PluginSdkRegistry`, keyed by an `sdk@backend/variant` handle). **What's missing is the inversion**: core still owns the backend→implementation mapping in centralized `match plugin.sdk:` statements inside the four worker factories. A third party cannot add a backend without editing core.

So the work here is the mirror of Temporal's: define the registry, have backends register into it (via the *same* entry-point discovery), and delete the `match` statements.

## First: resolve the "plugin" naming overload

The word is already overloaded three ways, and that has to be fixed before adding a real plugin system or every conversation will be ambiguous:

- `pipelex/plugins/<backend>/` — the directories. These are **in-tree SDK adapters**, not installable plugins.
- `Plugin` (`pipelex/plugins/plugin.py`) — a value object: `sdk` + `backend` + `variant`, with an `sdk_handle` like `anthropic@bedrock/claude`. This is a **backend selector / handle**, not a plugin.
- `PluginManager` / `PluginSdkRegistry` — a **runtime cache of instantiated SDK clients** keyed by that handle, with `teardown()`. Not a discovery mechanism.

None of these is a plugin in the installable-distribution sense. Proposed vocabulary:

- Rename the existing trio to what it is: `SdkClientRegistry` / `SdkClientManager`, `BackendSelector` (or keep `Plugin` as `ModelHandle`). Pure rename, no behaviour change.
- Reserve **"plugin"** for the new concept shared with Temporal: an installable unit, discovered via the `pipelex.plugins` entry-point group, that registers extensions at boot.

(This rename can land independently and ahead of everything else — it's low-risk and unblocks clear naming for the rest.)

## What kind of plugin these are

**Driver plugins.** Many of them, all the same shape, chosen at runtime by the model spec's `sdk` field. They don't replace core behavior; they *supply an implementation* for a backend the core asked for. The right seam is a **typed registry keyed by `sdk` handle**, one per worker family. A driver plugin's job is to call `registry.register(sdk_handle, factory)` at boot. Contrast Temporal, which swaps singleton seams on the hub — different hook, same discovery.

## The seams today

Four worker factories, each a centralized dispatch on `plugin.sdk`:

| Factory | File | Backends in its `match` |
|---|---|---|
| `LLMWorkerFactory` | `cogt/llm/llm_worker_factory.py` | `gateway_completions`, `portkey_completions`, `openai` / `azure_openai`, `anthropic` / `bedrock_anthropic`, `mistral`, `bedrock_boto3` / `bedrock_aioboto3`, `google` |
| `ImgGenWorkerFactory` | `cogt/img_gen/img_gen_worker_factory.py` | `gateway_img_gen`, `fal`, `huggingface_img_gen`, `openai_img_gen`, `blackboxai_img_gen`, `azure_rest_img_gen`, `google` |
| `ExtractWorkerFactory` | `cogt/extract/extract_worker_factory.py` | `gateway_extract`, `mistral`, `pypdfium2`, `docling_sdk`, `linkup_fetch` |
| `SearchWorkerFactory` | `cogt/search/search_worker_factory.py` | `linkup`, `gateway_search` |

Each `case` does the same three things: optionally `importlib.util.find_spec(...)` to raise a friendly `MissingDependencyError` (lib name + extra name), lazily import the backend's factory + worker, then build the worker (reusing a cached SDK client from `PluginSdkRegistry`). The lazy import inside each `case` is exactly the inversion point — it's already "don't touch the SDK until this backend is selected"; it just needs to become "ask the registry for the selected backend's factory."

Supporting structure already in place:

- **Abstract contracts.** `InferenceWorkerAbstract` → `{LLM,ImgGen,Extract,Search}WorkerAbstract`. A registered factory returns one of these. `PluginFactoryAbstract.make_extras(...)` is a partial start at a common factory contract.
- **Optional extras.** `pyproject.toml`: `anthropic`, `bedrock`, `docling`, `fal`, `google` / `google-genai`, `huggingface`, `linkup`, `mistralai` (plus `dynamodb` / `s3` infra extras). `openai`, `portkey`, `pypdfium2` are **core deps** (always present), so `gateway`/`portkey`/`openai`/`azure_rest` backends never need a guard. (OpenAI is a core dep for a deeper reason than "it's always installed" — see "OpenAI is two things" below.)
- **Runtime client cache.** `PluginSdkRegistry` keyed by `sdk_handle` — keep this as-is (rename aside); it's the right place to memoize clients and already has lifecycle teardown.

## "Plugin" and "in-repo" are orthogonal axes

Before deciding what ships where, kill one confusion: **being a plugin** (registering through the seam) and **shipping as a separate dist** are independent choices. A built-in plugin that lives in this repo is the *default*, not a contradiction.

|  | **In-repo** | **Separate dist** |
|---|---|---|
| **Through the seam** (registry / entry point) | built-in plugins — the default for *every* backend (OpenAI driver, gateway, portkey, …) | external plugins (`pipelex-anthropic`, `pipelex-google`, …) |
| **Hardcoded in core** | the wart we're deleting | n/a |

"Plugin" = *registers through the seam* instead of a `match` arm. "In-repo vs separate dist" = a *packaging* decision (the granularity choices below). They don't constrain each other — so "keep it internal" never has to mean "keep it a hardcoded special case."

## OpenAI is two things: substrate vs driver

The OpenAI SDK is not just another backend — it is the lingua franca a large fraction of the others are built on. `gateway`, `portkey`, `openrouter`, `blackboxai` all construct `openai.AsyncOpenAI(base_url=...)` (OpenAI-compatible endpoints), and even `anthropic`, `mistral`, `google` import the SDK for the shared `ChatCompletion*` message types. So "the OpenAI SDK" hides two concerns with different fates:

- **Substrate** — the OpenAI-compatible client (`AsyncOpenAI(base_url=…)`), the shared request/response types, and the completions/responses plumbing that gateway/portkey/openrouter/blackboxai/azure_rest reuse. This is **infrastructure other backends import**, not a backend itself.
- **Driver** — the `openai` / `azure_openai` / `openai_img_gen` registrations: the actual "talk to api.openai.com" worker.

They live in the same `pipelex/plugins/openai/` directory today but want opposite treatment:

- **Substrate → core internal library, always a hard dependency.** Promote it out of `pipelex/plugins/openai/` into a deliberate module (e.g. `pipelex.openai_compat`) with a stable signature, importable by any backend — in-repo or external. The "OpenAI API is a de-facto standard" argument is precisely the argument for keeping the substrate in core: if it were instead an optional dist, gateway/portkey/openrouter/blackboxai/azure would *all* have to depend on it — a diamond where a dozen "plugins" pull `pipelex-openai`. Core is the right home. And once plugins import it, the substrate becomes a **contract** — shape it deliberately rather than letting plugins reach into `pipelex/plugins/openai/` internals (which `anthropic_factory.py` et al. effectively do today).
- **Driver → always-on built-in plugin, through the seam.** No extra, registered unconditionally — but registered like everyone else. Do **not** leave OpenAI as the one surviving hardcoded `match` arm: the seam's whole value is *core names no backend*, and a privileged special case is a two-tier system the next "important" backend will want to join, eroding the abstraction. It ships in-repo and is always present; it just goes through the same door.

Net: **substrate in core (a library, not a plugin); OpenAI driver is an always-on built-in plugin through the seam.** OpenAI never leaves the repo and is never gated — without keeping a privileged backend.

## Recommended approach: a worker-factory registry the backends populate

1. **One registry per worker family** (or one registry, partitioned by family), keyed by `sdk` handle, mapping to a factory callable returning the right `*WorkerAbstract`. Core owns the registry + the abstract contracts; backends own the entries.

2. **Each backend registers itself.** Replace the `match` arms with `registry.lookup(plugin.sdk)`. The friendly `MissingDependencyError` (lib + extra name) moves into the backend's registration/factory so the error stays as helpful as today. Built-in backends register at boot through the same `pipelex.plugins` entry-point mechanism Temporal uses — **dogfood the plugin API in-tree first**, before any backend is externalized.

3. **Keep selection data-driven.** Nothing changes for users: models still declare `sdk` / `backend_name` / `variant` in TOML; `Plugin.make_for_inference_model(...)` (→ `ModelHandle`) still builds the handle; the registry lookup replaces the `match`. The `MISSING extra` failure mode is preserved, just relocated.

4. **Decide packaging granularity** (this is the real product decision, deferrable):
   - **In-tree but registerable (lowest churn).** All backends stay in `pipelex`, but register through the seam. Wins: third parties can add a backend in their own dist without a core PR; the `match` statements die; no distribution split to maintain. This alone delivers most of the value.
   - **Per-vendor dists** (`pipelex-anthropic`, `pipelex-google`, `pipelex-bedrock`, …): each owns its SDK dep and its entry point; base `pipelex` ships only the always-on backends (openai/portkey/gateway). Wins: smallest base install, independent cadence, clean dependency surface. Costs: many small repos/dists, version-matrix testing, more release overhead.
   - **Bundles** (e.g. `pipelex-aws` = bedrock + s3 + dynamodb; `pipelex-google` = genai + vertex): a middle ground grouping by shared SDK/credentials.

   Recommendation: **adopt the registry seam first (in-tree), externalize selectively later** — only split out a backend when its dependency weight or release cadence actually justifies a separate dist. The seam makes that a packaging move, not a refactor.

## Watch-items

- **Granularity of the handle.** `sdk` vs `backend` vs `variant` already encode a lot (`anthropic@bedrock/claude`). The registry key should be the `sdk` handle the factories currently switch on — confirm that's stable and 1:1 with a factory.
- **Inconsistent factory shapes.** Some backends have a factory class (`AnthropicFactory`, `MistralFactory`), some instantiate the worker directly (Fal). Normalize on one registration contract (extend `PluginFactoryAbstract`) so every entry looks the same.
- **Core-dep backends.** openai/portkey/gateway/pypdfium2/azure_rest have no extra and must always be registered — make their registration unconditional so a misconfigured plugin environment can't drop them.
- **OpenAI substrate is a shared contract.** Once the OpenAI-compat substrate is promoted to a core module that other backends import (see "OpenAI is two things"), its signature is part of the surface plugins depend on — version and shape it deliberately, don't let it drift as an accidental internal.
- **Cross-family backends.** `mistral` appears in LLM *and* Extract; `google` in LLM *and* ImgGen; `linkup` in Extract *and* Search; `gateway_*` everywhere. A per-vendor dist must register into multiple family registries — the plugin's `register_*` hook needs access to all of them.
- **Error parity.** The `MissingDependencyError` messages today are genuinely helpful (they suggest alternatives, e.g. "use Anthropic via Bedrock instead"). Preserve that quality when moving the guard into registration.

## Effort & risk

- **Moderate, and mostly mechanical** — but with more surface than Temporal (four factories, ~15 backends, two extras families) and a naming refactor up front. No new hard algorithms; the lazy-import + extras + client-cache machinery already exists.
- The risk concentrates in the **registration timing** (everything must be registered before the first worker is built) and in **not silently dropping a core backend**. Both are covered by keeping built-in registration unconditional and tested.

## Suggested phasing

- **Phase 0 — rename.** `Plugin`/`PluginManager`/`PluginSdkRegistry` → `ModelHandle` (or `BackendSelector`) / `SdkClientManager` / `SdkClientRegistry`. Pure rename. _Checkpoint: suite green, naming unambiguous, "plugin" freed for the real concept._
- **Phase 0.5 — extract the OpenAI substrate.** Promote the OpenAI-compatible client + shared types + completions/responses plumbing out of `pipelex/plugins/openai/` into a deliberate core module (e.g. `pipelex.openai_compat`); repoint gateway/portkey/openrouter/blackboxai/azure_rest (and the type-only imports in anthropic/mistral/google) at it. Pure move + import rewrite, still in core. _Checkpoint: suite green; no backend reaches into `pipelex/plugins/openai/` internals — the substrate is the only OpenAI surface they touch._
- **Phase 1 — registry seam, in-tree.** Add the per-family worker-factory registry; convert each `match` arm (OpenAI driver included — no special case) to a registration + the factory body; built-in backends register through the shared `pipelex.plugins` entry point. No packaging change, no behaviour change. _Checkpoint: full suite green with all backends in-repo but selected via the registry — proves the seam (mirrors Temporal Phase 1)._
- **Phase 2 — externalize selectively (optional).** Split out only the backends whose dependency weight or cadence justifies it, into per-vendor or bundle dists, each declaring its entry point and owning its extra. The OpenAI driver and the `openai_compat` substrate stay in core. _Checkpoint: base `pipelex` ships only always-on backends + the substrate; each external backend's suite green against the published base._
