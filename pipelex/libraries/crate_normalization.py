"""Normalization pass: authored library crate -> normalized library crate.

Given a merged, key-qualified crate (as produced by `LibraryCrateFactory.make_from_blueprints` over a
loaded, validated library), this pass applies the [Library Crate Format] normalization so the result
is closed, canonical, and explicit:

1. merge — already done upstream (keys are `domain.Code` / `domain.code`);
2. fully qualify every *in-body* reference — pipe `inputs` / `output` concept refs, pipe-step / branch
   / outcome / batch pipe refs, concept `refines`, and structure-field `concept_ref` / `item_concept_ref`.
   Delegated to `qualify_crate` (see `crate_qualification`), which owns the reference-resolution rule
   so it is stated once rather than mirrored per consumer;
3. flatten refinement — a refining concept adopts its **in-crate structured** base's effective
   structure (the `refines` link is dropped once the structure is materialized). A concept whose
   refinement chain bottoms out at a **native** keeps its `refines` link: the native is materialized
   into `concepts` by step 4, so the base is resolvable in-crate, and keeping the link preserves the
   native content class on crate round-trip (`refines: native.Text` reloads as a `TextContent`
   subclass rather than a bare `StructuredContent` that lost `TextContent`'s specialized rendering);
4. expand natives — every referenced native is materialized into `concepts` as a `native.<Code>` entry
   (see `native_expansion`), transitively, and the crate is stamped with `mthds_version`;
5. materialize string-described concepts — a `Foo = "text"` shorthand becomes a description-only
   `ConceptBlueprint`; string structure fields become explicit `text` fields.

Deferred normalization steps (the spec's [Library Crate Format] "Normalization Pass" lists these; they
are not yet applied here, mirroring the spec's own "Specification Status" callout):

- materialize defaults and multiplicity (spec step 5): multiplicity markers already present on a ref are
  preserved by the qualification pass, but a bare singular ref is not rewritten to an explicit form,
  and default values are not yet materialized;
- cross-package (`alias->…`) references: the referenced dependency content is not folded into this crate
  yet, so those refs are left intact rather than rewritten to a canonical ref that would dangle. A
  single-package multi-bundle closure normalizes to a fully self-contained crate.

[Library Crate Format]: mthds/docs/spec/library-crate.md
"""

from typing import NamedTuple

from pipelex.codegen.native_expansion import collect_native_refs_from_structure, materialize_native_concept
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint
from pipelex.core.concepts.helpers import normalize_structure_blueprint
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.pipes.variable_multiplicity import parse_concept_with_multiplicity
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.libraries.crate_qualification import qualify_crate
from pipelex.libraries.exceptions import CrateNormalizationError
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.mthds_parsing.pipelex_bundle_blueprint import PipeBlueprintUnion

_ConceptEntry = ConceptBlueprint | str


class _RefinementResolution(NamedTuple):
    is_native_backed: bool
    effective_structure: dict[str, ConceptStructureBlueprint] | None


def normalize_crate(crate: LibraryCrate, *, mthds_version: str) -> LibraryCrate:
    """Produce a normalized library crate from a merged, key-qualified crate.

    The input crate must already be assembled and key-qualified (e.g. from
    `LibraryCrateFactory.make_from_blueprints` over a validated library, per D6). The output carries
    the normalized `fingerprint` (D2 scope) and the `mthds_version` stamp; `qualify_crate` returns
    content only, so the envelope is assembled here.

    Qualification runs as one complete phase up front, over concepts *and* pipes, rather than
    interleaved with the steps below. So a crate carrying two independent defects — say a refinement
    cycle *and* an unqualified crate key — reports the key first, where the interleaved version could
    report the cycle. Both are `CrateNormalizationError` and the crate is invalid either way; which
    defect is named first is not a contract.

    The pass qualifies but does not resolve, so a normalized crate is closed over its pipe refs only
    because the library it came from validated first. Feed this an unvalidated crate whose pipe
    references a sibling domain by bare code and you get a crate naming a pipe that does not exist —
    which is the point: that ref was never resolvable by the rule, and validation is where it is
    reported.
    """
    qualified = qualify_crate(crate)

    concepts: dict[str, _ConceptEntry] = {
        concept_ref: _normalize_concept(value, source=crate.source_map.get(concept_ref)) for concept_ref, value in qualified.concepts.items()
    }
    _flatten_refinement(concepts)

    pipes = qualified.pipes

    _expand_natives(concepts=concepts, pipes=pipes)

    fingerprint = LibraryCrate.compute_normalized_fingerprint(concepts=concepts, pipes=pipes, domains=crate.domains)
    return LibraryCrate(
        mthds_version=mthds_version,
        concepts=concepts,
        pipes=pipes,
        domains=crate.domains,
        source_map=crate.source_map,
        fingerprint=fingerprint,
    )


# --------------------------------------------------------------------------------------------------
# Concepts
# --------------------------------------------------------------------------------------------------


def _normalize_concept(value: _ConceptEntry, *, source: str | None) -> _ConceptEntry:
    """Materialize the authoring shorthands. In-body refs are already qualified by `qualify_crate`."""
    # String-described concept -> explicit description-only ConceptBlueprint (structureless).
    if isinstance(value, str):
        return ConceptBlueprint(source=source, description=value)

    if not isinstance(value.structure, dict):
        return value
    # String structure fields -> explicit `text` fields.
    return value.model_copy(update={"structure": normalize_structure_blueprint(value.structure)})


def _flatten_refinement(concepts: dict[str, _ConceptEntry]) -> None:
    """Materialize each refining concept's effective structure in place, dropping the `refines` link
    once a non-empty structure is materialized. Two kinds of base keep their `refines` link untouched:

    - a **native-backed** base (the refinement chain bottoms out at a native): the native is
      materialized into `concepts` by native expansion, so the base is resolvable in-crate; keeping
      the link is what preserves the native content class on round-trip (B1-2) — flattening would drop
      `refines: native.Text` and reload the concept as a bare `StructuredContent`, silently losing
      `TextContent`'s specialized rendering;
    - a structureless or cross-package base (nothing to materialize / not resolvable in-crate).
    """
    resolution_cache: dict[str, _RefinementResolution] = {}
    for concept_ref, value in list(concepts.items()):
        if not isinstance(value, ConceptBlueprint) or not value.refines or isinstance(value.structure, dict):
            continue
        resolution = _resolve_refinement(value.refines, concepts=concepts, cache=resolution_cache)
        if resolution.is_native_backed:
            continue
        if resolution.effective_structure:
            concepts[concept_ref] = value.model_copy(update={"refines": None, "structure": dict(resolution.effective_structure)})


def _resolve_refinement(
    concept_ref: str,
    *,
    concepts: dict[str, _ConceptEntry],
    cache: dict[str, _RefinementResolution],
) -> _RefinementResolution:
    """Resolve native ancestry and effective structure iteratively, caching each visited ref once."""
    if concept_ref in cache:
        return cache[concept_ref]

    path: list[str] = []
    path_index_by_ref: dict[str, int] = {}
    current_ref = concept_ref
    resolution: _RefinementResolution
    while current_ref not in cache:
        if current_ref in path_index_by_ref:
            cycle = path[path_index_by_ref[current_ref] :]
            first_ref = min(cycle)
            first_index = cycle.index(first_ref)
            ordered_cycle = cycle[first_index:] + cycle[:first_index] + [first_ref]
            msg = f"Refinement cycle detected: {' -> '.join(ordered_cycle)}"
            raise CrateNormalizationError(msg)

        path_index_by_ref[current_ref] = len(path)
        path.append(current_ref)

        if NativeConceptCode.is_native_concept_ref_or_code(concept_ref_or_code=current_ref):
            native_ref = NativeConceptCode.get_validated_native_concept_ref(concept_ref_or_code=current_ref)
            resolution = _RefinementResolution(is_native_backed=True, effective_structure=_native_effective_structure(native_ref))
            break

        value = concepts.get(current_ref)
        if not isinstance(value, ConceptBlueprint):
            # Cross-package or unknown base: not resolvable in-crate.
            resolution = _RefinementResolution(is_native_backed=False, effective_structure=None)
            break
        if isinstance(value.structure, dict):
            effective_structure = {field_name: field for field_name, field in value.structure.items() if isinstance(field, ConceptStructureBlueprint)}
            resolution = _RefinementResolution(is_native_backed=False, effective_structure=effective_structure)
            break
        if value.refines:
            current_ref = value.refines
            continue
        resolution = _RefinementResolution(is_native_backed=False, effective_structure=None)
        break
    else:
        resolution = cache[current_ref]

    for visited_ref in reversed(path):
        cache[visited_ref] = resolution
    return resolution


def _native_effective_structure(native_ref: str) -> dict[str, ConceptStructureBlueprint] | None:
    native_code = NativeConceptCode(QualifiedRef.parse(native_ref).local_code)
    materialized = materialize_native_concept(native_code)
    if not isinstance(materialized.structure, dict):
        return None
    return {field_name: field for field_name, field in materialized.structure.items() if isinstance(field, ConceptStructureBlueprint)}


# --------------------------------------------------------------------------------------------------
# Native expansion
# --------------------------------------------------------------------------------------------------


def _expand_natives(*, concepts: dict[str, _ConceptEntry], pipes: dict[str, PipeBlueprintUnion]) -> None:
    referenced = _collect_referenced_natives(concepts=concepts, pipes=pipes)
    materialized: dict[str, ConceptBlueprint] = {}
    worklist = list(referenced)
    while worklist:
        native_ref = worklist.pop()
        if native_ref in materialized:
            continue
        native_code = NativeConceptCode(QualifiedRef.parse(native_ref).local_code)
        blueprint = materialize_native_concept(native_code)
        materialized[native_ref] = blueprint
        if isinstance(blueprint.structure, dict):
            structure = {field_name: field for field_name, field in blueprint.structure.items() if isinstance(field, ConceptStructureBlueprint)}
            worklist.extend(ref for ref in collect_native_refs_from_structure(structure) if ref not in materialized)
    concepts.update(materialized)


def _collect_referenced_natives(*, concepts: dict[str, _ConceptEntry], pipes: dict[str, PipeBlueprintUnion]) -> set[str]:
    referenced: set[str] = set()
    for value in concepts.values():
        if not isinstance(value, ConceptBlueprint):
            continue
        if value.refines:
            _add_native_ref(referenced=referenced, concept_ref_or_code=value.refines)
        if isinstance(value.structure, dict):
            for field in value.structure.values():
                if isinstance(field, ConceptStructureBlueprint):
                    _add_native_ref(referenced=referenced, concept_ref_or_code=field.concept_ref)
                    _add_native_ref(referenced=referenced, concept_ref_or_code=field.item_concept_ref)
    for blueprint in pipes.values():
        for io_ref in [*(blueprint.inputs_concept_specs or {}).values(), blueprint.output]:
            _add_native_ref(referenced=referenced, concept_ref_or_code=_io_ref_concept(io_ref))
    return referenced


def _io_ref_concept(io_ref: str) -> str | None:
    if not io_ref or QualifiedRef.has_cross_package_prefix(io_ref):
        return None
    return parse_concept_with_multiplicity(io_ref).concept_ref_or_code


def _add_native_ref(*, referenced: set[str], concept_ref_or_code: str | None) -> None:
    if concept_ref_or_code and NativeConceptCode.is_native_concept_ref_or_code(concept_ref_or_code=concept_ref_or_code):
        referenced.add(NativeConceptCode.get_validated_native_concept_ref(concept_ref_or_code=concept_ref_or_code))
