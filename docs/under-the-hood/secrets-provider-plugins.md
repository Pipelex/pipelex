---
title: "Secrets Provider Plugins"
description: "How Pipelex selects a secrets backend by config, the keyed-registry-plus-config-selected-singleton seam a secrets plugin rides, and how to author an out-of-tree pipelex-secrets-<backend> package."
---

# Secrets Provider Plugins

Every credential Pipelex reads — an API key, a service-account file path, a signing secret — is resolved through a single **secrets provider** set on the hub at boot. Which provider that is comes entirely from data: one config field, `secrets_config.method`, names a backend, and a **secrets plugin** is what teaches Pipelex how to build the provider for that method.

Core names no secrets backend by import or by string. The built-in `env` provider (reads secrets from environment variables) is a plugin too — the always-on `SecretsPlugin` — riding the exact same seam an out-of-tree `pipelex-secrets-<backend>` package (Vault, AWS Secrets Manager, GCP Secret Manager, …) would. This page documents that seam, the factory contract a plugin registers, and how to write one.

This is the second application of the mechanism the [storage provider](storage-provider-plugins.md) seam introduced; secrets reuses it wholesale, so the two pages describe the same shape with the nouns swapped.

---

## A different shape from the inference/orchestrator seams

The [inference-backend](inference-backend-plugins.md) and [orchestrator](orchestrator-plugins.md) registries are selected **per call** — a model's `sdk`, a request's `orchestration_mode`. Secrets is not: it is a **process-global singleton selected by its own config key**, independent of the orchestrator. So it rides the same **keyed registry + config-selected singleton** mechanism storage uses:

> Plugins register N provider factories into a registry keyed by an open `method` token. At boot, core reads `secrets_config.method`, looks that token up in the registry, and calls the factory to produce the one provider set on the hub.

This is deliberately **not** a hub slot (those are orchestrator-coupled, claimed only when `boot_orchestrator == plugin.name`). Secrets selection has nothing to do with the orchestrator, so it gets its own registry and its own config key — the sibling of `storage_config.method`.

---

## The seam in one view

```
boot (Pipelex.setup)
  └─ build_registrar(config)                       # pure, import-light
       ├─ for each plugin in BUILTIN_PLUGINS         (SecretsPlugin is one)
       └─ for each installed "pipelex.plugins" entry point
            └─ plugin.register(registrar)            # side-effect-free
                 └─ registrar.add_secrets_provider(method=…, factory=…)
  └─ SecretsProviderRegistry(registrar.secrets_providers)    # stored on the hub
  └─ secrets_provider = registry.get_required(method=secrets_config.method)(secrets_config)
  └─ set_secrets_provider(secrets_provider)          # the one provider every consumer reads
```

There is no `match secrets_config.method:` anywhere in boot — the token set is open, so validation *is* the registry lookup. Adding a backend means registering a factory for its token; nothing in core changes. Every downstream consumer (`get_secret(...)`, telemetry credentials, the storage `gcp` arm, search/extract workers) keeps calling `get_secrets_provider()` and is unaffected by which method was selected.

### Where in boot secrets is resolved

Secrets is resolved **early** — right after plugin discovery, after the gateway/terms precondition gate but before the telemetry factory (its first in-process consumer) and well before storage selection. Two consequences that this ordering guarantees:

- **Telemetry** receives the config-selected secrets provider when it is constructed.
- **Storage's `gcp` factory** reads the config-selected secrets provider from the hub at *its* apply-point (it resolves `GCP_CREDENTIALS_FILE_PATH`) — secrets is already on the hub by then. This ordering is pinned by an integration test that boots a non-`env` secrets method alongside `gcp` storage and asserts the gcp arm read the external provider.

### Injection precedence

`Pipelex.setup` resolves the secrets provider in this order:

1. an explicit `setup(secrets_provider=...)` parameter (test/host injection) — always wins;
2. the config-selected registry factory (`get_required(method=secrets_config.method)(config)`).

There is no separate core default: the built-in `SecretsPlugin` *is* the default supplier of the `env` method, so an ordinary boot always resolves through step 2.

---

## The contract: `SecretsProviderFactoryFn`

A secrets backend is a typed **callable** — whole secrets config in, provider out (`pipelex/plugins/secrets_provider_registry.py`):

```python
SecretsProviderFactoryFn = Callable[[SecretsProviderConfig], SecretsProviderAbstract]
```

Passing the whole `SecretsProviderConfig` (not a pre-resolved sub-config) is deliberate: it lets a factory read whatever it needs — an SDK-backed provider (Vault, AWS Secrets Manager) reads its own settings — at the boot apply-point, never at registration. The built-in `env` factory ignores the config entirely.

A plugin contributes one factory per method it serves by calling the registrar menu in its `register`, passing the token as a raw string:

```python
registrar.add_secrets_provider(method="vault", factory=_make_vault_secrets_provider)
```

`register` is **side-effect-free** — it may call the registrar menu and nothing else (no hub access, no I/O, no SDK import). That is what keeps `build_registrar` safe to run more than once (at boot, and again for the `pipelex plugins list` diagnostic).

### Import-light registration, deferred dependency

The factory is a plain callable stored at registration and **invoked only at the boot apply-point**. Two invariants follow, and they are what let an SDK-backed provider ship without weighing down every boot:

- **Import-light.** The plugin module must import no backend SDK at module load. The built-in `SecretsPlugin` needs none (the `env` provider reads environment variables); an out-of-tree `pipelex-secrets-vault` plugin must keep its `hvac`/`boto3`/etc. import *inside* the provider's methods (or its factory), never at module top-level, so discovery stays import-light even when the extra is installed.
- **Fail at use, not at boot.** An optional dependency raises `MissingDependencyError` (naming the package and the `pipelex[<extra>]` install hint) when the backend is *used*, not when it is registered or selected.

---

## The built-in `SecretsPlugin`

`pipelex/plugins/secrets/secrets_plugin.py` is the reference secrets plugin. It is **core-unconditional** — a secrets provider is required infra, so it joins `CORE_UNCONDITIONAL_PLUGIN_NAMES` and cannot be disabled into a boot with no secrets provider:

```python
class SecretsPlugin:
    name = "secrets"
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_secrets_provider(method="env", factory=_make_env_secrets_provider)
```

The `env` factory ignores its config and returns a bare `EnvSecretsProvider` — the `config` parameter exists only to conform to `SecretsProviderFactoryFn`; an SDK-backed external provider is where reading the config earns its keep:

```python
def _make_env_secrets_provider(config: SecretsProviderConfig) -> SecretsProviderAbstract:
    return EnvSecretsProvider()
```

`env` is a single-impl backend: `EnvSecretsProvider` resolves `get_required_secret` / `get_optional_secret` from environment variables, and its versioned reads (`*_specific_version`) raise `NotImplementedError` because environment variables have no version history. A full external provider (Vault, AWS Secrets Manager) implements those versioned reads.

---

## Selecting a method by config

`secrets_config.method` is an **open `str` token** (Decision S1), not a closed enum. The built-in uses `"env"`; an external `pipelex-secrets-<backend>` plugin registers its own (e.g. `"vault"`). A config naming an external method **parses fine** — the token is stored verbatim and its installability is validated later, at registry lookup:

```toml
# .pipelex/pipelex.toml
[pipelex.secrets_config]
method = "vault"          # an out-of-tree provider — selected iff its plugin is installed
```

Whether that token names an *installed* provider is validated at **registry lookup**, not at parse: an unknown method surfaces as `UnknownSecretsMethodError` at boot, which is the right layer — it lists the registered methods so the fix is obvious.

!!! note "External-provider config surface is a scoped follow-up"
    `SecretsProviderConfig` today carries only `method` — the built-in `env` backend needs no per-method sub-config. An out-of-tree `vault` provider has nowhere to read *its* structured config yet; a generic passthrough for external providers is a captured follow-up (Decision S4), not built speculatively. Until it lands, an external provider reads its own config from the environment or its own file.

---

## Fail-loud guarantees

| Condition | Error |
|-----------|-------|
| `secrets_config.method` names no registered provider | `UnknownSecretsMethodError` (lists the registered methods) |
| two plugins register the same `method` | `DuplicateSecretsProviderError` (names both plugins) |
| `name` (`"secrets"`) in `plugins.disabled` | `CoreUnconditionalPluginDisabledError` |
| entry point raises while loading/registering | `BrokenPluginError` |
| optional SDK missing at use | `MissingDependencyError` (package + `pipelex[<extra>]` hint) |

The duplicate detection is the same fail-loud `_add` helper the inference/orchestrator/storage menus use — a conflict names both contributing plugins, so a collision between two installed secrets packages is unambiguous.

---

## Authoring an out-of-tree secrets plugin

A third-party secrets plugin is a distribution that:

1. implements a `SecretsProviderAbstract` subclass — `get_required_secret` / `get_optional_secret`, the versioned `*_specific_version` reads, and `set_secret_as_env_var` — deferring any SDK import into those methods (import-light);
2. defines a plugin class (`name`, `targets_api`, `register`) whose `register` calls `add_secrets_provider(method="<token>", factory=...)` — and nothing else;
3. advertises itself under the `pipelex.plugins` entry-point group:

```toml
# pyproject.toml of your plugin package
[project.entry-points."pipelex.plugins"]
vault_secrets = "pipelex_secrets_vault.plugin:VaultSecretsPlugin"
```

Installing the distribution makes the method selectable (`secrets_config.method = "vault"`); uninstalling removes it. No core change, no central registration list — *presence* is the source of truth. A discovered plugin can be quarantined without uninstalling via the `plugins.disabled` denylist (matched against the entry-point name *before* load, so a broken install can still be disabled to recover startup — see [Inference Backend Plugins](inference-backend-plugins.md) for the shared discovery/denylist machinery).

Use `pipelex plugins list` to see every discovered plugin, what each contributed, and its denylist state.

---

## Related

- [Storage Provider Plugins](storage-provider-plugins.md) — the sibling config-selected-singleton seam this one mirrors; its `gcp` arm reads the secrets provider at boot
- [Secrets Provider Injection](../advanced/secrets-provider-injection.md) — supplying a custom secrets provider from your own vault or secrets manager
- [Inference Backend Plugins](inference-backend-plugins.md) — the per-call sibling seam and the shared discovery/denylist machinery
- [Orchestrator Plugins](orchestrator-plugins.md) — the other per-call seam, plus the hub-slot mechanism these config-selected seams deliberately avoid
- [Error Model](error-model.md) — how these errors render and dereference
- [Architecture Overview](architecture-overview.md)
