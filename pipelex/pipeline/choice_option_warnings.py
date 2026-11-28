"""The advisory warnings of dubious string options: an empty or a repeated plain option in a `choices` list.

A plain-string option list keeps the shorthand it always had, so an empty string or a value written twice is not refused:
the standard reports it as the warning `method.choice_option_dubious`, with the site's `field_path` and the `reason`
(`empty_value` or `duplicate_value`), and the method stays valid (spec: mthds-format.md, "Choice Options"). The option
table form is stricter, and its faults are refusals the blueprints raise.
"""

from pipelex.base_exceptions import ValidationErrorCategory, ValidationErrorItem
from pipelex.core.concepts.choice_options import ChoiceOptionValue, DubiousOptionReason, dubious_string_options
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.libraries.crate_qualification import QualifiedCrateContent
from pipelex.pipe_machinery.pipe_blueprint import InputSlotBlueprint
from pipelex.validation_error_types import PipeValidationErrorType


def build_choice_option_warnings(*, qualified: QualifiedCrateContent) -> list[ValidationErrorItem]:
    """One advisory item per dubious option list: structure fields by concept, then input slots by pipe, in authored order."""
    items: list[ValidationErrorItem] = []
    for concept_ref, value in sorted(qualified.concepts.items()):
        if not isinstance(value, ConceptBlueprint) or not isinstance(value.structure, dict):
            continue
        parsed_ref = QualifiedRef.parse(concept_ref)
        for field_name, field in value.structure.items():
            if isinstance(field, ConceptStructureBlueprint) and field.choices:
                items.extend(
                    _option_items(
                        options=field.choices,
                        field_path=f"concept.{parsed_ref.local_code}.structure.{field_name}",
                        domain_code=parsed_ref.domain_path,
                        concept_code=parsed_ref.local_code,
                        pipe_code=None,
                        field_name=field_name,
                    )
                )
    for pipe_ref, blueprint in sorted(qualified.pipes.items()):
        parsed_ref = QualifiedRef.parse(pipe_ref)
        for slot_name, slot_value in (blueprint.inputs or {}).items():
            if isinstance(slot_value, InputSlotBlueprint) and slot_value.choices:
                items.extend(
                    _option_items(
                        options=slot_value.choices,
                        field_path=f"pipe.{parsed_ref.local_code}.inputs.{slot_name}",
                        domain_code=parsed_ref.domain_path,
                        concept_code=None,
                        pipe_code=parsed_ref.local_code,
                        field_name=f"inputs.{slot_name}",
                    )
                )
    return items


def _option_items(
    *,
    options: list[ChoiceOptionValue],
    field_path: str,
    domain_code: str | None,
    concept_code: str | None,
    pipe_code: str | None,
    field_name: str,
) -> list[ValidationErrorItem]:
    return [
        ValidationErrorItem(
            category=ValidationErrorCategory.BLUEPRINT_VALIDATION,
            error_type=PipeValidationErrorType.CHOICE_OPTION_DUBIOUS,
            message=f"At '{field_path}': {_reason_sentence(reason=reason)}",
            domain_code=domain_code,
            concept_code=concept_code,
            pipe_code=pipe_code,
            field_name=field_name,
            field_path=field_path,
            params={"field_path": field_path, "reason": reason},
        )
        for reason in dubious_string_options(options=options)
    ]


def _reason_sentence(*, reason: DubiousOptionReason) -> str:
    match reason:
        case DubiousOptionReason.EMPTY_VALUE:
            return "a choice option is the empty string, which a person cannot pick by reading it"
        case DubiousOptionReason.DUPLICATE_VALUE:
            return "two choice options share a value, so one of them can never be told apart"
