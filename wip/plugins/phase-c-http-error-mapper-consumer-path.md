# Phase C decision — how `pipelex-api` reaches the F3 HTTP-error mappers

**Status:** deferred design decision, to settle when Phase C (`pipelex-api` decoupling) starts. Not a bug. Surfaced by the Phase A `/code-review` (finding #1).

## Context

Phase A added the F3 seam exactly as the plan scoped it: `PluginRegistrar.add_http_error_mapper(*, exc_type, to_error_report)` plus the read accessor `PluginRegistrar.get_http_error_mappers()`. It deliberately did **not** push the collected mappers onto the hub.

This differs from how the *other* plugin contributions are exposed: orchestrators / inference backends / model listers each get a hub registry (`set_orchestrator_registry(...)` etc.) that any consumer reads via a module-level `get_*_registry()` in `pipelex/hub.py`. The HTTP-error mappers have no such hub surface, and the boot registrar is held privately as `Pipelex._plugin_registrar` (no public getter).

## The question for Phase C

How does `pipelex-api` obtain the mappers at app construction (`api/main.py` → `register_exception_handlers`)? Two viable paths:

1. **Rebuild in the API (no further core change).** Call the documented pure, repeatable `build_registrar(config=get_config())` and iterate `registrar.get_http_error_mappers()`. Precedent: `pipelex/cli/commands/plugins_cmd.py` already calls `build_registrar` standalone. Cost: a third `build_registrar` pass (after CLI-build harvest is gone, this is boot + api-construction) — pure and import-light, so cheap, but it re-runs every plugin's `register()` and is *a* registrar, not *the* boot registrar (fine for a pure function whose output is deterministic for a given config).

2. **Expose the boot registrar from core.** Either (a) a public `get_plugin_registrar()` getter on `Pipelex`/hub returning the already-built registrar, or (b) a full `HttpErrorMapperRegistry` on the hub mirroring the orchestrator pattern. Either keeps a single registrar instance but is a **second core change**, which the per-repo handoff table frames as "Phase C = pipelex-api only".

## Recommendation (not yet ratified)

Default to **option 1** — it keeps Phase C a pure `pipelex-api` change (matching the per-repo table) and `build_registrar`'s contract explicitly blesses repeated calls. Choose option 2(b) only if a second consumer of the mappers appears, or if rebuilding in the API proves to interleave badly with boot ordering. Whichever is chosen, record it in the Phase C as-built.

## Why not just do it now

Per the deferral convention: this is a design tradeoff, not a silent bug, and the plan scoped Phase A to the registrar method + accessor only. Pre-building a hub registry now would be speculative surface for a consumer that doesn't exist yet in this repo. See [[feedback_defer_design_tradeoff_findings]].

## Phase B seam refinement — two consequences to note in the Phase C as-built

The Phase A seam was refined during Phase B (core commit `75196e2e3`): `add_http_error_mapper` now takes a lazy `exc_type_provider` thunk, resolved by `get_http_error_mappers()` at the host's read time, so a plugin's `register()` never imports the orchestrator SDK to name its exception class. Two downstream consequences for the Phase C consumer (surfaced by the Phase B `/code-review`, both deferred — fail-loud either way, no code change):

1. **Duplicate-mapper detection now fires at the host's app-construction read time, not at boot discovery.** `get_http_error_mappers()` is what runs the providers and raises `DuplicateHttpErrorMapperError`. For the locked one-orchestrator-per-image flavor model a collision can't occur, so this is theoretical — but a mis-packaged image with two mapper-contributing plugins fails when `pipelex-api` builds the app, not at boot. Phase C should know the raise lands at its `register_exception_handlers` call site.

2. **`pipelex plugins list` shows a generic `"http error mapper"` contribution line** (no `{exc_type.__qualname__}`), unlike the `family:sdk` / `mode` detail the other contributions carry — an unavoidable consequence of not resolving the type at register. If the per-type label matters, add an optional `display_label: str` to `add_http_error_mapper` (the plugin passes `"temporalio.TemporalError"` as a plain string). Speculative surface today; skip until something needs it.
