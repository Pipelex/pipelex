---
title: "Storage Provider Plugins"
description: "How Pipelex selects a storage backend by config, the keyed-registry-plus-config-selected-singleton seam a storage plugin rides, and how to author an out-of-tree pipelex-storage-<backend> package."
---

# Storage Provider Plugins

Every asset Pipelex persists — a generated image, an uploaded document, a payload blob — is written through a single **storage provider** set on the hub at boot. Which provider that is comes entirely from data: one config field, `storage_config.method`, names a backend, and a **storage plugin** is what teaches Pipelex how to build the provider for that method.

Core names no storage backend by import or by string. The built-in providers (`local`, `in_memory`, `s3`, `gcp`) are a plugin too — the always-on `StoragePlugin` — riding the exact same seam an out-of-tree `pipelex-storage-<backend>` package would. This page documents that seam, the factory contract a plugin registers, and how to write one.

---

## A different shape from the inference/orchestrator seams

The [inference-backend](inference-backend-plugins.md) and [orchestrator](orchestrator-plugins.md) registries are selected **per call** — a model's `sdk`, a request's `orchestration_mode`. Storage is not: it is a **process-global singleton selected by its own config key**, independent of the orchestrator. So it rides a net-new mechanism the track calls a **keyed registry + config-selected singleton**:

> Plugins register N provider factories into a registry keyed by an open `method` token. At boot, core reads `storage_config.method`, looks that token up in the registry, and calls the factory to produce the one provider set on the hub.

This is deliberately **not** a hub slot (those are orchestrator-coupled, claimed only when `boot_orchestrator == plugin.name`). Storage selection has nothing to do with the orchestrator, so it gets its own registry and its own config key. The same mechanism also backs the [secrets provider](secrets-provider-plugins.md) seam (`secrets_config.method`).

---

## The seam in one view

```
boot (Pipelex.setup)
  └─ build_registrar(config, builtin_plugins=BUILTIN_PLUGINS, …)   # pure, import-light
       ├─ for each built-in plugin                   (StoragePlugin is one)
       └─ for each installed "pipelex.plugins" entry point
            └─ plugin.register(registrar)            # side-effect-free
                 └─ registrar.add_storage_provider(method=…, factory=…)
  └─ StorageProviderRegistry(registrar.storage_providers)    # stored on the hub
  └─ storage_provider = registry.get_required(method=storage_config.method)(storage_config)
  └─ set_storage_provider(storage_provider)          # the one provider every consumer reads
```

There is no `match storage_config.method:` anywhere in boot — the token set is open, so validation *is* the registry lookup. Adding a backend means registering a factory for its token; nothing in core changes. Every downstream consumer (input normalizer, content generator, PDF/image utilities, delivery executor) keeps calling `get_storage_provider()` and is unaffected by which method was selected.

The provider is resolved **after** the secrets provider is on the hub, so a factory may perform a hub secrets read at its apply-point (the `gcp` factory does — see below).

### Injection precedence

`Pipelex.setup` resolves the storage provider in this order:

1. an explicit `setup(storage_provider=...)` parameter (test/host injection) — always wins;
2. the config-selected registry factory (`get_required(method=storage_config.method)(config)`).

There is no separate core default: the built-in `StoragePlugin` *is* the default supplier of every method, so an ordinary boot always resolves through step 2.

---

## The contract: `StorageProviderFactoryFn`

A storage backend is a typed **callable** — whole storage config in, provider out (`pipelex/plugins/storage_provider_registry.py`):

```python
StorageProviderFactoryFn = Callable[[StorageProviderConfig], StorageProviderAbstract]
```

Passing the whole `StorageProviderConfig` (not a pre-resolved sub-config) is deliberate: it lets a factory read whatever it needs — including a hub secrets read — at the boot apply-point, never at registration.

A plugin contributes one factory per method it serves by calling the registrar menu in its `register`, passing the token as a raw string:

```python
registrar.add_storage_provider(method="azure", factory=_make_azure_storage_provider)
```

`register` is **side-effect-free** — it may call the registrar menu and nothing else (no hub access, no I/O, no SDK import). That is what keeps `build_registrar` safe to run more than once (at boot, and again for the `pipelex plugins list` diagnostic).

### Import-light registration, deferred dependency

The factory is a plain callable stored at registration and **invoked only at the boot apply-point**. Two invariants follow, and they are what let an SDK-backed provider ship without weighing down every boot:

- **Import-light.** The plugin module must import no backend SDK at module load. Registering the built-in `s3`/`gcp` factories pulls in neither `aioboto3` nor `google-cloud-storage` — the SDK guard lives *inside* the provider's I/O methods (`_get_session` / `_get_bucket`), not its `__init__`. Selecting `s3` therefore *constructs* an `S3StorageProvider` even with the extra absent; the guard fires only on the first actual load/store.
- **Fail at use, not at boot.** An optional dependency raises `MissingDependencyError` (naming the package and the `pipelex[<extra>]` install hint) when the backend is *used*, not when it is registered or selected.

---

## The built-in `StoragePlugin`

`pipelex/providers/storage/storage_plugin.py` is the reference storage plugin. It is **core-unconditional** — storage is required infra, so it joins the kernel layer's `KERNEL_CORE_UNCONDITIONAL_PLUGIN_NAMES` — composed into `CORE_UNCONDITIONAL_PLUGIN_NAMES` at the boot entrypoint — and cannot be disabled into a boot with no storage:

```python
class StoragePlugin:
    name = "storage"
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_storage_provider(method=StorageMethod.LOCAL, factory=_make_local_storage_provider)
        registrar.add_storage_provider(method=StorageMethod.IN_MEMORY, factory=_make_in_memory_storage_provider)
        registrar.add_storage_provider(method=StorageMethod.S3, factory=_make_s3_storage_provider)
        registrar.add_storage_provider(method=StorageMethod.GCP, factory=_make_gcp_storage_provider)
```

Each factory is a module-level closure that None-checks its sub-config, calls `lazy_validate()`, and constructs the provider. The built-in tokens are the `StorageMethod` enum values (`"local"`, `"in_memory"`, `"s3"`, `"gcp"`); because a `StrEnum` key compares and hashes equal to its plain-`str` form, boot's plain-`str` `config.method` resolves them.

The `gcp` factory is the one that reads a secret from the hub — legal because the factory runs at the boot apply-point, after the secrets provider is set, never inside `register`:

```python
def _make_gcp_storage_provider(config: StorageProviderConfig) -> StorageProviderAbstract:
    ...
    return GcpStorageProvider(
        bucket_name=config.gcp.bucket_name,
        project_id=config.gcp.project_id,
        credentials_file_path=get_secrets_provider().get_required_secret(secret_id="GCP_CREDENTIALS_FILE_PATH"),
        signed_urls_lifespan=config.gcp.signed_urls_lifespan,
    )
```

---

## Selecting a method by config

`storage_config.method` is an **open `str` token** (Decision D1), not a closed enum. The built-ins use the `StorageMethod` values; an external `pipelex-storage-<backend>` plugin registers its own (e.g. `"azure"`). A config naming an external method **parses fine** — the per-method sub-config validator requires a matching sub-config only for the four built-in tokens and lets any other token through:

```toml
# .pipelex/pipelex.toml
[pipelex.storage_config]
method = "azure"          # an out-of-tree provider — no built-in sub-config required
```

Whether that token names an *installed* provider is validated at **registry lookup**, not at parse: an unknown method surfaces as `UnknownStorageMethodError` at boot, which is the right layer — it lists the registered methods so the fix is obvious.

!!! note "External-provider config surface is a scoped follow-up"
    `StorageProviderConfig` has fixed, typed per-method sub-models, so an out-of-tree `azure` provider has nowhere to read *its* structured config yet. The seam for built-in methods lands first; a generic passthrough sub-config for external providers is a captured follow-up (Decision D3), not built speculatively. Until it lands, an external provider reads its own config from the environment or its own file. **One live gap:** `StorageProviderConfig.uri_format` (read by `GeneratedContentFactory._build_storage_key` on every content store) is only defined for the four built-in methods and raises `StorageConfigError` for any other token — so an external provider selects and boots cleanly but a *generated-content store* through it fails until D3 gives external methods a `uri_format`. External providers are therefore usable today for their own direct storage API, not yet as the backing store for generated content.

---

## Fail-loud guarantees

| Condition | Error |
|-----------|-------|
| `storage_config.method` names no registered provider | `UnknownStorageMethodError` (lists the registered methods) |
| two plugins register the same `method` | `DuplicateStorageProviderError` (names both plugins) |
| `name` (`"storage"`) in `plugins.disabled` | `CoreUnconditionalPluginDisabledError` |
| entry point raises while loading/registering | `BrokenPluginError` |
| optional SDK missing at use | `MissingDependencyError` (package + `pipelex[<extra>]` hint) |

The duplicate detection is the same fail-loud `_add` helper the inference/orchestrator menus use — a conflict names both contributing plugins, so a collision between two installed storage packages is unambiguous.

---

## Authoring an out-of-tree storage plugin

A third-party storage plugin is a distribution that:

1. implements a `StorageProviderAbstract` subclass — the three hooks `_load_with_metadata`, `_store`, and `public_url` — deferring any SDK import into those methods (import-light);
2. defines a plugin class (`name`, `targets_api`, `register`) whose `register` calls `add_storage_provider(method="<token>", factory=...)` — and nothing else;
3. advertises itself under the `pipelex.plugins` entry-point group:

```toml
# pyproject.toml of your plugin package
[project.entry-points."pipelex.plugins"]
azure_storage = "pipelex_storage_azure.plugin:AzureStoragePlugin"
```

Installing the distribution makes the method selectable (`storage_config.method = "azure"`); uninstalling removes it. No core change, no central registration list — *presence* is the source of truth. A discovered plugin can be quarantined without uninstalling via the `plugins.disabled` denylist (matched against the entry-point name *before* load, so a broken install can still be disabled to recover startup — see [Inference Backend Plugins](inference-backend-plugins.md) for the shared discovery/denylist machinery).

Use `pipelex plugins list` to see every discovered plugin, what each contributed, and its denylist state.

---

## Related

- [Secrets Provider Plugins](secrets-provider-plugins.md) — the sibling config-selected-singleton seam riding the same mechanism; the `gcp` factory above reads its provider
- [Inference Backend Plugins](inference-backend-plugins.md) — the per-call sibling seam and the shared discovery/denylist machinery
- [Orchestrator Plugins](orchestrator-plugins.md) — the other per-call seam, plus the hub-slot mechanism storage deliberately avoids
- [Error Model](error-model.md) — how these errors render and dereference
- [Architecture Overview](architecture-overview.md)
