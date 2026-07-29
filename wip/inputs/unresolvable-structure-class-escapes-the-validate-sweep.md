# An unresolvable structure class would escape the `/validate` sweep

**Status:** deferred — a latent granularity tradeoff, not a live bug. Raised by the Phase-1 code review on `refactor/Concept-purity`, and rejected for Phase 1 after checking reachability.

## The claim

Phase 1 made `ConceptLibrary.is_compatible` **raise** `ConceptStructureClassNotFoundError` when a concept's declared `structure_class_name` does not resolve, where `Concept.are_concept_compatible` used to silently return `False`. That is the branch's stated fix (b): a name that should have resolved and didn't is not an answer to "are these compatible?", and answering `False` makes it indistinguishable from a genuine "incompatible" verdict.

The review observed that `is_compatible` is called from many pre-existing sites that do **not** guard against a raise, and proposed adding `except` guards at each. The named sites: `core/memory/input_shaper.py:236` (`resolve_input_kind`), `core/stuffs/stuff_factory.py` (the dict-building arms), `pipe_operators/compose/pipe_compose.py`, `.../extract/pipe_extract{,_factory}.py`, `.../structure/pipe_structure.py`, `.../img_gen/pipe_img_gen.py`, `.../search/pipe_search_factory.py`.

## Why it is not reachable today

`ConceptFactory` refuses to build a concept whose declared structure class does not resolve:

- `concept_factory.py:305` — a `structure = "SomeClass"` declaration that is not a registered `StuffContent` subclass raises `ConceptFactoryError` at concept-construction time.
- The basic-blueprint path (`concept_factory.py:371-385`) either finds an existing registered class or **generates** one.

Every `Concept(...)` construction in `pipelex/` source lives inside `concept_factory.py`. So a concept sitting in a loaded library always has a resolvable structure class, and the raise cannot fire on the loader path. The two direct `Concept.model_validate` sites (`pipe_run/delivery_executor.py:212`, `runtime_bridge/primitives/hydration.py:155`) rehydrate a stuff's concept in a process that has the bundle loaded.

Applying the proposed guards would convert the loud failure back into the silent degradation this branch exists to remove — at eight call sites, for a state the factory already refuses to produce. That is the "don't guard impossible scenarios" line.

## Why it is still worth writing down

If the state ever *does* become reachable — a concept deserialized into a process where the bundle's generated classes were never registered is the plausible route — the failure mode is coarser than it should be:

`pipeline/bundle_validator.py:214-225` sweeps pipes with `pipe.validate_with_libraries()` inside a `try` that catches **only** `PipeNotFoundError`. A `ConceptStructureClassNotFoundError` is a `ConceptValueError` is a `ValueError`, so it would escape the sweep and abort the whole bundle rather than reporting the one offending pipe as failed.

This is not a hypothesis about the codebase's opinion — `pipe_controllers/parallel/pipe_parallel.py:159-176` already wraps its `get_structure_class()` call for exactly this reason, and says so: *"A plain ValueError would escape the /validate sweep and abort the whole bundle; convert it so this pipe alone is reported as failed."*

The right shape, if it ever needs doing, is **not** eight scattered `except` blocks. It is one decision at the sweep boundary: `bundle_validator` catching `ConceptValueError` alongside `PipeNotFoundError` and recording the pipe as failed — one place, matching the granularity contract the sweep already implements for unresolved dependencies.

## Related, for Phase 2

`input_shaper.py:239-241` carries a comment listing "any concept whose class is unregistered" among the cases that fall back to bottom-up building, guarded by an `except ConceptValueError` around `concept.get_structure_class()`. Given the factory guard above, that arm looks unreachable and the comment overstates it. Phase 2 migrates this exact call site to the provider — re-read the comment against reality then rather than editing it in isolation now.
