# Concept purity — working docs

Working notes for the `refactor/Concept-purity` track: getting the process-global class-registry reads out of `Concept`, the MTHDS-protocol wire model. **Track complete** — [PR #1072](https://github.com/Pipelex/pipelex/pull/1072) is open against `dev` with CI green and both review bots clean. The repo-root `TODOS.md` tracker was archived here once the PR was finalized.

| doc | what it is |
| --- | --- |
| [`concept-purity-explained.html`](concept-purity-explained.html) | **Start here.** The architecture note for co-developers: TL;DR, before/after diagrams, the five critical diffs, the three bugs closed, and every judgement call with its reasoning. |
| [`concept-purity-tracker.md`](concept-purity-tracker.md) | The as-built tracker, written as the PR reviewer's guide. Phase-by-phase state, the surprises log, and the deliberate non-goals. |

## What shipped, in one paragraph

`Concept` reads no registry at all. Compatibility split into a pure declaration tier on the model, a pure class tier in `tools/typing/class_utils.py`, and a composition in `ConceptLibrary.is_compatible` — the one place that owns resolution and therefore the only place that can tell "no class" from "not compatible". `ConceptProviderAbstract.get_structure_class` is the single seam turning a `structure_class_name` string into a type. Three live bugs closed on the way: cross-package `refines` aliases silently failing to resolve at five operator call sites, an unresolvable structure class answering `False` instead of raising, and `native.Anything` being answered for the wrong reason. No wire-format change.

## What is deliberately left

- **The scoping half.** Class resolution still goes through the async context's registry rather than one the provider carries. Unreachable divergence today; the mechanism, the four trip-wires, and the shape of the fix are in [`../inputs/provider-scoped-class-resolution.md`](../inputs/provider-scoped-class-resolution.md).
- **The materialization write side stays ambient.** `concept_factory` and `structure_generation/generator.py` register generated classes at library-load time — genuinely the registry's business. Pinned as a golden set by `tests/unit/pipelex/core/concepts/test_concept_registry_boundary.py`.
- **Two run-path `except` arms deliberately not added**, and one dead one removed. Reasoning in [`../inputs/unresolvable-structure-class-escapes-the-validate-sweep.md`](../inputs/unresolvable-structure-class-escapes-the-validate-sweep.md).
