# Deferred: what should a cross-package refinement generate at runtime?

**Raised during** the review-bot triage of PR #1151 (release/v0.52.0), while verifying a Codex finding on `input_form`. Not itself bot-reported — it surfaced from the code the finding pointed at.

## The open question

When a concept refines a cross-package base (`alias->domain.Code`), the base class is not available locally. `ConceptFactory._handle_refines` (`pipelex/core/concepts/concept_factory.py`, the `QualifiedRef.has_cross_package_prefix(current_refine)` branch) handles this by generating a standalone structure class with an empty structure blueprint and **no** `base_class_name`. `StructureGenerator` defaults that to `StructuredContent`, so the result is a **field-less `StructuredContent` subclass**. The refinement itself survives only as the `refine_string` on the concept model, for runtime compatibility checks.

The comment above that branch used to say it generated a `TextContent` subclass — which the code has never done. That comment has been corrected to describe the actual behaviour, but correcting it does not settle the question it was hiding: **is a field-less `StructuredContent` the right thing to generate here at all?**

Three candidate answers, none obviously correct:

1. **Keep `StructuredContent`** — honest about knowing nothing, and structurally compatible with whatever the base turns out to be. But a field-less structured object is not usable shape information for anything downstream.
2. **`TextContent`, as the stale comment claimed** — makes the concept usable as prose, but invents a shape the base may not have. If the dependency's concept is structured, this is a lie with consequences at execution time, not just in a descriptor.
3. **Resolve the base from the dependency's child library** — the only answer that is actually informed. Costly: dependency concepts load into an isolated `child_library` and are deliberately not in the consuming crate, so this would mean crossing a boundary the loader draws on purpose.

## Why it is deferred rather than fixed

The descriptor half of this is already fixed and does not depend on the answer. `build_input_form` now reports such a concept as `unknown` (with its real `refines` chain preserved) instead of promoting it to `prose` with a fabricated `native.Text` link — see `_blueprint_node_for_chain` in `pipelex/pipeline/input_form.py` and the pinning test `test_chain_ending_at_a_base_absent_from_the_crate_is_unknown` in `tests/unit/pipelex/pipeline/test_input_form_deriver.py`. That is correct **under all three answers above**: `input_form` cannot know the base's shape in any of them, so `unknown` is the honest report either way.

What remains is a runtime design decision about what the engine should back these concepts with, and that is not a call a PR-review pass should make unilaterally — particularly not on a release branch.

## Where to look

- `pipelex/core/concepts/concept_factory.py` — `_handle_refines`, the cross-package branch.
- `pipelex/libraries/concept/concept_library.py` — `validation_static`, which hard-rejects every dangling `refines` *except* a cross-package one. That carve-out is what makes this path reachable at all.
- `pipelex/libraries/library_manager.py` — `_load_single_dependency`, which builds the isolated child library. This is why the base never appears in the consuming crate, loaded or not.
- `tests/data/packages/refining_consumer/refining.mthds` — a fixture already shipping this shape (`PkgTestRefinedScore` refines a dependency's concept).

## Related

- [[deferred-descriptor-reflection-and-roundtrip]] — the other descriptor-side follow-up from this workstream.
- PR thread: <https://github.com/Pipelex/pipelex/pull/1151#discussion_r> (Codex, `pipelex/pipeline/input_form.py`) — the descriptor fix that thread asked for has landed; this note is the runtime question left behind it.
