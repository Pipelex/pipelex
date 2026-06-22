# Deferred: `start` / `validate_verdict` mode-dispatch duplication (pipelex-api)

Surfaced during the `/code-review` of the `feature/Orchestrator-dispatched-validate` staged diff in `pipelex-api`. Deferred (not fixed) as a design tradeoff, not a clear win.

## The observation

`ApiRunner.start` and `ApiRunner.validate_verdict` (both in `api/routes/pipelex/pipeline.py`) now share the same three-line dispatch shape:

1. `execution_mode = resolve_execution_mode(requested_execution_mode, config=get_api_config())` — resolve the effective mode FIRST, so a forbidden per-request override is refused with a 403 before any library load / registry lookup.
2. `arm = get_<orchestrator|bundle_validator>_registry().get_optional(mode=execution_mode)`.
3. `if arm is None: raise Missing<Orchestrator|BundleValidator>Error(mode=execution_mode)`.

The "resolve mode FIRST … refused (403) here, before any … load" comment is also near-duplicated between the two methods.

The two sites differ only in the registry getter (`get_orchestrator_registry` vs `get_bundle_validator_registry`) and the error class (`MissingOrchestratorError` vs `MissingBundleValidatorError`).

## Why deferred (not fixed)

A helper such as `_resolve_arm(registry_getter, missing_error_cls)` would collapse the two sites to one, but:

- It is only ~4 lines × 2, and the two registries / error types are genuinely distinct seams.
- The helper would take a registry-getter callable and an exception class as parameters — that is *added* indirection and surface area, the opposite of removing complexity.
- The user's review brief for this change was explicit: clean, solid software, no speculative abstractions, and "in case of any doubt, do NOT fix." This is a judgment call, not an unambiguous win.

So the code is left as-is.

## When this becomes worth doing

Revisit the extraction only if a concrete pull arrives:

- A third surface acquires the same resolve-then-dispatch shape (the contract would then live in three places).
- The override-policy ordering guarantee changes (e.g. the "403 before any load" point moves), so a maintainer would otherwise have to remember to edit every site and keep the parallel comments in sync.

At that point a single small helper carries its weight; until then the duplication is the lower-churn, lower-surface choice.
