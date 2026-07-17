# PR #1051 review notes — deferred items

Triage record for the SWE-agent review threads on [PR #1051](https://github.com/Pipelex/pipelex/pull/1051) (PipeCompose whole-stuff copies into native fields). Confirmed issues were fixed on the branch; this file captures the one item deliberately deferred.

## Defensive guard for genuine-union nested fields (greptile, deferred)

- **Reporter:** greptile (P1), review thread `PRRT_kwDOOwmMFc6RvbW7` on [PR #1051](https://github.com/Pipelex/pipelex/pull/1051), file `pipelex/pipe_operators/compose/structured_content_composer.py` (`_get_nested_field_class`).
- **Verdict:** the reported regression is a false positive — pre-PR code also passed genuine unions (`Address | Contact`, no `None` arm) through unchanged, since its unwrap was gated on `type(None) in args`. The only behavior change is for `X | Y | None`: pre-PR silently picked the first arm (worse), post-PR returns the union unchanged (honest passthrough, locked in by `tests/unit/pipelex/tools/test_annotation_utils.py`).
- **The real (pre-existing, latent) gap:** a hand-authored `StructuredContent` subclass with a genuine multi-arm union nested field, targeted by a NESTED construct, would flow the union into the nested composer's `output_class` and die downstream with a cryptic `AttributeError` on `model_fields` / `model_validate`. Unreachable through the supported authoring path: `StructureGenerator` has no UNION resolved-type kind, so generated models cannot carry genuine union fields.
- **Why deferred:** pre-existing, unreachable from generated structures, and out of scope for the PR. Whether to support hand-authored union fields at all is a design decision.
- **Recommendation if addressed:** raise `StructuredContentComposerTypeError` in `_get_nested_field_class` when the post-`unwrap_optional` annotation is still a union (`get_origin(...) in (Union, types.UnionType)`), naming the field, class, and union arms. Never resolve an arbitrary arm — silent first-arm picking is the anti-pattern this PR removed. Same reasoning applies to `_get_field_expected_type`, though a union there degrades more gracefully (falls through to keep-object).
