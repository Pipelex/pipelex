# A failed boot leaves the telemetry manager singleton live, and the next boot adopts the dead one

**Status:** deferred. Pre-existing on `dev` — not introduced by the boot split (PR #1073) — but surfaced by the gstack pre-landing review of it, and the release helper's docstring used to overclaim in a way that hid it. The docstring is corrected; the leak is not fixed.

## The leak

`RuntimeBoot._release_after_failed_boot()` (formerly the inline block in `Pipelex.make`) releases:

- the runtime hub's config, `class_registry_scoping`, `KajsonManager`, `TemplateLoader`, `TemplateRegistry`, the `MetaSingleton` registration — and, since PR #1073, the plugin teardown callbacks.

It does **not** release:

| singleton / state | cleared only in | consequence of a failed boot |
|---|---|---|
| `TelemetryManager` (`ABCSingletonMeta`, `clear_instance()`) | `teardown()` | the next boot adopts the **same object**; its `__init__` never re-runs, and `TelemetryManagerAbstract.get_instance()` resolves to the dead manager |
| `sdk_client_manager` | `teardown()` | clients not closed |
| `reporting_delegate` | `teardown()` | not torn down |
| `func_registry` | `teardown()` | retains registrations |

## Why it is reachable in production

`ensure_pipelex_booted` (`pipelex/runtime_bridge/bootstrap.py`) is a per-call lazy boot on the bridge hot path. The most common boot failure — `models_manager.setup()` raising on a missing model deck or missing credentials — fires *after* the telemetry factory has already constructed and `setup()` the manager. So a first request whose boot dies there leaves every later request in that process exporting spans through a torn-down/dead telemetry manager.

This is independent of the boot split: the ordering (telemetry before models) is unchanged from `dev`, and so is the set of things the release path skips.

## Why it was not fixed on PR #1073

Widening the release path is a change to **failure-path semantics**, not a comment fix:

- `TelemetryManager.clear_instance()` is currently reachable only from `teardown()`. Calling it from the failure path means deciding what "half-set-up telemetry" means — the manager may have been constructed but not `setup()`, or `setup()` may have half-run.
- The same question applies to `sdk_client_manager.teardown()` and `reporting_delegate.teardown()`: both are *already* guarded with `if self.…:` in `_teardown_runtime`, so they are safe to call on a half-built instance — which means the omission was never justified by the "only safe entry points" rationale the docstring used to give. That rationale explained `inference_manager` and `pipeline_manager` (genuinely unguarded) and was silently extended to cover things it did not explain.
- Doing it properly probably means making `_teardown_runtime` itself safe on a half-built instance and calling *it* from the failure path, which collapses the two paths into one — a good outcome, but it changes what a failed boot does for every existing caller and wants its own test matrix.

Fixing it inside a placement refactor would have buried a real semantic change in a diff whose whole claim is that behaviour is unchanged.

## Suggested shape

Prefer collapsing the two paths over adding a sixth line to the failure path:

1. Make `_teardown_runtime()` tolerant of a half-built instance — guard `inference_manager` and `pipeline_manager` the way `telemetry_manager` and `reporting_delegate` already are.
2. Have `_release_after_failed_boot()` call it, keeping the `try`/`finally` so the process-global un-poisoning still happens if a plugin callback or a manager teardown raises.
3. Add `TelemetryManager.clear_instance()` to that path, and a test that a boot failing at `models_manager.setup()` leaves `TelemetryManagerAbstract.get_instance()` unresolvable rather than resolving to a dead object.

The risk to weigh in step 1 is the one the current code deliberately accepts: guards let a half-built teardown *look* successful. The mitigation is that the failure path already has a caller who knows the boot failed, so "looking successful" is not load-bearing there — unlike in `teardown()`, where it is.
