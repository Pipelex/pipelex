> **Background — verdict still holds.** The boot-parity argument (API process and Temporal worker register the same class registry, user concept classes are loaded per-request not at boot) was re-checked against the live branch and is unchanged. Signature-validation does not alter this: signature pipes are loaded from the same per-request MTHDS payload as any other pipe. The `PARITY_HOLDS` verdict — and therefore the safety of "DRY → local" — stands.

# E. Parity Gate — API/Worker Library Preload Verification

## Why this gate exists

The plan in `D-plan.md` routes DRY runs to a local in-process `PipeRun` **even when the hub default is the Temporal-backed runner** (i.e. in the hosted `pipelex-api-deploy` runner). The original outside-voice review flagged one concrete risk:

> Edge case: user-defined dynamic concepts loaded only in the Temporal worker — would a local dry-run fail to resolve them?

If the Temporal worker process pre-loads things (extensions, plugins, library dirs, Python concept classes) that the API process does not, then a local DRY run inside the API would fail with "class not found" errors that the equivalent LIVE-on-Temporal run would not see. That would invalidate "DRY → always local" and the routing decision would have to change.

**Gate rule:** Verify parity BEFORE writing any implementation code. If parity holds, proceed. If parity diverges, redesign.

## Verdict: PARITY_HOLDS

Both API and Temporal worker boot through the same `Pipelex.make()` path with no pre-loaded `library_dirs`. User concept structure classes are not registered at process boot — they are dynamically generated and registered **per request** from the MTHDS payload via `ConceptFactory.make_from_blueprint() → register_class()`. The same MTHDS payload that the worker would receive over a workflow argument is the same payload the API receives in an HTTP request, so both processes end up with identical class registries for any given pipeline run.

## Evidence

### API boot (`pipelex-api` → FastAPI lifespan)

`pipelex-api/api/lifespan.py` calls `Pipelex.make(integration_mode=IntegrationMode.FASTAPI)` with no custom `library_dirs`. `Pipelex.setup()` (`pipelex/pipelex.py:162`) registers only:

- `CoreRegistryModels` (line 412) — built-in concept structures
- `TestRegistryModels` (line 415) — only when `unit_testing=True`
- Plugin manager (line 323) — loads plugins declared in config
- Template registries (lines 298–316)

No per-request user concept classes at this point. Global class registry starts essentially empty for user types.

### Worker boot (`pipelex-worker` → CLI `worker` command)

`pipelex/cli/commands/worker_cmd.py` calls `make_pipelex_for_cli(context=..., temporal_enabled=True)`, which invokes `Pipelex.make(integration_mode=IntegrationMode.CLI, temporal_enabled=True)`. Same `setup()` path as the API — same registries, no library preload.

**Identical boot sequence.**

### Per-request loading (where user classes appear)

`pipelex/pipeline/pipeline_run_setup.py` line 164: `PipelexInterpreter.make_pipelex_bundle_blueprint()` parses MTHDS content from the request. Line 182: `library_manager.load_from_blueprints()` loads parsed blueprints. Inside `library_manager.py:669`, `ConceptFactory.make_from_blueprint()` is called for each concept; inside `concept_factory.py` (lines 332, 373, 421, 452), generated structure classes are registered via `_get_class_registry().register_class(the_generated_class)`.

`hub.py:384–395`: `get_class_registry()` returns a per-workflow-scoped registry when one is set (Temporal contexts), otherwise the singleton KajsonManager class registry. **User concept structure classes are NOT preloaded at process boot.** They are registered dynamically per request from the MTHDS payload — same path on API and worker.

## Justification (under 150 words)

The API and worker:

- Boot with identical `Pipelex.setup()` paths
- Register only core/test models at startup
- Defer user-concept-class registration to per-request MTHDS loading
- Share the same global class registry (KajsonManager)

When a DRY run is dispatched locally in the API process, it loads the same MTHDS contents the corresponding LIVE Temporal run would, triggering the same `ConceptFactory.make_from_blueprint() → register_class()` flow. Structure classes resolve identically.

The only way parity could break: if `pipelex-api-deploy` introduced a `.pipelex/` override that pre-loads bundles the worker doesn't (or vice versa). Today it doesn't. Adding one would re-open this gate — anyone adding boot-time library preloads on one side must add the matching preload on the other, or the "DRY → always local" routing decision is no longer safe.

## Implication for future work

- If we ever ship "user-defined Python concept classes preloaded as a worker plugin" without an equivalent API-side load, this gate fails and DRY-in-API must route back through Temporal (or block).
- The gate is essentially a parity invariant on the boot path. Worth a CI check if drift becomes likely.
