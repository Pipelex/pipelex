# Suspects — package `libraries`

Reviewed: 28 Section A + 19 primitive lone-subjects. Suspects: 4.

## High confidence

- `pipelex/libraries/libraries/library_crate.py:39` — `LibraryCrate.compute_fingerprint_from_content` — `def compute_fingerprint_from_content(concepts: dict[str, 'ConceptBlueprint | str'], *, pipes: dict[str, PipeBlueprintUnion]) -> str` — `concepts` and `pipes` are co-equal operands (both dict inputs to a hash); neither is the semantic object of the function. Call sites already keyword both (`compute_fingerprint_from_content(concepts=concepts, pipes=pipes)`). A directional-pair with no natural subject. — suggested fix: make fully keyword-only `def compute_fingerprint_from_content(*, concepts, pipes)`

## Medium / low confidence

- `pipelex/libraries/concept/concept_library.py:191` — `ConceptLibrary.add_dependency_concept` — `def add_dependency_concept(self, alias: str, *, concept: Concept) -> None` — `alias` is a namespace/prefix used to build a composite key; `concept` is what is actually being added to the library. Call sites already use `alias=alias` (keyword). The real "subject" of "add" is the concept, not the alias. — suggested fix: `def add_dependency_concept(self, *, alias: str, concept: Concept)` or reorder to `def add_dependency_concept(self, concept: Concept, *, alias: str)`

- `pipelex/libraries/pipe/pipe_library.py:97` — `PipeLibrary.add_dependency_pipe` — `def add_dependency_pipe(self, alias: str, *, pipe: PipeAbstract) -> None` — identical pattern to `add_dependency_concept` above: `alias` is the namespacing key, `pipe` is the actual subject being added. Call sites already use `alias=alias`. — suggested fix: same as above, make `alias` keyword-only too

- `pipelex/libraries/visibility_utils.py:35` — `make_visibility_checker` — `def make_visibility_checker(manifest: MethodsManifest | None, *, blueprints: list[PipelexBundleBlueprint]) -> PackageVisibilityChecker` — `manifest` is nullable config/filter (often `None`), while `blueprints` is the primary data being inspected. Call sites always pass `manifest=manifest` already. Same pattern for `check_visibility_for_blueprints` at line 53. Low confidence: `manifest` could be argued as the filter subject. — suggested fix: make both args keyword-only for both functions
