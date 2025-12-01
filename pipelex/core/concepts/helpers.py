def strip_multiplicity_from_concept_string_or_code(concept_string_or_code: str) -> str:
    """Strip multiplicity from a concept string or code.

    Args:
        concept_string_or_code: The concept string or code to strip multiplicity from

    Returns:
        The concept string or code without multiplicity
    """
    if "[" in concept_string_or_code:
        return concept_string_or_code.split("[", maxsplit=1)[0]
    return concept_string_or_code
