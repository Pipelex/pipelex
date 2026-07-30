# A failed boot still leaves three non-singleton resources unreleased

**Status:** deferred, narrowed. The headline item this file used to describe — the **telemetry manager singleton** surviving a failed boot so the next boot adopted the dead one — is **fixed** on PR #1073 (`_release_after_failed_boot` now calls the guarded `telemetry_manager.teardown()`, which flushes and calls `clear_instance()`), pinned by `tests/unit/pipelex/test_runtime_boot_failed_boot_release.py` and verified to fail when the release is reverted.

A second item has since been fixed too, and it belonged to the *other* path — worth recording because this file used to scope itself to the failed-boot path alone, and that scoping is exactly what let the defect hide. `_teardown_runtime` kept `KajsonManager.teardown()`, `TemplateLoader.reset()` and `TemplateRegistry.clear()` in its `try`, above steps reachable through injectable abstract types, while its sibling had them in the `finally`. Since the same commit also moved the `MetaSingleton` de-registration into the `finally`, a raiser stopped failing loudly on the next boot ("already initialized") and started letting it **succeed against the previous boot's class registry** — the `KajsonManager` singleton hands back the surviving manager and discards the fresh registry. The three releases now sit in `_teardown_runtime`'s `finally` as well, so the *poisoning* half of the two lists is identical on both paths, and `test_runtime_boot_teardown_resilience.py` asserts no `KajsonManager` survives a raising teardown.

**The scope of this note is therefore both paths, not just the failed-boot one.** What remains is smaller and of a different kind.

## What is still not released on a failed boot

`_release_after_failed_boot()` releases the process globals that would otherwise **poison the next boot**: the hub config, `class_registry_scoping`, `KajsonManager`, the template registries, the telemetry singleton, and the `MetaSingleton` registration. It does not release three things that `teardown()` does:

| not released | what `teardown()` does | consequence |
|---|---|---|
| `sdk_client_manager` | `.teardown()` | vendor SDK clients constructed during `sdk_client_manager.setup()` are not closed |
| `reporting_delegate` | `.teardown()` | the delegate's own resources are not released |
| `func_registry` | `.teardown()` | registrations from this boot persist into the next one |

None of these is a *singleton-identity* bug — that was the telemetry case, where a stale registration silently replaced a fresh construction, and the `KajsonManager` case above. These are ordinary "resources not closed on the error path": the next boot builds its own `sdk_client_manager` and `reporting_delegate`, so it does not inherit broken state, it merely leaves the old ones dangling. `func_registry` is the closest to a real problem, being a module-level global whose entries carry over — and note that it carries over on the **normal** teardown path too, whenever a step above it raises, since it stayed in `_teardown_runtime`'s `try`. That was left alone deliberately: moving it would break the symmetry with `_release_after_failed_boot`, which cannot release it at all, and the symmetry is what makes the two lists reviewable against each other. It is the first thing the collapse below should pick up.

## Why it is deferred rather than patched

Adding three more guarded calls to the failure path is easy but is the wrong shape. `_release_after_failed_boot` exists only because `teardown()` is unsafe on a half-built instance — it reads `self.inference_manager` (and, on the interpreter half, `self.pipeline_manager`) unguarded, deliberately, so that a half-built teardown cannot look successful. Every resource added to the failure path widens a **second, hand-maintained copy** of the teardown list, which will drift from the first.

The better change is to collapse them:

1. Guard `inference_manager` and `pipeline_manager` in `_teardown_runtime` / `Pipelex.teardown` the way `telemetry_manager` and `reporting_delegate` already are.
2. Have `_release_after_failed_boot()` call the real teardown, keeping its own `try`/`finally` so the process-global un-poisoning still happens even if a manager teardown or a plugin callback raises.
3. Delete the duplicated list.

The risk to weigh in step 1 is the property the current code deliberately protects: guards let a half-built teardown *look* successful. The mitigation is that on the failure path the caller already knows the boot failed, so "looking successful" is not load-bearing there — unlike in `teardown()`, where it is. That asymmetry is the thing to decide, and it is a decision about lifecycle semantics rather than a missing line.

## Why not on PR #1073

That PR is a placement refactor whose claim is that a full `Pipelex` boot behaves identically. Collapsing the two teardown paths changes what *every* failed boot does for every existing caller and wants its own test matrix. The telemetry singleton was fixed there because it is a different class of defect — a stale singleton silently adopted by the next boot, production-reachable through `ensure_pipelex_booted`'s per-call lazy boot, and closed by one guarded call to an API written to never raise.
