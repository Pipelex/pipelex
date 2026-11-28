"""The contract-fact judgments that need the library's concepts: sites typed by a concept, and file-valued outputs.

A blueprint judges the contract facts of a site whose value class it knows: a structure field typed by a field type. A
site typed by a concept, a `concept` field, an input slot, a concept's `unit` on a refinement of another declared concept,
holds the value class of that concept, which only the library's concepts decide (spec: mthds-format.md, "Value Classes" and
"Input slot declarations"). So do the outputs an `output_filename` needs to be file-valued (spec: "Naming Produced Files").
This module judges them over the qualified crate, once the batch's concepts are merged, before any pipe is built.

A site whose concept the crate cannot see, a cross-package reference or a concept an earlier load holds, is left alone: the
runtime's own validation of its values still applies, and nothing is refused on a guess.
"""

from typing import Any

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint
from pipelex.core.exceptions import PipelexBundleBlueprintValidationErrorData, PipesAndConceptValidationErrorData
from pipelex.core.pipes.variable_multiplicity import parse_concept_with_multiplicity
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.language.contract_facts import (
    ContractFactFinding,
    ContractFactKey,
    ContractFactReason,
    FactSiteType,
    ValueClass,
    applicability_findings,
    value_findings,
)
from pipelex.language.intent_hints import HintSiteValueKind
from pipelex.libraries.concept.exceptions import ConceptLibraryError
from pipelex.libraries.concept_value_kinds import CrateConceptKinds
from pipelex.libraries.crate_qualification import QualifiedCrateContent
from pipelex.pipe_machinery.pipe_blueprint import InputSlotBlueprint
from pipelex.validation_error_types import PipeValidationErrorType


def ensure_contract_fact_sites_valid(*, qualified: QualifiedCrateContent, source_map: dict[str, str]) -> None:
    """Refuse every contract fact, `choices` or `output_filename` whose site's concept rules it out.

    Args:
        qualified: The qualified crate content of the batch being loaded.
        source_map: The source file of each crate key, for the items' locators.

    Raises:
        ConceptLibraryError: With one item per fault, concept-owned faults as blueprint items and pipe-owned ones as pipe
            items, as the concept-reference resolution reports them.
    """
    kinds = CrateConceptKinds(concepts=qualified.concepts)
    concept_items: list[PipelexBundleBlueprintValidationErrorData] = []
    pipe_items: list[PipesAndConceptValidationErrorData] = []

    for concept_ref, value in sorted(qualified.concepts.items()):
        if not isinstance(value, ConceptBlueprint):
            continue
        parsed_ref = QualifiedRef.parse(concept_ref)
        domain_code = parsed_ref.domain_path
        concept_code = parsed_ref.local_code
        concept_path = f"concept.{concept_code}"
        source = source_map.get(concept_ref)
        concept_kind = kinds.kind_of(concept_ref=concept_ref)
        if value.unit is not None and value.refines and concept_kind is not None:
            # A unit on a refinement the blueprint could not judge: the chain decides it now.
            if not concept_kind.is_number_valued:
                finding = ContractFactFinding(
                    ContractFactKey.UNIT,
                    ContractFactReason.INAPPLICABLE,
                    "'unit' is allowed only on a concept whose refinement chain reaches native.Number, and this concept is not number-valued",
                )
                concept_items.append(
                    _concept_item(finding=finding, site_path=concept_path, domain_code=domain_code, concept_code=concept_code, source=source)
                )
        if not isinstance(value.structure, dict):
            continue
        for field_name, field in value.structure.items():
            if not isinstance(field, ConceptStructureBlueprint) or not field.is_concept_typed or not field.concept_ref:
                continue
            facts = field.contract_facts
            if not facts:
                continue
            kind = kinds.kind_of(concept_ref=field.concept_ref)
            if kind is None:
                continue
            findings = _site_findings(
                facts=facts, value_class=_class_of(kind=kind), is_slot=False, has_choices=False, default_value=field.default_value
            )
            if findings:
                concept_items.append(
                    _concept_item(
                        finding=findings[0],
                        site_path=f"{concept_path}.structure.{field_name}",
                        domain_code=domain_code,
                        concept_code=concept_code,
                        source=source,
                    )
                )

    for pipe_ref, blueprint in sorted(qualified.pipes.items()):
        parsed_ref = QualifiedRef.parse(pipe_ref)
        domain_code = parsed_ref.domain_path
        pipe_code = parsed_ref.local_code
        source = source_map.get(pipe_ref)
        for slot_name, slot_value in (blueprint.inputs or {}).items():
            if not isinstance(slot_value, InputSlotBlueprint):
                continue
            facts = slot_value.contract_facts
            if not facts and slot_value.choices is None:
                continue
            kind = kinds.kind_of_slot(concept_spec=slot_value.concept)
            if kind is None:
                continue
            findings = _site_findings(facts=facts, value_class=_class_of(kind=kind), is_slot=True, has_choices=slot_value.choices is not None)
            if findings:
                finding = findings[0]
                site_path = f"pipe.{pipe_code}.inputs.{slot_name}"
                pipe_items.append(
                    PipesAndConceptValidationErrorData(
                        error_type=PipeValidationErrorType.CONTRACT_FACT_INVALID,
                        domain_code=domain_code,
                        source=source,
                        pipe_code=pipe_code,
                        field_name=f"inputs.{slot_name}",
                        variable_names=[slot_name],
                        field_path=site_path,
                        message=f"Input '{slot_name}' of pipe '{pipe_code}': {finding.message}",
                        params=_fact_params(finding=finding, site_path=site_path),
                    )
                )
        if blueprint.output_filename is not None:
            output_kind = kinds.kind_of(concept_ref=parse_concept_with_multiplicity(blueprint.output).concept_ref_or_code)
            if output_kind is not None and not output_kind.is_file_valued:
                pipe_items.append(
                    PipesAndConceptValidationErrorData(
                        error_type=None,
                        domain_code=domain_code,
                        source=source,
                        pipe_code=pipe_code,
                        field_name="output_filename",
                        field_path=f"pipe.{pipe_code}.output_filename",
                        message=(
                            f"`output_filename` is allowed only on an operator whose output is file-valued (an Image or a Document), "
                            f"and the output '{blueprint.output}' of pipe '{pipe_code}' is not"
                        ),
                    )
                )

    if concept_items or pipe_items:
        messages = [item.message for item in concept_items] + [item.message for item in pipe_items]
        msg = "Contract facts that do not apply where they are written:\n  - " + "\n  - ".join(messages)
        raise ConceptLibraryError(msg, blueprint_validation_errors=concept_items, pipe_concept_validation_errors=pipe_items)


def _class_of(*, kind: HintSiteValueKind | None) -> ValueClass | None:
    return ValueClass.of_site_kind(site_kind=kind) if kind is not None else None


def _site_findings(
    *,
    facts: dict[str, Any],
    value_class: ValueClass | None,
    is_slot: bool,
    has_choices: bool,
    default_value: Any = None,
) -> list[ContractFactFinding]:
    """The faults of a site typed by a concept: facts its class rules out, then examples and a default breaking its facts."""
    findings = applicability_findings(facts=facts, value_class=value_class, is_slot=is_slot, has_choices=has_choices)
    if findings or value_class is None:
        return findings
    return value_findings(facts=facts, site_type=FactSiteType.of_concept_class(value_class=value_class), default_value=default_value)


def _fact_params(*, finding: ContractFactFinding, site_path: str) -> dict[str, Any]:
    """The parameters of the standard's `method.contract_fact_invalid`, carried whichever code the item takes."""
    return {"fact": finding.fact, "reason": finding.reason, "field_path": site_path}


def _concept_item(
    *,
    finding: ContractFactFinding,
    site_path: str,
    domain_code: str | None,
    concept_code: str,
    source: str | None,
) -> PipelexBundleBlueprintValidationErrorData:
    return PipelexBundleBlueprintValidationErrorData(
        error_type=PipeValidationErrorType.CONTRACT_FACT_INVALID,
        domain_code=domain_code,
        source=source,
        concept_code=concept_code,
        field_path=site_path,
        message=f"At '{site_path}': {finding.message}",
        params=_fact_params(finding=finding, site_path=site_path),
    )
