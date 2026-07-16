# Storage provider → `pipelex.plugins` plugin

Status: **COMPLETE.** All phases delivered — this vertical (Phases 1–2 of the master plan) defines the shared "keyed registry + config-selected singleton" mechanism (§ The new mechanism) that the secrets plan reuses. See [TODOS.md](../../TODOS.md) for the execution record (Phases 1–2 code + tests + docs, Phase 5 release gating).

Goal: turn the storage provider into a formal plugin seam so third parties can ship `pipelex-storage-<backend>` packages discovered via the `pipelex.plugins` entry-point group and selected at deploy time by `storage_config.method`. The built-in providers (local / in_memory / s3 / gcp) become a single unconditional builtin plugin registering their factories — exactly as `OpenAIPlugin` registers several inference backends.

Read [README.md](README.md) first for the track's shared decisions (DX-1 API bump, DX-2 unconditional builtin, DX-3 external config follow-up) and the boot-audit rationale.

---

## Cold-start context (the seam as it is today)

Everything below is verified against the tree (worktree `_plugins`, branch is whatever's checked out — this is `pipelex/` code).

**Abstract base** — `pipelex/tools/storage/storage_provider_abstract.py`
- `StorageProviderAbstract` (line 16). Template methods `load` / `load_with_metadata` / `store`; subclass hooks `_load_with_metadata`, `_store`, `public_url` (abstract).
- Also defines `PIPELEX_STORAGE_SCHEME = "pipelex-storage://"` and `StoredData(NamedTuple)` (`data: bytes`, `mime_type: str | None`).

**Built-in implementations** — all under `pipelex/tools/storage/`
- `LocalStorageProvider` (`local_storage_provider.py:12`) — ctor `(root_path: Path)`; hard-imports `aiofiles`; path-traversal guarded; `public_url` → `file://`.
- `InMemoryStorageProvider` (`in_memory_storage_provider.py:13`) — a `RootModel[dict[str, bytes]]` **and** `StorageProviderAbstract`; no deps; `public_url` → `None`.
- `S3StorageProvider` (`s3_storage_provider.py:15`) — ctor `(bucket_name, region, signed_urls_lifespan)`; optional dep **`aioboto3`** (extra `"s3"`) + botocore, lazy-imported inside methods, guarded by `find_spec` → `MissingDependencyError`.
- `GcpStorageProvider` (`gcp_storage_provider.py:21`) — ctor `(bucket_name, project_id, credentials_file_path, signed_urls_lifespan)`; optional dep **`google-cloud-storage`** (extra `"gcp-storage"`), lazy-imported; sync GCS wrapped in `asyncio.to_thread`.

**The factory being replaced** — `pipelex/tools/storage/storage_provider_factory.py`
- `make_storage_provider_from_config(storage_provider_config)` (line 14) is a `match storage_provider_config.method:` over `StorageMethod`, each arm: `None`-check the sub-config → `sub.lazy_validate()` → construct the provider.
- Imports all four concrete classes at module top (importing the factory imports all providers; optional SDKs still stay lazy inside the providers).
- The **GCP arm** calls `get_secrets_provider().get_required_secret(secret_id="GCP_CREDENTIALS_FILE_PATH")` (line 62) — a storage→secrets→hub dependency. Safe at boot because storage is set on the hub (`pipelex.py:310`) *after* secrets (`pipelex.py:306`); **not** safe inside a plugin `register` (hub access is forbidden there). ⇒ construction must happen in a lazily-invoked factory closure, never in `register`.

**Config** — `pipelex/tools/storage/storage_config.py`
- `StorageMethod(StrEnum)` (line 13): `LOCAL`, `IN_MEMORY`, `S3`, `GCP`.
- Per-method sub-models: `StorageLocalConfig`, `StorageInMemoryConfig`, `StorageS3Config`, `StorageGcpConfig`, each with `lazy_validate()` raising `StorageConfigError`.
- `StorageProviderConfig` (line 171): `method: StorageMethod = Field(strict=False)` + one optional sub-field per method + a `model_validator(mode="after")` requiring the sub-config matching `method`.
- `StorageConfig(StorageProviderConfig)` (line 238) adds `is_fetch_remote_content_enabled` / `is_upload_local_content_enabled`.
- TOML `[pipelex.storage_config]` at `pipelex/pipelex.toml:5-27`; reached as `get_config().pipelex.storage_config`.

**Boot injection** — `pipelex/pipelex.py`
- `setup()` param `storage_provider: StorageProviderAbstract | None = None` (line 187).
- Boot block (lines 307-310): `if storage_provider is None: … make_storage_provider_from_config(get_config().pipelex.storage_config)` then `set_storage_provider(...)`.
- Also read at line 416 for the `CONTENT_GENERATOR` default thunk (`GeneratedContentFactory(storage_provider=...)`).
- `make()` mirror: param line 561, forwarded line 637.

**Hub accessors** — `pipelex/hub.py`: `set_storage_provider` (186), `get_storage_provider()` (306, raises if unset), module-level `get_storage_provider()` (476). Consumed by ~9 files / ~20 sites (input normalizer, pdf renderer, pypdfium2 worker, gateway extract worker, delivery executor, content generator, file/image/document prompt utils). **None of these change** — they keep calling `get_storage_provider()`.

**The plugin pattern to mirror** (verified):
- Contract `pipelex/plugins/contract.py` — `PipelexPlugin` protocol (`name`, `targets_api`, `register`); `PLUGIN_API_VERSION` (currently 2); `register` is **side-effect-free** (menu calls only; no hub, no I/O, no SDK import).
- Registrar `pipelex/plugins/registrar.py` — menu methods like `add_orchestrator` / `add_bundle_validator` funnel through the generic `_add` helper (line 279) which fail-louds on duplicate keys naming both plugins. Keyed registries live as `dict` fields on the registrar.
- Builtins `pipelex/plugins/builtins.py` — `BUILTIN_PLUGINS` is a list of instantiated plugin objects; `CORE_UNCONDITIONAL_PLUGIN_NAMES = frozenset({"direct", "openai"})`.
- Discovery `pipelex/plugins/discovery.py` — `build_registrar(config=...)` iterates builtins then external `pipelex.plugins` entry points; strict-equality `targets_api` check; denylist via `config.plugins.disabled`.
- Reference builtin registering several factories: `pipelex/plugins/openai/openai_plugin.py`. Reference optional-dep lazy closure: `pipelex/plugins/docling/docling_plugin.py` (`register` just calls `add_inference_backend`; the SDK import + `require_sdk` live in the module-level `_make_..._worker` closure).
- Example registry read-view to copy: `pipelex/plugins/orchestrator_registry.py` (`OrchestratorRegistry`, `get_optional` / `has` / `modes`).

---

## The new mechanism (defines the shared pattern)

A **keyed registry + config-selected singleton**. New, because no existing pattern selects a process-global singleton by its own config key (see [README.md](README.md) § The shared new pattern).

- **Open method token.** Make the registry key an open `str` token, mirroring `OrchestrationMode` (an open string, not a closed enum). The built-in tokens stay the `StorageMethod` values (`"local"`, `"in_memory"`, `"s3"`, `"gcp"`); an external plugin registers e.g. `"azure"`. **Decision D1** below covers making `storage_config.method` accept arbitrary tokens.
- **Registration side (in the plugin):** a new registrar menu method
  `add_storage_provider(*, method: str, factory: StorageProviderFactoryFn)` where
  `StorageProviderFactoryFn = Callable[[StorageProviderConfig], StorageProviderAbstract]`.
  Accumulates into `registrar.storage_providers: dict[str, StorageProviderFactoryFn]`, fail-loud on duplicate via the existing `_add` helper.
- **Read view:** `StorageProviderRegistry` (new, `pipelex/plugins/storage_provider_registry.py`) mirroring `OrchestratorRegistry` — `get_optional(method=...)` / `get_required(method=...)` (raising a new `UnknownStorageMethodError`) / `has` / `methods`.
- **Selection side (in core boot):** replace the `make_storage_provider_from_config` call at `pipelex.py:307-310` with:
  register-built `StorageProviderRegistry` on the hub → read `config.method` → `registry.get_required(method=config.method)(config)` → `set_storage_provider(...)`. The explicit `setup(storage_provider=...)` param still wins ahead of this (same three-tier precedence as content generator: explicit param > registry selection > — there is no separate core default; the builtin plugin *is* the default supplier).
- **Where the per-method construction goes:** each `match` arm body from today's factory (None-check → `lazy_validate()` → construct) moves verbatim into a module-level factory closure in the builtin `StoragePlugin`, e.g. `_make_local_storage_provider(config)`, `_make_s3_storage_provider(config)`. The GCP closure keeps its `get_secrets_provider()` hub read — legal because the closure runs at the boot apply-point, not in `register`.

Net effect: `make_storage_provider_from_config` and its `match` are deleted; the four arms become four registered closures; core boot does a registry lookup instead of a hardcoded factory call. `StorageProviderAbstract`, the four provider classes, the config models, and every consumer are unchanged.

---

## Decisions (recommended defaults — confirm before building)

- **D1 — Open method token.** Make `StorageProviderConfig.method` accept an open `str` while keeping the `StorageMethod` enum for the built-ins (validate against the registry at boot, not against the enum at parse time — an unknown token surfaces as `UnknownStorageMethodError` from `get_required`, which is the right layer). *Recommended:* yes; without it external providers can be registered but never selected. *Alternative:* keep the closed enum and defer external selection — rejected, it guts the feature.
- **D2 — One builtin `StoragePlugin`, unconditional.** A single builtin plugin (`name = "storage"`) registers all built-in methods, and joins `CORE_UNCONDITIONAL_PLUGIN_NAMES` (DX-2) so it can't be disabled into a broken boot. *Alternative:* one plugin per method — rejected as needless fragmentation; `OpenAIPlugin` already precedents "one plugin, many factories."
- **D3 — External-provider config surface (follow-up, not Phase 1).** `StorageProviderConfig` has fixed typed sub-fields, so an `azure` provider has nowhere to read its config. Phase 1 lands the seam for built-in methods only. Follow-up: a generic passthrough (e.g. `extra: dict[str, dict[str, Any]]` on `StorageProviderConfig`, handed to the factory) so out-of-tree providers get structured config. Captured in § Follow-ups; do not build speculatively.
- **D4 — Factory signature.** `Callable[[StorageProviderConfig], StorageProviderAbstract]` (whole config in, provider out) — lowest-churn move of the existing arm bodies, and keeps the GCP secrets read where it already is. *Alternative:* pass a pre-resolved typed sub-config + secrets provider explicitly (cleaner/more testable) — deferred; revisit if D3's passthrough makes "whole config in" awkward.
- **D5 — API version bump batched with secrets (DX-1).** Introduce `add_storage_provider` **and** `add_secrets_provider` in the same `PLUGIN_API_VERSION` 2→3 bump even though storage lands first, so external plugins re-declare `targets_api` once. If secrets is genuinely far behind, fall back to bumping per-feature and accept the double external-plugin update — but default to batching.

---

## Phased checklist

### Phase 0 — Confirm design
- [ ] Walk D1–D5 with the user; lock the token-openness (D1) and the API-bump batching (D5) — those two shape everything downstream.

### Phase 1 — The mechanism (core)
- [ ] Add `PLUGIN_API_VERSION` bump to 3 in `pipelex/plugins/contract.py` (batched with secrets per DX-1; do the bump once).
- [ ] Add `storage_providers: dict[str, StorageProviderFactoryFn]` field + `add_storage_provider(*, method, factory)` menu method to `PluginRegistrar` (`pipelex/plugins/registrar.py`), routed through `_add`. Add the `StorageProviderFactoryFn` type alias.
- [ ] New `pipelex/plugins/storage_provider_registry.py`: `StorageProviderRegistry` (mirror `OrchestratorRegistry`) with `get_optional` / `get_required` / `has` / `methods`.
- [ ] New `UnknownStorageMethodError` in `pipelex/plugins/exceptions.py` (message lists registered methods, mirroring `UnknownBootOrchestratorError`).
- [ ] Hub: `set_storage_provider_registry` / `get_storage_provider_registry` on `PipelexHub` + module-level accessor (mirror the four existing registry accessors in `pipelex/hub.py`).

### Phase 2 — The builtin plugin
- [ ] New `pipelex/plugins/storage/storage_plugin.py`: `StoragePlugin` (`name="storage"`, `targets_api=PLUGIN_API_VERSION`, `register` calling `add_storage_provider` for each built-in method).
- [ ] Module-level factory closures (`_make_local_storage_provider`, `_make_in_memory_storage_provider`, `_make_s3_storage_provider`, `_make_gcp_storage_provider`) holding the exact bodies moved from the deleted `match` arms (keep `lazy_validate()`; keep GCP's `get_secrets_provider()` read).
- [ ] Register `StoragePlugin()` in `BUILTIN_PLUGINS` and add `"storage"` to `CORE_UNCONDITIONAL_PLUGIN_NAMES` (`pipelex/plugins/builtins.py`).

### Phase 3 — Wire core boot to the registry
- [ ] In `pipelex.py` setup: after `build_registrar(...)`, build + `set_storage_provider_registry(StorageProviderRegistry(plugin_registrar.storage_providers))` alongside the other four registry sets (near lines 404-407).
- [ ] Replace the `make_storage_provider_from_config` block (lines 307-310) with the registry-selection path (explicit param > `registry.get_required(method=config.method)(config)`). Note ordering: storage still resolves after secrets is on the hub (keep the GCP secrets read working).
- [ ] Delete `make_storage_provider_from_config` and `pipelex/tools/storage/storage_provider_factory.py` if nothing else imports it (grep first — `show_cmd`, tests). Move any residual import of the provider classes into the plugin module.
- [ ] D1: relax `StorageProviderConfig.method` to open `str` (drop the strict enum bind at parse; validation happens at registry lookup).

### Phase 4 — Tests
- [ ] Unit: `StorageProviderRegistry` (`get_required` hit/miss → `UnknownStorageMethodError`; duplicate registration fail-loud through `_add`).
- [ ] Unit/boot: booting with each built-in `method` yields the right provider on the hub (parametrized). Include the s3/gcp arms with SDK absent → the factory raising `MissingDependencyError` only when selected, not at registration.
- [ ] Integration: an external test plugin registering a fake `method="test_mem"` (entry-point discovered) is selectable via config — mirror `tests/.../test_external_plugin.py` (the inference-backend external-plugin test) for the harness.
- [ ] `pipelex plugins list` shows `storage` (origin builtin) with its contributions.

### Phase 5 — Docs & changelog
- [ ] New `docs/under-the-hood/storage-provider-plugins.md`, mirroring `docs/under-the-hood/orchestrator-plugins.md` structure (seam-in-one-view, the contract, the factory closure + lazy optional-dep guard, config selection, authoring an out-of-tree provider). Add to mkdocs nav.
- [ ] Update `docs/under-the-hood/inference-backend-plugins.md` cross-links / any "the plugin seams are: inference, orchestrator" enumerations to include storage.
- [ ] CHANGELOG `[Unreleased]`: "breaking" — `PLUGIN_API_VERSION` 2→3 (external plugins must re-declare `targets_api`); storage provider is now a plugin seam.

---

## Verification / gates
- [ ] `make agent-check` (pyright, ruff, mypy, plxt, keyword-only guard).
- [ ] `make tb` — **critical here:** it tests the boot sequence incl. config loading; the `storage_config` model ↔ TOML ↔ selection path must stay in sync.
- [ ] `make agent-test` — full suite; catches the framework-positional and discovery edges the type checker can't.
- [ ] Manual: `pipelex plugins list`; a real run with `method="local"`; flip to `method="in_memory"` and confirm selection.

## Cross-repo consequence (release-gated, not this PR)
- `pipelex-mistralai-workflows` must bump `targets_api` to 3 (DX-1); it registers no storage provider and imports none of the removed symbols, so the bump is its only change. `pipelex-temporal` needs the bump **and** a code migration: its payload-codec factory (`pipelex_temporal/codec/codec_factory.py`) imports the now-removed `make_storage_provider_from_config` and must switch to `get_storage_provider_registry().get_required(method=...)`. Do both when the pipelex version carrying this lands, not before.

## Follow-ups (do not build now)
- **D3 external config passthrough** — generic `extra` sub-config on `StorageProviderConfig` for out-of-tree providers. This must also fix the **`uri_format` gap**: `StorageProviderConfig.uri_format` (read by `GeneratedContentFactory._build_storage_key` on every content store) is defined only for the four built-in methods and raises `StorageConfigError` on the `case _:` arm for any external token — so an external provider selects and boots cleanly but crashes on the first *generated-content* store. D3 must give external methods a `uri_format` (e.g. promote it to a top-level field, or a passthrough default). Until then the docs page flags external providers as usable for their own storage API but not yet as the generated-content backing store.
- **Cookbook example** — a `pipelex-storage-hello` external plugin mirroring the hello-inference-plugin cookbook track, once the seam is proven.
