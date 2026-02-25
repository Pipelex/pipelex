from __future__ import annotations

from typing import TYPE_CHECKING

from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.concepts.validation import is_concept_ref_or_code_valid
from pipelex.core.qualified_ref import QualifiedRef

if TYPE_CHECKING:
    from pipelex.core.concepts.concept_blueprint import ConceptBlueprint


def get_structure_class_name_from_blueprint(
    blueprint_or_string_description: ConceptBlueprint | str,
    concept_ref_or_code: str,
) -> str:
    """Get the structure class name from a blueprint.

    The logic is:
    - If blueprint is a string (description only), class name is the concept_code
    - If blueprint.structure is a string, class name is that string (structure class reference)
    - If blueprint.structure is a dict or None, class name is the concept_code

    Args:
        blueprint_or_string_description: The concept blueprint or string description
        concept_ref_or_code: The concept reference (domain.ConceptCode) or concept code (ConceptCode)

    Returns:
        The structure class name to use

    Raises:
        ValueError: If concept_ref_or_code is not a valid concept reference or code
    """
    if not is_concept_ref_or_code_valid(concept_ref_or_code):
        msg = f"Invalid concept_ref_or_code: '{concept_ref_or_code}'"
        raise ValueError(msg)

    # Extract concept_code from concept_ref_or_code
    ref = QualifiedRef.parse(concept_ref_or_code)
    concept_code = ref.local_code

    if isinstance(blueprint_or_string_description, str):
        return concept_code

    if isinstance(blueprint_or_string_description.structure, str):
        return blueprint_or_string_description.structure

    return concept_code


def strip_multiplicity_from_concept_ref_or_code(concept_ref_or_code: str) -> str:
    """Strip multiplicity from a concept string or code.

    Args:
        concept_ref_or_code: The concept string or code to strip multiplicity from

    Returns:
        The concept string or code without multiplicity
    """
    if "[" in concept_ref_or_code:
        return concept_ref_or_code.split("[", maxsplit=1)[0]
    return concept_ref_or_code


def normalize_structure_blueprint(structure_dict: dict[str, str | ConceptStructureBlueprint]) -> dict[str, ConceptStructureBlueprint]:
    """Convert a mixed structure dictionary to a proper ConceptStructureBlueprint dictionary.

    Args:
        structure_dict: Dictionary that may contain strings or ConceptStructureBlueprint objects

    Returns:
        Dictionary with all values as ConceptStructureBlueprint objects
    """
    normalized: dict[str, ConceptStructureBlueprint] = {}

    for field_name, field_value in structure_dict.items():
        if isinstance(field_value, str):
            # Simple string descriptions default to required=True (shorthand syntax implies required)
            normalized[field_name] = ConceptStructureBlueprint(
                description=field_value,
                type=ConceptStructureBlueprintFieldType.TEXT,
                required=True,
            )
        else:
            normalized[field_name] = field_value

    return normalized


def extract_concept_code_from_concept_ref_or_code(concept_ref_or_code: str) -> str:
    """Extract the concept code from a concept reference or code.

    Args:
        concept_ref_or_code: The concept reference (domain.ConceptCode) or concept code (ConceptCode)

    Returns:
        The concept code
    """
    if not is_concept_ref_or_code_valid(concept_ref_or_code):
        msg = f"Invalid concept_ref_or_code: '{concept_ref_or_code}' for extracting concept code"
        raise ValueError(msg)

    ref = QualifiedRef.parse(concept_ref_or_code)
    return ref.local_code
