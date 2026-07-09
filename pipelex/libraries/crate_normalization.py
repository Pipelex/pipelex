"""Normalization pass: authored library crate -> normalized library crate.

Given a merged, key-qualified crate (as produced by `LibraryCrateFactory.make_from_blueprints` over a
loaded, validated library), this pass applies the [Library Crate Format] normalization so the result
is closed, canonical, and explicit:

1. merge — already done upstream (keys are `domain.Code` / `domain.code`);
2. fully qualify every *in-body* reference — pipe `inputs` / `output` concept refs, pipe-step / branch
   / outcome / batch pipe refs, concept `refines`, and structure-field `concept_ref` / `item_concept_ref`;
3. flatten refinement — a refining concept adopts its base's effective structure (natives and
   same-package bases resolved; the `refines` link is dropped once the structure is materialized);
4. expand natives — every referenced native is materialized into `concepts` as a `native.<Code>` entry
   (see `native_expansion`), transitively, and the crate is stamped with `mthds_version`;
5. materialize string-described concepts — a `Foo = "text"` shorthand becomes a description-only
   `ConceptBlueprint`; string structure fields become explicit `text` fields.

Deferred normalization steps (the spec's [Library Crate Format] "Normalization Pass" lists these; they
are not yet applied here, mirroring the spec's own "Specification Status" callout):

- materialize defaults and multiplicity (spec step 5): multiplicity markers already present on a ref are
  preserved (`_render_ref_with_markers`), but a bare singular ref is not rewritten to an explicit form,
  and default values are not yet materialized;
- cross-package (`alias->…`) references: the referenced dependency content is not folded into this crate
  yet, so those refs are left intact rather than rewritten to a canonical ref that would dangle. A
  single-package multi-bundle closure normalizes to a fully self-contained crate.

[Library Crate Format]: mthds/docs/spec/library-crate.md
"""

from pipelex.codegen.native_expansion import collect_native_refs_from_structure, materialize_native_concept
from pipelex.core.bundles.pipelex_bundle_blueprint import PipeBlueprintUnion
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint
from pipelex.core.concepts.helpers import normalize_structure_blueprint
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.pipes.variable_multiplicity import MultiplicityParseResult, parse_concept_with_multiplicity
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.libraries.exceptions import CrateNormalizationError
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_controllers.condition.special_outcome import SpecialOutcome
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint

_ConceptEntry = ConceptBlueprint | str


def normalize_crate(crate: LibraryCrate, *, mthds_version: str) -> LibraryCrate:
    """Produce a normalized library crate from a merged, key-qualified crate.

    The input crate must already be assembled and key-qualified (e.g. from
    `LibraryCrateFactory.make_from_blueprints` over a validated library, per D6). The output carries
    the normalized `fingerprint` (D2 scope) and the `mthds_version` stamp.
    """
    concepts: dict[str, _ConceptEntry] = {
        concept_ref: _normalize_concept(value, owner_domain=_domain_of(concept_ref), source=crate.source_map.get(concept_ref))
        for concept_ref, value in crate.concepts.items()
    }
    _flatten_refinement(concepts)

    pipes: dict[str, PipeBlueprintUnion] = {
        pipe_ref: _normalize_pipe(blueprint, owner_domain=_domain_of(pipe_ref)) for pipe_ref, blueprint in crate.pipes.items()
    }

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


def _domain_of(qualified_ref: str) -> str:
    domain_path = QualifiedRef.parse(qualified_ref).domain_path
    if domain_path is None:
        msg = f"Crate key '{qualified_ref}' is not domain-qualified; the normalizer expects a merged, key-qualified crate."
        raise CrateNormalizationError(msg)
    return domain_path


# --------------------------------------------------------------------------------------------------
# Concepts
# --------------------------------------------------------------------------------------------------


def _normalize_concept(value: _ConceptEntry, *, owner_domain: str, source: str | None) -> _ConceptEntry:
    # String-described concept -> explicit description-only ConceptBlueprint (structureless).
    if isinstance(value, str):
        return ConceptBlueprint(source=source, description=value)

    updates: dict[str, object] = {}
    if value.refines:
        updates["refines"] = ConceptFactory.make_refine(value.refines, domain_code=owner_domain)
    if isinstance(value.structure, dict):
        normalized_structure = normalize_structure_blueprint(value.structure)
        updates["structure"] = {
            field_name: _qualify_structure_field(field_blueprint, domain=owner_domain) for field_name, field_blueprint in normalized_structure.items()
        }
    return value.model_copy(update=updates) if updates else value


def _qualify_structure_field(field_blueprint: ConceptStructureBlueprint, *, domain: str) -> ConceptStructureBlueprint:
    field_updates: dict[str, object] = {}
    if field_blueprint.concept_ref:
        field_updates["concept_ref"] = _qualify_concept_ref(field_blueprint.concept_ref, domain=domain)
    if field_blueprint.item_concept_ref:
        field_updates["item_concept_ref"] = _qualify_concept_ref(field_blueprint.item_concept_ref, domain=domain)
    return field_blueprint.model_copy(update=field_updates) if field_updates else field_blueprint


def _qualify_concept_ref(concept_ref_or_code: str, *, domain: str) -> str:
    # make_concept_ref_with_domain_from_concept_ref_or_code resolves natives to `native.<Code>`,
    # bare refs to `domain.<Code>`, and preserves cross-package `alias->domain.Code` as-is (deferred).
    return ConceptFactory.make_concept_ref_with_domain_from_concept_ref_or_code(domain_code=domain, concept_ref_or_code=concept_ref_or_code)


def _flatten_refinement(concepts: dict[str, _ConceptEntry]) -> None:
    """Materialize each refining concept's effective structure in place, dropping the `refines` link
    once a non-empty structure is materialized. A concept whose refinement base is structureless or
    cross-package keeps its `refines` link (its base is materialized natively or resolved in-crate).
    """
    effective_cache: dict[str, dict[str, ConceptStructureBlueprint] | None] = {}
    for concept_ref, value in list(concepts.items()):
        if not isinstance(value, ConceptBlueprint) or not value.refines or isinstance(value.structure, dict):
            continue
        effective = _effective_structure(value.refines, concepts=concepts, cache=effective_cache, in_progress=set())
        if effective:
            concepts[concept_ref] = value.model_copy(update={"refines": None, "structure": dict(effective)})


def _effective_structure(
    concept_ref: str,
    *,
    concepts: dict[str, _ConceptEntry],
    cache: dict[str, dict[str, ConceptStructureBlueprint] | None],
    in_progress: set[str],
) -> dict[str, ConceptStructureBlueprint] | None:
    """The complete field set of `concept_ref`, walking refinement bases. None = structureless."""
    if concept_ref in cache:
        return cache[concept_ref]
    if concept_ref in in_progress:
        # A refinement cycle would have been rejected upstream; guard defensively rather than recurse.
        return None

    if NativeConceptCode.is_native_concept_ref_or_code(concept_ref_or_code=concept_ref):
        native_ref = NativeConceptCode.get_validated_native_concept_ref(concept_ref_or_code=concept_ref)
        result = _native_effective_structure(native_ref)
        cache[concept_ref] = result
        return result

    value = concepts.get(concept_ref)
    if not isinstance(value, ConceptBlueprint):
        # Cross-package or unknown base: not resolvable in-crate.
        cache[concept_ref] = None
        return None

    in_progress.add(concept_ref)
    if isinstance(value.structure, dict):
        result = {field_name: field for field_name, field in value.structure.items() if isinstance(field, ConceptStructureBlueprint)}
    elif value.refines:
        result = _effective_structure(value.refines, concepts=concepts, cache=cache, in_progress=in_progress)
    else:
        result = None
    in_progress.discard(concept_ref)
    cache[concept_ref] = result
    return result


def _native_effective_structure(native_ref: str) -> dict[str, ConceptStructureBlueprint] | None:
    native_code = NativeConceptCode(QualifiedRef.parse(native_ref).local_code)
    materialized = materialize_native_concept(native_code)
    if not isinstance(materialized.structure, dict):
        return None
    return {field_name: field for field_name, field in materialized.structure.items() if isinstance(field, ConceptStructureBlueprint)}


# --------------------------------------------------------------------------------------------------
# Pipes
# --------------------------------------------------------------------------------------------------


def _normalize_pipe(blueprint: PipeBlueprintUnion, *, owner_domain: str) -> PipeBlueprintUnion:
    updates: dict[str, object] = {}
    if blueprint.inputs:
        updates["inputs"] = {name: _qualify_io_ref(ref, domain=owner_domain) for name, ref in blueprint.inputs.items()}
    if blueprint.output:
        updates["output"] = _qualify_io_ref(blueprint.output, domain=owner_domain)

    match blueprint:
        case PipeSequenceBlueprint():
            updates["steps"] = [step.model_copy(update={"pipe": _qualify_pipe_ref(step.pipe, domain=owner_domain)}) for step in blueprint.steps]
        case PipeParallelBlueprint():
            updates["branches"] = [
                branch.model_copy(update={"pipe": _qualify_pipe_ref(branch.pipe, domain=owner_domain)}) for branch in blueprint.branches
            ]
        case PipeConditionBlueprint():
            if blueprint.outcomes:
                updates["outcomes"] = {key: _qualify_pipe_ref(pipe_ref, domain=owner_domain) for key, pipe_ref in blueprint.outcomes.items()}
            if blueprint.default_outcome:
                updates["default_outcome"] = _qualify_pipe_ref(blueprint.default_outcome, domain=owner_domain)
        case PipeBatchBlueprint():
            if blueprint.branch_pipe_code:
                updates["branch_pipe_code"] = _qualify_pipe_ref(blueprint.branch_pipe_code, domain=owner_domain)
        case _:
            pass

    return blueprint.model_copy(update=updates)


def _qualify_io_ref(io_ref: str, *, domain: str) -> str:
    if QualifiedRef.has_cross_package_prefix(io_ref):
        return io_ref  # cross-package deferred
    parsed = parse_concept_with_multiplicity(io_ref)
    qualified = _qualify_concept_ref(parsed.concept_ref_or_code, domain=domain)
    return _render_ref_with_markers(qualified, parsed=parsed)


def _render_ref_with_markers(concept_ref: str, *, parsed: MultiplicityParseResult) -> str:
    if parsed.multiplicity is True:
        suffix = "[]"
    elif isinstance(parsed.multiplicity, int):
        suffix = f"[{parsed.multiplicity}]"
    else:
        suffix = ""
    return f"{concept_ref}{suffix}{parsed.presence.symbol}"


def _qualify_pipe_ref(pipe_ref: str, *, domain: str) -> str:
    if QualifiedRef.has_cross_package_prefix(pipe_ref):
        return pipe_ref  # cross-package deferred
    if pipe_ref in SpecialOutcome.value_list():
        return pipe_ref
    if "." in pipe_ref:
        return pipe_ref
    return f"{domain}.{pipe_ref}"


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
            _add_native_ref(referenced, concept_ref_or_code=value.refines)
        if isinstance(value.structure, dict):
            for field in value.structure.values():
                if isinstance(field, ConceptStructureBlueprint):
                    _add_native_ref(referenced, concept_ref_or_code=field.concept_ref)
                    _add_native_ref(referenced, concept_ref_or_code=field.item_concept_ref)
    for blueprint in pipes.values():
        for io_ref in [*(blueprint.inputs or {}).values(), blueprint.output]:
            _add_native_ref(referenced, concept_ref_or_code=_io_ref_concept(io_ref))
    return referenced


def _io_ref_concept(io_ref: str) -> str | None:
    if not io_ref or QualifiedRef.has_cross_package_prefix(io_ref):
        return None
    return parse_concept_with_multiplicity(io_ref).concept_ref_or_code


def _add_native_ref(referenced: set[str], *, concept_ref_or_code: str | None) -> None:
    if concept_ref_or_code and NativeConceptCode.is_native_concept_ref_or_code(concept_ref_or_code=concept_ref_or_code):
        referenced.add(NativeConceptCode.get_validated_native_concept_ref(concept_ref_or_code=concept_ref_or_code))
