# Storage Provider Plugins

Every asset Pipelex persists — a generated image, an uploaded document, a payload blob — is written through a single **storage provider** set on the hub at boot. Which provider that is comes entirely from data: one config field, `runtime.storage.method`, names a backend, and a **storage plugin** is what teaches Pipelex how to build the provider for that method.

Core names no storage backend by import or by string. The built-in providers (`local`, `in_memory`, `s3`, `gcp`) are a plugin too — the always-on `StoragePlugin` — riding the exact same seam an out-of-tree `pipelex-storage-<backend>` package would. This page documents that seam, the factory contract a plugin registers, and how to write one.

---

## A different shape from the inference/orchestrator seams

The [inference-backend](inference-backend-plugins.md) and [orchestrator](orchestrator-plugins.md) registries are selected **per call** — a model's `sdk`, a request's `orchestration_mode`. Storage is not: it is a **process-global singleton selected by its own config key**, independent of the orchestrator. So it rides a net-new mechanism the track calls a **keyed registry + config-selected singleton**:

> Plugins register N provider factories into a registry keyed by an open `method` token. At boot, core reads `runtime.storage.method`, looks that token up in the registry, and calls the factory to produce the one provider set on the hub.

This is deliberately **not** a hub slot (those are orchestrator-coupled, claimed only when `boot_orchestrator == plugin.name`). Storage selection has nothing to do with the orchestrator, so it gets its own registry and its own config key. The same mechanism also backs the [secrets provider](secrets-provider-plugins.md) seam (`runtime.secrets.method`).

---

## The seam in one view

```
boot (Pipelex.setup)
  └─ build_registrar(config, builtin_plugins=BUILTIN_PLUGINS, …)   # pure, import-light
       ├─ for each built-in plugin                   (StoragePlugin is one)
       └─ for each installed entry point in the requested groups
            #  "pipelex.plugins.kernel" alone on a kernel-only boot; both groups on a full one
            └─ plugin.register(registrar)            # side-effect-free
                 └─ registrar.add_storage_provider(method=…, factory=…)
  └─ StorageProviderRegistry(registrar.storage_providers)    # stored on the hub
  └─ storage_provider = registry.get_required(method=runtime.storage.method)(runtime.storage)
  └─ set_storage_provider(storage_provider)          # the one provider every consumer reads
```

There is no `match runtime.storage.method:` anywhere in boot — the token set is open, so validation *is* the registry lookup. Adding a backend means registering a factory for its token; nothing in core changes. Every downstream consumer (input normalizer, content generator, PDF/image utilities, delivery executor) keeps calling `get_storage_provider()` and is unaffected by which method was selected.

The provider is resolved **after** the secrets provider is on the hub, so a factory may perform a hub secrets read at its apply-point (the `gcp` factory does — see below).

### Injection precedence

`Pipelex.setup` resolves the storage provider in this order:

1. an explicit `setup(storage_provider=...)` parameter (test/host injection) — always wins;
2. the config-selected registry factory (`get_required(method=runtime.storage.method)(config)`).

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

- **Import-light.** The plugin module must import no backend SDK at module load. Registering the built-in `s3`/`gcp` factories pulls in neither `aiobotocore` nor `google-cloud-storage` — the SDK guard lives *inside* the provider's I/O methods (`_get_session` / `_get_bucket`), not its `__init__`. Selecting `s3` therefore *constructs* an `S3StorageProvider` even with the extra absent; the guard fires only on the first actual load/store.
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

`runtime.storage.method` is an **open `str` token**, not a closed enum. The built-ins use the `StorageMethod` values; an external `pipelex-storage-<backend>` plugin registers its own (e.g. `"azure"`). A config naming an external method **parses fine** — the per-method sub-config validator requires a matching sub-config only for the four built-in tokens and lets any other token through:

```toml
# .pipelex/pipelex.toml
[runtime.storage]
method = "azure"          # an out-of-tree provider — no built-in sub-config required
```

Whether that token names an *installed* provider is validated at **registry lookup**, not at parse: an unknown method surfaces as `UnknownStorageMethodError` at boot, which is the right layer — it lists the registered methods so the fix is obvious.

!!! note "External-provider config surface is a scoped follow-up"
    `StorageProviderConfig` has fixed, typed per-method sub-models, so an out-of-tree `azure` provider has nowhere to read *its* structured config yet. The seam for built-in methods lands first; a generic passthrough sub-config for external providers is a possible follow-up, not built speculatively. Until it lands, an external provider reads its own config from the environment or its own file. **One live gap:** `StorageProviderConfig.uri_format` (read by `GeneratedContentFactory._build_storage_key` on every content store, where it renders the FILENAME only — its placeholders are `{hash}` and `{extension}`, while the prefix `{storage_scope}/generated/` is composed in code so a config cannot omit it) is only defined for the four built-in methods and raises `StorageConfigError` for any other token — so an external provider selects and boots cleanly but a *generated-content store* through it fails until every storage method has a `uri_format`. External providers are therefore usable today for their own direct storage API, not yet as the backing store for generated content.

---

## Fail-loud guarantees

| Condition | Error |
|-----------|-------|
| `runtime.storage.method` names no registered provider | `UnknownStorageMethodError` (lists the registered methods) |
| published under the retired `pipelex.plugins` group | `RetiredPluginEntryPointGroupError` (names the plugins and the group each should move to) |
| two plugins register the same `method` | `DuplicateStorageProviderError` (names both plugins) |
| `name` (`"storage"`) in `runtime.plugins.disabled` | `CoreUnconditionalPluginDisabledError` |
| entry point raises while loading/registering | `BrokenPluginError` |
| optional SDK missing at use | `MissingDependencyError` (package + `pipelex[<extra>]` hint) |

The duplicate detection is the same fail-loud `_add` helper the inference/orchestrator menus use — a conflict names both contributing plugins, so a collision between two installed storage packages is unambiguous.

---

## Authoring an out-of-tree storage plugin

A third-party storage plugin is a distribution that:

1. implements a `StorageProviderAbstract` subclass — the three hooks `_load_with_metadata`, `_store`, and `public_url` — deferring any SDK import into those methods (import-light); `_store` publishes the bytes whole or not at all, never leaving an object cut short under its key, and takes the bytes' SHA-256 as `checksum_sha256_hex`, which it sends when its storage can check a write's checksum and ignores otherwise (see [Checksums](#checksums)), and a provider that can read a byte range or an object's size without its bytes also overrides `_load_head` and `_load_size`, whose defaults load the whole object, one that can create an object only when its key is free also overrides `_store_if_absent` (see [Create-only writes](#create-only-writes)), and one that keeps a client open between operations closes it in `teardown` (see [Clients and teardown](#clients-and-teardown));
2. defines a plugin class (`name`, `targets_api`, `register`) whose `register` calls `add_storage_provider(method="<token>", factory=...)` — and nothing else;
3. advertises itself under the `pipelex.plugins.kernel` entry-point group — a storage provider is kernel-layer, and the group is how a plugin declares that (see [Inference Backend Plugins](inference-backend-plugins.md#shipping-it-as-an-out-of-tree-plugin) for what each group means and what happens if you pick the wrong one; the pre-split `pipelex.plugins` group is retired and now fails startup):

```toml
# pyproject.toml of your plugin package
[project.entry-points."pipelex.plugins.kernel"]
azure_storage = "pipelex_storage_azure.plugin:AzureStoragePlugin"
```

Installing the distribution makes the method selectable (`runtime.storage.method = "azure"`); uninstalling removes it. No core change, no central registration list — *presence* is the source of truth. A discovered plugin can be quarantined without uninstalling via the `runtime.plugins.disabled` denylist (matched against the entry-point name *before* load, so a broken install can still be disabled to recover startup — see [Inference Backend Plugins](inference-backend-plugins.md) for the shared discovery/denylist machinery).

Use `pipelex plugins list` to see every discovered plugin, the entry-point group it was found under, what each contributed, and its denylist state. The **Group** column is the first thing to read when a plugin is missing: a built-in shows `—`, and an external plugin that resolved to the wrong layer shows it there.

### Create-only writes

`store_if_absent(data=…, key=…, content_type=…, checksum_sha256_hex=…)` creates an object only when its key holds none, and answers whether this call created it: an object already there is never replaced, and the answer is then `False`. With a checksum, the bytes are checked against it before anything is written, a mismatch raising `StorageChecksumMismatchError`, and the provider sends it on when its storage can check it. The API server's blob store writes every blob and tree listing this way, so a bucket refusing unconditional writes under those prefixes refuses none of them.

Each built-in provider makes the condition atomic in its storage: S3 sends `If-None-Match: *` with the SHA-256 as `x-amz-checksum-sha256` and reads a `412` as the key held, and on a `409`, which S3 answers while another write or delete of the key is in flight, sends the write again after a short pause, a bounded number of times, failing once the conflict outlasts them; GCS uploads on generation 0; the local provider writes a temporary file and hard-links it to the key, which fails when the name is taken, and fails loudly when something other than a file is there or a file stands where one of the key's folders should be; the in-memory one checks its dict. A provider that does not override `_store_if_absent`, such as an external plugin written before it existed, keeps working through the default, which looks the key up with `_load_size` and then calls `_store`, so two writers racing on one free key may both write, which a caller keying objects by their content can live with since both write the same bytes, but which a storage refusing unconditional writes would refuse.

### Checksums

`store(data=…, key=…, content_type=…, checksum_sha256_hex=…)` takes the bytes' SHA-256 in lowercase hexadecimal from a caller that hashed them already and hands it to `_store`; the default `_store_if_absent` hands its checksum to `_store` too, so a provider overriding only `_store` receives it on both paths. Unlike `store_if_absent`, `store` does not check it against the bytes: the caller hashed the bytes it hands over, so hashing them again here would only repeat the work. The generated content factory is such a caller: a generated file's key carries the first 16 hexadecimal digits of its SHA-256, and the write carries the whole digest.

The S3 provider sends the SHA-256 with every write it makes, `store` and `store_if_absent` alike, so S3 refuses a body that does not hash to it, answering `BadDigest`, which the provider raises as `StorageS3Error`, and keeps the checksum beside the object, where a `HeadObject` with `ChecksumMode=ENABLED` returns it as `ChecksumSHA256`. A reader of the bucket therefore learns the full hash of any object the provider wrote without reading its bytes. Each write passes `ChecksumAlgorithm="SHA256"`, and with the caller's digest `ChecksumSHA256` as well, which botocore sends as the `x-amz-checksum-sha256` header; without one, botocore hashes the body as it sends it and sends the checksum as a trailer of the upload. The client never signs the payload (`payload_signing_enabled` is off). botocore already leaves it unsigned when it computes the checksum itself; with the caller's digest, the checksum header is among the request's signed headers, sent over TLS, which protects the body as well as a signed payload would, and botocore, which recognises only a checksum of its own, would otherwise hash the whole body a second time just to sign it. The other built-in providers take no SHA-256 checksum: GCS and its client library check a CRC32C or an MD5 of the upload, and a local file and the in-memory store have no checksum of their own.

### Clients and teardown

The S3 provider keeps one aiobotocore client per event loop. The first operation a loop runs opens it, and every later operation on that loop shares it and its pool of connections, `S3_MAX_POOL_CONNECTIONS` of them, so an operation pays neither a client build nor a new TLS connection to S3; an operation finding every connection busy waits for one. It must be one per loop, because an aiobotocore client and the aiohttp session under it belong to the loop that opened them, and the runtime reaches storage from more than one: a command line runs each step under its own `asyncio.run`, and a test suite runs a loop per class.

A client is closed on its own loop, at whichever of two moments comes first. A loop that shuts its asynchronous generators down, as `asyncio.run` does once its tasks have ended, closes the client as it shuts down, through a generator the provider started on that loop with the client. The runtime's teardown calls `teardown()` on the provider it booted with, which schedules the close on a loop still running, the server's own loop when an API server shuts down, and runs a loop no longer running until the close is done. A loop closed without shutting its generators down leaves its client open, with nothing left to close it on, which aiohttp reports as an unclosed session. A close that fails is logged at DEBUG and never raised out of the teardown, so the other loops' clients are still closed and the rest of the runtime's teardown still runs. An operation after a teardown opens a new client.

The GCS provider needs none of this: its client is the synchronous `google-cloud-storage` one, built once and called in worker threads, whose connections belong to no loop.

`StorageProviderAbstract.teardown()` holds nothing by default. A plugin's provider that does its own I/O through a client it keeps between operations closes that client there. The teardown is synchronous and may run on the very thread running the loop the client belongs to, so a client bound to a loop is closed by scheduling its close on that loop, never by waiting for it, and the provider still works afterwards, opening a new client on its next operation. It should not raise: a raise skips the releases the runtime's teardown makes after it.

### A provider is not the tenant boundary

A provider reads any key it is handed with the process's own credentials, and it should: it has no notion of whose run asked. On a host serving several tenants, what bounds a run's reads is the **read scope** the host passes with the run, which the content-generation leaves and the input seam check before they call a provider. A key outside that prefix, and any local path, is refused there, so a provider never sees it. A self-hosted deployment serving one tenant passes no read scope and reads as before. See [Distributed Content Generation](distributed-content-generation.md#what-a-leaf-may-read-the-read-scope) for the rule and where it runs.

---

## Related

- [Secrets Provider Plugins](secrets-provider-plugins.md) — the sibling config-selected-singleton seam riding the same mechanism; the `gcp` factory above reads its provider
- [Inference Backend Plugins](inference-backend-plugins.md) — the per-call sibling seam and the shared discovery/denylist machinery
- [Orchestrator Plugins](orchestrator-plugins.md) — the other per-call seam, plus the hub-slot mechanism storage deliberately avoids
- [Error Model](error-model.md) — how these errors render and dereference
- [Architecture Overview](architecture-overview.md)
