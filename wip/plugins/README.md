# Provider plugins track — storage & secrets

Two features that promote existing dependency-injection seams to formal `pipelex.plugins` entry-point plugins, so third parties can ship `pipelex-storage-azure` / `pipelex-secrets-vault` packages selected at deploy time.

- **[storage-provider-plugin.md](storage-provider-plugin.md)** — the storage provider seam (local / in_memory / s3 / gcp today). **Land this first** — it has the real multi-implementation need and exercises the new pattern end to end.
- **[secrets-provider-plugin.md](secrets-provider-plugin.md)** — the secrets provider seam (env only today). Lands second, mirroring the storage pattern; validates that the mechanism generalizes to a second seam.

Both were selected after a full audit of the boot-time DI seams (see the classification below). They are the only two seams that pass all three plugin criteria; everything else is either already a plugin, a boot-orchestrator-owned hub slot, or a population/config point that should stay one.

## The shared new pattern these introduce

Neither seam maps onto an existing plugin pattern. The current keyed registries (inference backends, model listers, orchestrators, bundle validators) are selected **per-request/per-model** by a wire or model field. The hub slots (content generator, pipe router, pipe run, task manager, isolated-execution probe) are singletons but selected by **one name gate** — `plugins.boot_orchestrator` — because they move as a coherent set with the runtime flavor.

Storage and secrets are neither. Each is a **process-global singleton selected by its *own* config key**, independent of the orchestrator. So they need a net-new mechanism:

> **Keyed registry + config-selected singleton.** Plugins register N provider factories into a registry keyed by an open method token (mirroring `OrchestrationMode`). At boot, core reads a single config field (`storage_config.method` / `secrets_config.method`), looks that token up in the registry, and calls the factory to produce the one provider set on the hub.

This is deliberately **not** a `HubSlot` — hub slots are orchestrator-coupled (claimed inside `register` iff `boot_orchestrator == plugin.name`). Storage/secrets selection has nothing to do with the orchestrator, so reusing the slot machinery would wrongly couple them. The storage plan defines this pattern in full (§ "The new mechanism"); the secrets plan references it.

## Cross-cutting decisions (apply to both)

- **DX-1 — Batch the plugin-API version bump.** Discovery version-checks `targets_api` against `PLUGIN_API_VERSION` with **strict equality** (`pipelex/plugins/discovery.py`, `_register_plugin`), so *any* additive menu growth is a breaking bump that forces every external plugin to re-declare `targets_api`. Introduce **both** new registrar menu methods (`add_storage_provider` and `add_secrets_provider`) under a **single** `PLUGIN_API_VERSION` bump (2 → 3), even though the two features land in sequence, to avoid double-breaking the external plugins. The known external plugins that must bump their `targets_api` to 3: `pipelex-temporal`, `pipelex-mistralai-workflows`. (Per the workspace "no backward compatibility" principle, that's acceptable — note it in changelogs; there is no transition shim.)
  - *Option not taken:* relax discovery to accept `targets_api <= PLUGIN_API_VERSION` for additive growth. That would make menu additions non-breaking but changes the plugin-system contract semantics — out of scope for this track; raise separately if the coarse-bump churn becomes painful.
- **DX-2 — The builtin provider plugin is unconditional.** Storage and secrets are required infra: if the config-selected method has no registered factory, boot must fail loud. The builtin `StoragePlugin` / `SecretsPlugin` therefore join `CORE_UNCONDITIONAL_PLUGIN_NAMES` (`pipelex/plugins/builtins.py`) so they can't be disabled into a broken boot.
- **DX-3 — External-provider config surface is a scoped follow-up.** `StorageProviderConfig` / the new `SecretsProviderConfig` have fixed, typed per-method sub-models. An out-of-tree provider (`azure`, `vault`) needs somewhere to read *its* config. Phase 1 of each plan lands the seam for the built-in methods only; a generic passthrough sub-config for external providers is captured as a follow-up in each plan, not built speculatively.

## Boot-audit classification (why only these two)

- **Already plugins:** inference backends (LLM/img-gen/extract/search, incl. OCR & web search), model listers, orchestrators, bundle validators, HTTP error mappers.
- **Boot-orchestrator-owned hub slots (leave as-is):** content generator, pipe router, pipe run, task manager, isolated-execution probe — they move as a set with the runtime flavor.
- **Population / config points (NOT plugins):** class registry, func registry, model deck, template sets. Where under-modular (templates especially, which lack even an injection param today), the fix is a normal injection seam, not entry-point discovery.
- **Prove-a-second-impl-first:** telemetry (don't double-wrap OTel's own exporter plugins), reporting/cost delegate (looks host-runtime-owned, not shelf-installable).
- **Promote (this track):** **secrets** and **storage**.
