# `_revalidate_against_object_class` exists three times, in two repos

Surfaced while reviewing PR #1076 (`refactor/Exec`). Not caused by that PR — but that PR made the copies **diverge**, which is what turns tolerable duplication into a trap.

## The three sites

| where | shape | dump |
|---|---|---|
| `pipelex/cogt/content_generation/content_generator.py` — `_revalidate_against_object_class` | `BaseModel` in | `model_dump(serialize_as_any=True)` |
| `pipelex-temporal` — `tprl_content_generation/content_generator_in_workflow.py:52` | `BaseModel` in | `model_dump(mode="json", serialize_as_any=True)` |
| `pipelex/cogt/content_generation/content_generator.py` — inlined in `make_search_structured` | `dict` in | n/a (already a dict) |

All three implement the same contract: validate the leaf's data against the caller's original class, and on the dry path re-raise a `ValidationError` as `DryRunObjectFidelityError` naming the class and the `examples` / `mock_format` remedy. The dry/live split, the `try`/`except`, and most of the explanatory docstring are duplicated verbatim.

## Why the copies exist

The first two are the two implementations of `ContentGeneratorProtocol` — the direct/inline backend and the workflow arm. The plugin could not reuse core's version for one reason only: it is `_`-private. It already imports `assignment_models`, `content_generator_protocol` and `exceptions` from that same package, so nothing else was in the way.

The one real difference is `mode="json"`, needed because the Temporal object crossed a payload boundary and some fields only round-trip cleanly in json mode. That is a parameter, not a reason for a second function.

## What #1076 changed, and why it matters now

Core's copy gained an `isinstance(raw_obj, object_class)` short-circuit, to stop the caller's validators running twice when the leaf already built from the real class. The Temporal copy did **not** get it.

That is correct today: across `workflow.execute_activity` the object is always an instance of the class rebuilt from `__kajson_class_source__`, never of `object_class`, so the conversion is always needed. But it is now a latent trap — if that path ever hands back the caller's real class (a local activity, an in-process shortcut, a converter change), it will double-validate exactly the way core's did before #1076, and nothing links the two files to make anyone notice. The reasoning about instructor returning a *subclass*, which is why the check is `isinstance` and not `type(...) is`, lives only in core's docstring.

## What doing it looks like

1. Promote one public helper into `pipelex.cogt.content_generation` — the plugin already imports from that package, so this needs no new boundary.
2. Give it the dump mode as a parameter rather than forking the function. **Do not** unify blindly on `mode="json"` for the in-process path: it coerces values (datetime → str and back) and the round-trip's edge cases are unaudited — see `wip/refactoring/boundary-revalidation-round-trip-is-unaudited.md`, which is about exactly this conversion.
3. Fold the `make_search_structured` inline into it, or give the dict-in case its own thin entry point on the same helper, so the fidelity-error contract has one home.
4. Then delete the plugin's copy and have it call the shared one.

The prize is not line count — it is that the fidelity-error contract, and the `isinstance`-not-`type` reasoning, stop being things you have to already know to get right.

## Related

- `wip/refactoring/boundary-revalidation-round-trip-is-unaudited.md` — what the shared helper's boundary arm actually does, and what has not been checked about it.
- `wip/refactoring/structured-search-still-rebuilds-in-process.md` — the search path's other half of the same story.
