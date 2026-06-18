# Deferred: structured validation-errors follow-ups

Code-review follow-ups on the structured wiring/concept/type validation-errors work (`feature/Validate-api-render-format`). The two consumer-facing findings from that review (concept-owned refs mislabeled as `pipe_validation`; the missing dependency only in the message) were **fixed** in that change. The items below were judged lower-severity and **deferred** here rather than fixed inline — each is a contained, independent pickup. None is a silent correctness regression; they are coverage gaps, asymmetries, and one cleanup.

The surface: `validate_bundle` → `_translate_to_validate_bundle_error` (`pipelex/pipeline/validate_bundle.py`) → `build_validation_error_items` (`pipelex/pipeline/validation_errors.py`) → `ErrorReport.validation_errors[]` (`ValidationErrorItem` in `pipelex/base_exceptions.py`). The three categorizing sites are `categorize_blueprint_validation_error` (`pipelex/core/interpreter/validation_error_categorizer.py`), `validate_concept_references_in_blueprints` (`pipelex/libraries/concept_reference_validation.py`), and `Library.validate_pipe_library_with_libraries` (`pipelex/libraries/library.py`).

## 1. Missing-`type` pipe not categorized (`union_tag_not_found`)

`categorize_blueprint_validation_error` only categorizes `error["type"] == "union_tag_invalid"` as `UNKNOWN_PIPE_TYPE` (the case where a pipe declares a `type` matching no known operator/controller). A pipe block that **omits `type` entirely** raises pydantic `union_tag_not_found`, which the branch does not match — so it falls through to the uncategorized `log.warning(...)` residual with no `error_type` / `pipe_code`.

This is asymmetric with the present-but-unknown-`type` case the feature fixes: both are "bad/absent pipe type" from the author's view, but only one is categorized.

**Shape when picked up:** match both `union_tag_invalid` and `union_tag_not_found` in that branch (the loc is still `("pipe", <code>)`, so `pipe_code` populates the same way), and add a fixture with a `[pipe.foo]` block that omits `type`. Verify pydantic's exact error code for the missing-discriminator case first.

## 2. Dependency validation fails fast; only the first missing sub-pipe is reported

In `Library.validate_pipe_library_with_libraries`, the `raise LibraryLoadingError(...)` for an unresolved dependency sits **inside** the `for sub_pipe_code in pipe.pipe_dependencies()` loop, so a controller with several missing dependencies surfaces only **one** `unresolved_pipe_dependency` item. This contrasts with `validate_concept_references_in_blueprints`, which deliberately accumulates every unresolved reference and reports them together ("the author sees all of them at once").

**Shape when picked up:** accumulate `PipesAndConceptValidationErrorData` items across the dependency loop (and likely across pipes) and raise once at the end, mirroring the concept-ref accumulation. Note this is a behavioral change to a fail-fast path that predates the feature; scope the blast radius (other callers of `validate_pipe_library_with_libraries` rely on it raising on the first failure) before changing it.

## 3. Qualified same-domain ref yields a qualified `concept_code`

In `validate_concept_references_in_blueprints`, the pipe-owned `unresolved_concept` item sets `concept_code=concept_ref_or_code` — the **raw** ref. For a same-domain ref that the author happened to qualify (e.g. `output = "mydomain.Foo"` in domain `mydomain`), `ref.is_external_to("mydomain")` is `False`, so it reaches the unresolved branch and `concept_code` becomes the domain-qualified string `"mydomain.Foo"` rather than the bare `Foo`. The categorizer's concept path and the bare-ref test (`concept_code == "NonExistentConcept"`) assume the bare code, so a consumer keying on a bare `concept_code` mismatches when the author qualified the ref.

**Shape when picked up:** decide the canonical form for `concept_code` (bare local code vs. as-written) and normalize at the construction site — likely `ref.local_code` for the bare form — then add a fixture with a qualified same-domain output ref.

## 4. `unresolved_pipe_dependency` carries no `source`

The `unresolved_pipe_dependency` item omits `source`, while the sibling `unresolved_concept` and `unknown_pipe_type` items carry it. Root cause: at library-validation time `library.py` builds the item from the `pipe` object, and `PipeAbstract` has no `source` field — so there is no per-pipe declaring-file path to attach. A consumer mapping `validation_errors[]` to declaring files (the vscode cross-file diagnostics path) can attribute the concept/type failures but not the dependency one.

This is a **model limitation**, not a regression. Fixing it means threading the declaring source onto the pipe model (or looking it up by domain at validation time) — non-trivial.

Related but distinct: [`validate-parse-level-source-attribution.md`](validate-parse-level-source-attribution.md) covers the *parse-level* (malformed-TOML) source-less residual. Both are about `source` on `validation_errors[]`, but that one is in the parse comprehension and this one is in library validation — they would be fixed in different places.

## 5. (cleanup) Per-reference failure sentence is built twice

In `validate_concept_references_in_blueprints`, each unresolved reference builds two near-identical sentences in the same iteration: the `undeclared` aggregate-message entry (`'{ref}' in {context} is not declared in domain '{domain}' (source: '{source}')`) and the per-item `item_message` (`Concept '{ref}' in {context} is not declared in domain '{domain}' and is not native.`). A future wording change must touch both or the aggregate `ConceptLibraryError` message and the structured item silently diverge.

**Shape when picked up:** derive one from the other (or from a single small formatter), so there is a single phrasing of "this reference does not resolve."

## Known trade-off baked in by the concept-owned fix (revisit only if it bites)

The concept-owned-ref fix made `concept_code` mean different things across categories for `error_type == unresolved_concept`:

- pipe-owned (`pipe_validation`): `pipe_code` = owning pipe, `concept_code` = **missing** concept.
- concept-owned (`blueprint_validation`): `concept_code` = **owning** concept (consistent with how every other `blueprint_validation` concept error is categorized); the missing reference is named in the `message`.

A consumer disambiguates via `category`, and both branches carry comments. The clean-but-larger alternative would be distinct "owner" and "missing/referenced" locator fields on the wire item (and on `PipesAndConceptValidationErrorData` / `PipelexBundleBlueprintValidationErrorData`) so `concept_code` need not double as both. Deferred as a wire-model design question, not worth the churn unless a consumer needs the owner concept structurally in the pipe-owned case (or the missing concept structurally in the concept-owned case).

## Cross-repo note

Any change here that alters the `validation_errors[]` wire shape (new locator fields, normalized `concept_code`) must be mirrored in `conformance/conformance/validation_contract.py` + `conformance/conformance/assertions/json_output.py`, per the spec/conformance sync rule, and the conformance suite run on both arms.
