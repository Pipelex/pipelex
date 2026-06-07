# Deferred polish — additive multi-file library (from pre-landing /review)

> **Status: DEFERRED (P3 only).** Surfaced by the pre-landing `/review` on `feature/Support-recursive-design` (PR #970) via independent adversarial + testing + maintainability reviewers. None are bugs; the review verdict was **ship**. Both PR bots (greptile 5/5, cubic clean) and the full suite were green. These are recorded so they aren't lost — pick up only if touching this area again. Not worth re-triggering a CI/bot cycle on their own.

## Documentation / clarity nits

- **`domain_metadata_merge.py` summary line slightly overclaims "order-independent."** The merge is order-independent for the omission cases (a membership-only sibling never overrides a declared value), but two files declaring *different* non-empty values is genuinely first-seen-wins (it always warns). The docstring body already lists this case correctly ("both non-empty and different -> keep the first, warn"); only the one-line summary reads as if every case were order-independent. If editing this file, soften the summary to name the warned-conflict exception.

- **`library_crate_factory.py` `_reconcile_pipe_collision` tie-break drops a losing signature's `description` silently.** When two `PipeSignature`s for the same pipe have matching contracts but different `description`s, the deterministic `min(...)` tie-break keeps one and discards the other's description with no warning. This is harmless in practice — signature descriptions are advisory and a concrete definition's description wins outright once it arrives — but it's a silent drop. If touching reconciliation, add a one-line comment noting header descriptions are advisory (or warn, only if a real need appears; a warning here would be over-engineering for the DAG-forward-declared-by-multiple-callers edge).

- **`library_crate_factory.py` `or ""` coercion asymmetry.** The crate-factory merge coerces `merge_domain_metadata_field(...) or ""` because `DomainBlueprint.description` is non-optional, while the `DomainLibrary` merge of the same field needs no coercion because `Domain.description` is `str | None`. Behavior is correct; a one-line comment at the `or ""` would save a future reader the double-take.

## Test-coverage gap (low confidence)

- **`validate_bundle.py` `LibraryLoadingError` structured-forwarding branch is exercised but not asserted with a *populated* payload.** The `except LibraryError` arm forwards `blueprint_validation_errors` / `pipe_concept_validation_errors` when the error is a `LibraryLoadingError`. The generic-`LibraryError` `else` branch is well covered (undeclared concept/pipe). The `isinstance(LibraryLoadingError)` branch is reached only by the cycle-detection test, whose error carries *empty* lists — so no test proves a populated structured payload survives onto the resulting `ValidateBundleError` (which the CLI renders). A regression that collapsed the two branches would not be caught. If revisiting: one integration test driving a `LibraryLoadingError` with non-empty validation-error lists through `validate_bundle` and asserting the forwarded fields are populated (not `None`).

## Explicitly NOT worth doing (recorded so they aren't re-raised)

- `contracts_match` input-name divergence (same arity, same specs, different variable name): transitively covered by the dict comparison; a dedicated case would be over-testing.
- The `contract_match` `match is None` defensive return for a cross-package spec in `inputs`/`output`: documented as an impossible-in-blueprints input handled defensively; do not add a test for it.
- The inline undeclared-ref message in `concept_reference_validation.py`: fine as a one-off; only centralize next to `duplicate_ref_msg` if a third such message appears.
