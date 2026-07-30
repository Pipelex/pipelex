# Heads-up for the TS port: concept compatibility was restructured

**For:** whoever picks up the `pipelex-js` port next.
**Why you're getting this:** `pipelex-js/wip/gauntlet/invariants-structural.md` records invariant **CONCEPT-6** against `pipelex/core/concepts/concept.py`'s compatibility block. That block was restructured by [pipelex#1072](https://github.com/Pipelex/pipelex/pull/1072) (`refactor/Concept-purity`). Nothing in `pipelex-js` breaks — no TS code references the changed names — but the invariant now cites a shape that no longer exists, and re-deriving it from the new code is a better starting point than porting the old one.

## What to change in the invariant register

**CONCEPT-6 was one function; it is now three things in three places.** The old `Concept.are_concept_compatible(concept_1, concept_2, strict, concept_resolver)` did string comparisons, then fell through to class comparisons, and returned `False` when either class was missing. That single method is gone. In its place:

| tier | where | purity |
|---|---|---|
| declaration | `Concept.are_compatible_by_declaration(concept_1, concept_2, concept_resolver)` | pure over the model's own fields + the injected resolver |
| class | `are_structure_classes_compatible(class_1, class_2, strict)` in `tools/typing/class_utils.py` | pure over two already-resolved types |
| composition | `ConceptLibrary.is_compatible(tested_concept, wanted_concept, strict)` | owns resolution; the only thing that reads a registry |

`strict` no longer exists at the declaration tier — it never meant anything there. It only ever governed how much slack the *class* comparison allowed.

## Three semantics worth porting deliberately

**1 · The declaration tier's `False` is not a verdict.** It means "not established at this tier", not "incompatible". Two concepts whose declarations say nothing about each other can still be compatible through their classes. If the port collapses the tiers back into one function, this distinction is what gets lost — and losing it is the bug the refactor fixed. Worth encoding in the type: consider `Established | NotEstablished` over a bare `boolean` for the tier-1 result, even if the composed public API stays `boolean`.

**2 · An unresolvable structure class must fail, not answer.** The old code returned `False` when a class name did not resolve, which is indistinguishable from a genuine "incompatible". It now raises `ConceptStructureClassNotFoundError` (a `ConceptValueError` subclass). Port the raise, not the `False` — this is CONCEPT-6's most consequential change.

**3 · `native.Anything` has no structure class at all, by design.** `NativeConceptCode.ANYTHING.structure_class` is `None` — it is the untyped vehicle — while `structure_class_name` still derives `"AnythingContent"` mechanically, a name no registry ever holds. So the composition checks a *declared property* (`Concept.declares_a_structure_class` / `NativeConceptCode.is_structureless_concept`) and returns `False` **before** attempting class resolution. Skip this and porting semantic 2 turns every `Anything` comparison into a crash. The Python side has a regression test named exactly for it: `test_the_structureless_native_concept_is_answered_not_raised`.

## The ordering is load-bearing

```
is_compatible(tested, wanted, strict):
    if are_compatible_by_declaration(tested, wanted, resolver):   # no class ever looked up
        return True
    if not (tested.declares_a_structure_class
            and wanted.declares_a_structure_class):               # Anything
        return False
    return are_structure_classes_compatible(
        resolve(tested), resolve(wanted), strict)                  # may raise
```

Declaration tier **first** is not an optimisation. It is why a concept whose structure class was never materialised still gets an answer — the tier that could fail is never reached when the declarations already settle the question. Reversing the order, or resolving both classes up front "to simplify", changes observable behaviour.

## Two Python-specific things not to port

- **`ConceptProviderAbstract.get_structure_class`** exists because Python resolves a class *name* against a process-global registry. If the TS port holds real type references (or a module-scoped map) rather than stringly-typed class names, this seam may be unnecessary — the *provider* concept is worth keeping, the *name → type registry lookup* may not be.
- **The `class_registry_access` below-both-hubs placement** is a workaround for a pyright import-cycle constraint. It carries no design intent worth reproducing.

## Where the detail lives

`wip/concept-purity/concept-purity-explained.html` in the `pipelex` repo — the diagrams, the minimal diffs, and the reasoning behind each judgement call. `wip/concept-purity/concept-purity-tracker.md` is the as-built tracker with the decision log.

One open item that may matter to the port's design: class resolution is still *ambient* (scoped by an async-context variable, not carried by the provider). Unreachable divergence today, and the trip-wires are written up in `wip/inputs/provider-scoped-class-resolution.md`. If the TS port carries a registry on the provider from the start, it simply does not inherit this question — which is the better outcome.
