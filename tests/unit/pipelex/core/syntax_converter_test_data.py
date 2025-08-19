"""Test data for PipelexSyntaxConverter tests."""

from typing import ClassVar, List, Tuple

from pipelex.core.bundle.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concept.concept_blueprint import ConceptBlueprint


class SyntaxConverterTestCases:
    """Test cases for PipelexSyntaxConverter with TOML content and expected blueprints."""

    SIMPLE_DOMAIN = (
        "simple_domain",
        """
domain = "simple_test"
""",
        PipelexBundleBlueprint(
            domain="simple_test",
            definition="A simple test domain",
        ),
    )

    SIMPLE_DOMAIN_WITH_CONCEPTS = (
        "simple_domain_with_concepts",
        """
domain = "simple_test"
definition = "A simple test domain"
""",
        PipelexBundleBlueprint(
            domain="simple_test",
            definition="A simple test domain",
        ),
    )

    DOMAIN_WITH_SYSTEM_PROMPTS = (
        "domain_with_system_prompts",
        """
domain = "system_prompt_test"
definition = "A domain with system prompts"
system_prompt = "You are an expert assistant"
system_prompt_to_structure = "Generate structured output"
prompt_template_to_structure = "Structure the following data: ..."
""",
        PipelexBundleBlueprint(
            domain="system_prompt_test",
            definition="A domain with system prompts",
            system_prompt="You are an expert assistant",
            system_prompt_to_structure="Generate structured output",
            prompt_template_to_structure="Structure the following data: ...",
        ),
    )

    SIMPLE_CONCEPTS = (
        "simple_concept",
        """
domain = "simple_concept"
definition = "A simple concept"

[concepts]
Concept1 = "A concept"
Concept2 = "A concept"
""",
        PipelexBundleBlueprint(
            domain="simple_concept",
            definition="A simple concept",
            concepts={
                "Concept1": ConceptBlueprint(definition="A concept"),
                "Concept2": ConceptBlueprint(definition="A concept"),
            },
        ),
    )

    CONCEPTS_WITH_REFINES = (
        "concepts_with_refines",
        """
domain = "refining_concepts"
definition = "Domain with concepts that refine others"

[concepts]
Concept1 = "A concept"
Concept2 = "A concept"

[concepts.Concept3]
definition = "A concept"
refines = "Concept2"
""",
        PipelexBundleBlueprint(
            domain="refining_concepts",
            definition="Domain with concepts that refine others",
            concepts={
                "Concept1": ConceptBlueprint(definition="A concept"),
                "Concept2": ConceptBlueprint(definition="A concept"),
                "Concept3": ConceptBlueprint(definition="A concept", refines="Concept2"),
            },
        ),
    )

    CONCEPTS_WITH_STRUCTURES = (
        "concepts_with_structures",
        """
domain = "structured_concepts"
definition = "Domain with structured concepts"

[concepts]
SimpleData = "Simple data concept"

[concepts.PersonInfo]
definition = "Information about a person"

[concepts.PersonInfo.structure]
name = { type = "text", definition = "The name of the person", required = true }
age = { type = "number", definition = "The age of the person", required = true }
birthdate = { type = "date", definition = "The birthdate of the person", required = true }
""",
        PipelexBundleBlueprint(
            domain="structured_concepts",
            definition="Domain with structured concepts",
            concepts={
                "SimpleData": ConceptBlueprint(definition="Simple data concept"),
                "PersonInfo": ConceptBlueprint(
                    definition="Information about a person",
                    structure={
                        "name": {"type": "text", "definition": "The name of the person", "required": True},
                        "age": {"type": "number", "definition": "The age of the person", "required": True},
                        "birthdate": {"type": "date", "definition": "The birthdate of the person", "required": True},
                    },
                ),
            },
        ),
    )

    EMPTY_CONCEPTS = (
        "empty_concepts",
        """
domain = "empty_concepts"
definition = "Domain with empty concept section"

[concepts]
""",
        PipelexBundleBlueprint(domain="empty_concepts", definition="Domain with empty concept section", concepts={}),
    )

    ####### ERROR TEST CASES #######
    INVALID_TOML_SYNTAX = (
        "invalid_toml_syntax",
        """
domain = "invalid_syntax"
definition = "Domain with invalid TOML syntax"

[concepts]
InvalidConcept = "This is missing a closing quote""",
        None,  # Should raise an exception
    )

    MISSING_DOMAIN = (
        "missing_domain",
        """# Missing domain field
definition = "Domain without domain field"

[concepts]
TestConcept = "A test concept"
""",
        None,  # Should raise an exception
    )

    # Collection of all valid test cases
    VALID_TEST_CASES: ClassVar[List[Tuple[str, str, PipelexBundleBlueprint]]] = [
        SIMPLE_DOMAIN,
        DOMAIN_WITH_SYSTEM_PROMPTS,
        CONCEPTS_WITH_STRUCTURES,
        CONCEPTS_WITH_REFINES,
        EMPTY_CONCEPTS,
    ]

    # Collection of error test cases
    ERROR_TEST_CASES: ClassVar[List[Tuple[str, str]]] = [
        # (INVALID_TOML_SYNTAX[0], INVALID_TOML_SYNTAX[1]),
        # (MISSING_DOMAIN[0], MISSING_DOMAIN[1]),
    ]
