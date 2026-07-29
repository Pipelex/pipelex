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

## Resolved in Phase 2: the `input_shaper` fallback arm

`input_shaper.resolve_input_kind` carried an `except ConceptValueError: return InputKind.DYNAMIC` around `concept.get_structure_class()`, and a comment listing "any concept whose class is unregistered" among the cases that fall back to bottom-up building. Given the factory guard above, that arm was unreachable and the comment overstated it. Phase 2 migrated the call site to `concept_provider.get_structure_class(...)` and **dropped the guard**: keeping it would have converted the loud raise straight back into the silent fallback fix (b) exists to remove, for a state the factory refuses to produce. The comment now names only the cases that actually reach it.

## Also declined in Phase 2: guarding the two run-path lookups

The branch's own inventory flagged `pipe_parallel.py` (the combine step) and `pipe_search.py` (the structured-output step) as pre-existing bugs — they call `get_structure_class()` unguarded on run paths where their *validation* siblings convert to `PipeValidationError`. Phase 2 migrated all three onto the library but **did not add a third guard**, for two reasons:

- Same reachability argument as above. A concept sitting in a loaded library always has a resolvable structure class, and both sites run mid-execution with that library loaded.
- The complaint has partly aged out. It was written against `ConceptValueError("Concept class 'X' not found")`, which named neither the concept nor the pipe. Phase 1 replaced that with `ConceptStructureClassNotFoundError`, whose message carries the concept ref *and* the declared class name — so a raw escape is already self-describing. What a `PipeRunError` wrapper would add is `pipe_code` and `run_mode`.

The asymmetry with the guarded validation siblings is deliberate and already explained in place: the `/validate` sweep needs per-pipe granularity or one bad pipe aborts the whole bundle, and a run has no sweep. If the conversion is ever wanted, it is a few lines at each site — but it should be motivated by a reachable failure, not by symmetry.

## Discovered in Phase 2: `--save-csv` runs outside the library window

Migrating `_run_core.py`'s `--save-csv` step to `get_concept_library()` broke `tests/e2e/pipelex/cli/test_csv_run.py` with `RuntimeError: No current library set` — `PipelexMTHDSProtocol.execute` tears the run library down on its way out (`runner.py:298-310`), so **everything** after it in `_execute_run` (the CSV save, the pretty print, the working-memory dump) runs with no current library.

The old code did not notice because `concept.get_structure_class()` read the process-global class registry, which is never unregistered at teardown — the exact wart `pipe_io_contracts.py`'s module docstring documents for its own rendering. Phase 2 resolves through `ConceptLibrary.make_empty()` instead, which reads the same process-global registry but keeps the single typed "name → `StuffContent` subclass, or `ConceptStructureClassNotFoundError`" implementation.

That is correct for the CLI (direct execution puts generated classes in the process-global registry) but it is a lifecycle smell, not a design: a post-run step that needs the method's *declarations* is running after the method is gone. The real fix is to give `_execute_run` a result object that carries what the post-run steps need, or to hold the library window open across them — both larger than this branch. Tracked in the workspace-root `wip/library-lifecycle-hygiene.md` alongside the registry-teardown question.
