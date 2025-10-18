"""Utilities for parsing and validating multiplicity notation in concept specifications."""

import re


class MultiplicityParseResult:
    """Result of parsing a concept string with multiplicity notation."""

    def __init__(self, concept: str, multiplicity: int | bool | None):
        self.concept: str = concept
        self.multiplicity: int | bool | None = multiplicity


def parse_concept_with_multiplicity(concept_spec: str) -> MultiplicityParseResult:
    """Parse a concept specification string to extract concept and multiplicity.

    Supported formats:
    - "ConceptName" -> (ConceptName, None)
    - "ConceptName[]" -> (ConceptName, True)
    - "ConceptName[5]" -> (ConceptName, 5)
    - "domain.ConceptName" -> (domain.ConceptName, None)
    - "domain.ConceptName[]" -> (domain.ConceptName, True)
    - "domain.ConceptName[5]" -> (domain.ConceptName, 5)

    Args:
        concept_spec: Concept specification string with optional multiplicity brackets

    Returns:
        MultiplicityParseResult with concept (without brackets) and multiplicity value
    """
    pattern = r"^(.+?)(?:\[(\d*)\])?$"
    match = re.match(pattern, concept_spec)

    if not match:
        # Should not happen with the regex, but handle gracefully
        return MultiplicityParseResult(concept=concept_spec, multiplicity=None)

    concept = match.group(1)
    bracket_content = match.group(2)

    multiplicity: int | bool | None
    if bracket_content is None:
        # No brackets - single item
        multiplicity = None
    elif bracket_content == "":
        # Empty brackets [] - variable list
        multiplicity = True
    else:
        # Number in brackets [N] - fixed count
        multiplicity = int(bracket_content)

    return MultiplicityParseResult(concept=concept, multiplicity=multiplicity)


def validate_multiplicity_syntax(concept_spec: str) -> bool:
    """Validate that a concept specification uses correct multiplicity syntax.

    Valid formats:
    - "ConceptName"
    - "ConceptName[]"
    - "ConceptName[N]" where N is a positive integer
    - "domain.ConceptName" (and variants with brackets)

    Args:
        concept_spec: Concept specification string to validate

    Returns:
        True if valid, False otherwise
    """
    # Pattern allows: ConceptName, domain.ConceptName, with optional [] or [N]
    pattern = r"^[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?(?:\[\d*\])?$"
    return bool(re.match(pattern, concept_spec))
