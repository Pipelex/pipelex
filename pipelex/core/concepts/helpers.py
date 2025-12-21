from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType


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
            normalized[field_name] = ConceptStructureBlueprint(
                description=field_value,
                type=ConceptStructureBlueprintFieldType.TEXT,
            )
        else:
            normalized[field_name] = field_value

    return normalized
