# Secrets provider → `pipelex.plugins` plugin

Status: **COMPLETE.** All phases delivered — this vertical (Phases 3–4 of the master plan) mirrors the storage pattern ([storage-provider-plugin.md](storage-provider-plugin.md), which defines the shared "keyed registry + config-selected singleton" mechanism this plan reuses wholesale). The execution record (Phases 3–4 code + tests + docs, Phase 5 release gating) lived in the branch's root tracker. This plan reads as "mirror storage, swap the nouns."

Goal: turn the secrets provider into a formal plugin seam so third parties can ship `pipelex-secrets-<backend>` packages (Vault, AWS Secrets Manager, GCP Secret Manager, …) discovered via `pipelex.plugins` and selected at deploy time. The built-in `EnvSecretsProvider` becomes an unconditional builtin plugin.

Read [README.md](README.md) for the track's shared decisions (DX-1 API bump, DX-2 unconditional builtin, DX-3 external config follow-up).

---

## Cold-start context (the seam as it is today)

**Abstract base** — `pipelex/tools/secrets/secrets_provider_abstract.py`
- `SecretsProviderAbstract(ABC)` (line 6). Abstract: `get_required_secret(secret_id)`, `get_optional_secret(secret_id)`, `get_required_secret_specific_version(secret_id, *, version_id)`, `get_optional_secret_specific_version(secret_id, *, version_id)`, `set_secret_as_env_var(secret_id, *, version_id=LATEST_SECRET_VERSION_NAME)`. Concrete convenience `get_secret(secret_id) -> str` delegates to `get_required_secret`.
- `LATEST_SECRET_VERSION_NAME = "latest"` (line 3).

**The one implementation** — `pipelex/tools/secrets/env_secrets_provider.py`
- `EnvSecretsProvider` (line 9). Reads env vars via `get_required_env` / `get_optional_env`. The two `*_specific_version` methods `raise NotImplementedError`; `set_secret_as_env_var` is a no-op `pass`. **This is a single-impl seam** — the whole point of the plan is to open it.

**Boot injection** — `pipelex/pipelex.py`
- Import line 90; `setup()` param `secrets_provider: SecretsProviderAbstract | None = None` (line 186).
- **Hardcoded default:** line 212 `secrets_provider = secrets_provider or EnvSecretsProvider()` — constructed **early**, before the gateway check (comment: "needed for gateway check"), and before config-driven subsystems. This early construction is the main structural wrinkle (see § The wrinkle).
- Passed to telemetry factory (288) and to two setup helpers (345, 375). Set on hub line 306. `make()` mirror: param 560, forwarded 636.

**Config** — **none today.** No field selects the provider; it is hardcoded to Env via the `or EnvSecretsProvider()` fallback. There is no `secrets_config` in `pipelex.toml` or `configs.py`. This plan introduces one.

**Hub accessors** — `pipelex/hub.py`: `set_secrets_provider` (183), `get_required_secrets_provider()` (294), module-level `get_secrets_provider()` (472) and `get_secret(secret_id)` (607). Consumers (~4 files): `storage_provider_factory.py:62` (GCP creds — see the storage↔secrets coupling in the storage plan), `linkup_search_worker.py`, `linkup_extract_worker.py`, `show_cmd.py`. `secrets_utils.py` takes a `secrets_provider` param explicitly rather than pulling from the hub. **None of these change.**

**Pattern to mirror:** identical to the storage plan — `PipelexPlugin` contract, the registrar `_add` helper, `OrchestratorRegistry` as the read-view template, `docling_plugin.py` for the lazy optional-dep closure shape, `CORE_UNCONDITIONAL_PLUGIN_NAMES`. See [storage-provider-plugin.md](storage-provider-plugin.md) § Cold-start context for the exact refs.

---

## The wrinkle: secrets is constructed before config-driven subsystems — but this is fine (Decision W RESOLVED → W-A)

Storage is selected *after* config load and *after* secrets is on the hub — clean. Secrets looked different: `EnvSecretsProvider()` is built at `pipelex.py:212`, **early**, with the comment `# needed for gateway check`. That comment turned out to be **stale**, which is what makes W-A clean.

**Verified 2026-07-06 (locks Decision W):**

- **The gateway-check path is entirely secrets-free.** Neither `pipelex/system/pipelex_service/remote_config_fetcher.py` (`fetch_remote_config`, `make_dummy_remote_config`) nor `pipelex/system/pipelex_service/pipelex_service_config.py` (`is_pipelex_gateway_enabled`) references secrets in any form — no param, no hub read. Grep for `get_secret|secrets_provider|get_secrets_provider` in both is empty. The line-211 comment is wrong; nothing between line 212 and the telemetry factory needs secrets.
- **The true first consumer of `secrets_provider` in `setup()` is `make_telemetry_manager` at line 288** (passed as a param). The hub secrets slot isn't set until line 306, so nothing in between could be reading it from the hub either.
- **`build_registrar` is pure over config.** `PluginRegistrar.__init__(*, config)` takes only config; `build_registrar(config=get_config())` touches no hub, no models, no telemetry, constructs no SDK. `get_config()` is valid at `setup()` entry (config is loaded in `__init__` via `setup_config`, before `setup` runs). It's called exactly once today (line 393) and only re-read later by `_resolve_hub_slot` (line 505) and teardown (line 516).

**⇒ Decision W = W-A, confirmed, zero ordering risk.** Move the single `build_registrar(config=get_config())` call (currently `pipelex.py:393-394`) up to **right after `boot_orchestrator` is set (after line 209), before line 212**. Then:

1. Build `SecretsProviderRegistry(plugin_registrar.secrets_providers)`, set it on the hub.
2. Resolve secrets: `if secrets_provider is None: secrets_provider = registry.get_required(method=get_config().pipelex.secrets_config.method)(get_config().pipelex.secrets_config)`.
3. **Delete** the hardcoded `secrets_provider or EnvSecretsProvider()` line 212 and its stale comment.
4. Everything downstream is untouched — telemetry (288), hub set (306), and the existing registry constructions / slot application at 404-418 keep referencing the already-built `self._plugin_registrar`. Only the *build call* moves up; its downstream consumers stay put.

Bonus (recommended, not required): move the `boot_orchestrator` validation gate (`pipelex.py:401-403`, `UnknownBootOrchestratorError`) up alongside the build call — it's a pure check on the registrar and moving it fails fast on a typo'd orchestrator before any secrets/gateway work.

**W-B is not needed** and is not the plan — recorded only so a future reader knows it was considered: keep Env hardcoded for a pre-gateway bootstrap, then re-resolve and overwrite the hub. Rejected because W-A is clean; W-B would leave a transient provider and a hub re-set for no benefit.

---

## The mechanism (reuse storage's)

Same "keyed registry + config-selected singleton" as the storage plan:

- New registrar menu method `add_secrets_provider(*, method: str, factory: SecretsProviderFactoryFn)` where `SecretsProviderFactoryFn = Callable[[SecretsProviderConfig], SecretsProviderAbstract]`, into `registrar.secrets_providers: dict[str, SecretsProviderFactoryFn]`, via `_add`.
- New read-view `SecretsProviderRegistry` (`pipelex/plugins/secrets_provider_registry.py`) mirroring `OrchestratorRegistry` / the new `StorageProviderRegistry`.
- New `UnknownSecretsMethodError` in `pipelex/plugins/exceptions.py`.
- New config: `SecretsProviderConfig(ConfigModel)` with `method: str = Field(strict=False)` (default `"env"`); built-in token `"env"` needs no sub-config. Add `[pipelex.secrets_config]\nmethod = "env"` to `pipelex/pipelex.toml`, and wire `secrets_config` into the config model where storage_config lives (`pipelex/tools/secrets/secrets_config.py` new file + a field on the owning config — confirm placement with the config-owner; the storage one hangs under `pipelex.storage_config`, so `pipelex.secrets_config` is the natural sibling).
- Builtin `SecretsPlugin` (`name="secrets"`, unconditional per DX-2) whose `register` calls `add_secrets_provider(method="env", factory=_make_env_secrets_provider)`; `_make_env_secrets_provider(config)` just returns `EnvSecretsProvider()`.
- Boot selects via the registry at the point Decision W lands; the explicit `setup(secrets_provider=...)` param still wins ahead of registry selection.

Because there's only one built-in method, introducing a config selector for a single impl looks like over-engineering — but the selector *is* the feature: it's what lets an external `vault` provider be chosen. `"env"` stays the default and the unconditional builtin, so out-of-the-box behavior is byte-identical.

---

## Decisions (recommended defaults — confirm before building)

- **W — Selection point. ✅ RESOLVED = W-A (verified 2026-07-06).** Move the pure `build_registrar(config=get_config())` call up to after line 209 / before line 212; registry-select secrets there; delete the hardcoded `or EnvSecretsProvider()` and its stale `# needed for gateway check` comment. Confirmed zero ordering risk — the gateway path is secrets-free (see § The wrinkle for the evidence). No Phase-0 investigation needed; this is now a build instruction.
- **S1 — Open method token + config selector.** Mirror storage D1: `SecretsProviderConfig.method` is an open `str`, validated at registry lookup, default `"env"`.
- **S2 — One unconditional builtin `SecretsPlugin`.** `name="secrets"`, added to `CORE_UNCONDITIONAL_PLUGIN_NAMES` (DX-2).
- **S3 — API bump batched with storage (DX-1).** `add_secrets_provider` ships in the same `PLUGIN_API_VERSION` 2→3 bump as `add_storage_provider`. If secrets lands in a much later PR than storage, that PR does its own bump and external plugins take a second `targets_api` update — acceptable but avoid if the two land close together.
- **S4 — External config surface (follow-up).** Same as storage D3: `SecretsProviderConfig` gets a generic passthrough for out-of-tree providers as a scoped follow-up, not Phase 1. `"env"` needs no sub-config, so Phase 1 has nothing to add.

---

## Phased checklist

### Phase 0 — Confirm design
- [x] **Decision W RESOLVED = W-A** (verified 2026-07-06) — gateway path is secrets-free; `build_registrar` is pure over config; move the build call ahead of line 212. See § The wrinkle. No further tracing needed.
- [ ] Confirm with the config owner where `secrets_config` hangs (sibling of `storage_config` under `pipelex.*`).
- [ ] Confirm the `PLUGIN_API_VERSION` bump is shared with storage (DX-1 / S3) or standalone.

### Phase 1 — The mechanism (core) — *skip the parts storage already landed*
- [ ] If storage already bumped `PLUGIN_API_VERSION` to 3 **and** added `add_storage_provider`: only add `add_secrets_provider` + `secrets_providers` field to `PluginRegistrar`. If storage hasn't landed: do the 2→3 bump here too.
- [ ] `add_secrets_provider(*, method, factory)` menu method via `_add`; `SecretsProviderFactoryFn` alias.
- [ ] New `pipelex/plugins/secrets_provider_registry.py`: `SecretsProviderRegistry` (`get_optional` / `get_required` / `has` / `methods`).
- [ ] New `UnknownSecretsMethodError` in `pipelex/plugins/exceptions.py`.
- [ ] Hub: `set_secrets_provider_registry` / `get_secrets_provider_registry` + module accessor.

### Phase 2 — Config
- [ ] New `SecretsProviderConfig(ConfigModel)` (`pipelex/tools/secrets/secrets_config.py`), `method: str = Field(strict=False)`; no default in the class per config rules — default lives in TOML.
- [ ] Add `[pipelex.secrets_config] method = "env"` to `pipelex/pipelex.toml`; wire `secrets_config` into the owning config model.
- [ ] Add the same block to `.pipelex/pipelex.toml` override **only if** it's a genuine client-override case — secrets backend selection plausibly is (a deployer picks vault vs env), so include it with the real `method = "env"` value, never commented out (house rule).
- [ ] `make tb` after config changes — config model ↔ TOML must stay in sync or boot fails.

### Phase 3 — The builtin plugin + boot wiring (Decision W = W-A)
- [ ] New `pipelex/plugins/secrets/secrets_plugin.py`: `SecretsPlugin` + `_make_env_secrets_provider(config)` returning `EnvSecretsProvider()`.
- [ ] Register `SecretsPlugin()` in `BUILTIN_PLUGINS`; add `"secrets"` to `CORE_UNCONDITIONAL_PLUGIN_NAMES`.
- [ ] **Move the `build_registrar(config=get_config())` call** (`pipelex.py:393-394`) up to after line 209 / before line 212; keep `self._plugin_registrar = plugin_registrar`. Downstream registry constructions + slot application (404-418) stay put referencing the already-built registrar. Optionally move the `boot_orchestrator` gate (401-403) up with it for fail-fast.
- [ ] Build + `set_secrets_provider_registry(...)` right after the moved build call.
- [ ] **Delete** `pipelex.py:211-212` (the stale `# needed for gateway check` comment + `secrets_provider = secrets_provider or EnvSecretsProvider()`); replace with `if secrets_provider is None: secrets_provider = get_secrets_provider_registry().get_required(method=get_config().pipelex.secrets_config.method)(get_config().pipelex.secrets_config)` — explicit `setup(secrets_provider=...)` param still wins.
- [ ] Drop the now-unused `EnvSecretsProvider` import from `pipelex.py` (it moves to the plugin module).

### Phase 4 — Tests
- [ ] Unit: `SecretsProviderRegistry` hit/miss (`UnknownSecretsMethodError`) + duplicate fail-loud.
- [ ] Boot: default config yields `EnvSecretsProvider` on the hub; explicit `setup(secrets_provider=...)` still overrides.
- [ ] Integration: external test plugin registering a fake `method="test_secret"` is selectable via config (mirror the inference external-plugin test).
- [ ] Guard the storage↔secrets ordering: a boot with a non-env secrets method must still be on the hub before storage's GCP arm reads it (add/extend a boot-order assertion).
- [ ] `pipelex plugins list` shows `secrets`.

### Phase 5 — Docs & changelog
- [ ] New `docs/under-the-hood/secrets-provider-plugins.md` (mirror the storage/orchestrator doc; emphasize the lazy optional-dep closure for SDK-backed providers like Vault/AWS). mkdocs nav.
- [ ] Update any "the plugin seams are …" enumerations to include secrets.
- [ ] CHANGELOG `[Unreleased]`: secrets provider is now a plugin seam; `PLUGIN_API_VERSION` bump note if not already recorded by the storage change.

---

## Verification / gates
- [ ] `make agent-check`.
- [ ] `make tb` — critical (new `secrets_config` ↔ TOML ↔ selection).
- [ ] `make agent-test`.
- [ ] Manual: `pipelex plugins list`; a run with default `method="env"`; confirm `get_secret(...)` still resolves env vars.

## Cross-repo consequence (release-gated)
- Same as storage: our Temporal and Mistral Workflows plugins bump `targets_api` to 3 (only once, if batched with storage per DX-1).

## Follow-ups (do not build now)
- **S4 external config passthrough** for out-of-tree secrets providers.
- **First real external provider** (Vault or AWS Secrets Manager) as the proof-of-seam, likely as a private/closed package if it targets the hosted platform.
- **Retire the `*_specific_version` `NotImplementedError`s** in `EnvSecretsProvider` only if a consumer needs them — out of scope here.
