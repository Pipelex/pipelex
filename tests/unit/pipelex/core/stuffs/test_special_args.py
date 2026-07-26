"""Test stuff with special args like 'content' that should work without conflicts."""

from typing import Callable, ClassVar

import pytest

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_structure_blueprint import (
    RESERVED_FIELD_NAMES,
    ConceptStructureBlueprint,
    ConceptStructureBlueprintFieldType,
)
from pipelex.core.stuffs.stuff_factory import StuffContentFactory, StuffFactory
from pipelex.method_hub import get_concept_library


class TestSpecialArgsStuff:
    """Test stuff with field names that should not conflict with internal fields."""

    # Field names that users should be able to use
    # These look like they might conflict but actually work fine with our underscore-prefix approach
    ALLOWED_FIELD_NAMES: ClassVar[list[str]] = [
        # Stuff class fields - these are OK because artefact uses underscore-prefixed versions
        "stuff_code",
        "stuff_name",
        "concept",
        "content",
    ]

    # Examples of field names that should fail validation
    # Includes the actual RESERVED_FIELD_NAMES plus additional examples for testing
    # Sorted to ensure consistent ordering across pytest-xdist workers
    FAILING_FIELD_NAMES: ClassVar[list[str]] = sorted(
        [
            *RESERVED_FIELD_NAMES,
            # Generic underscore-prefixed names (additional failing examples)
            "_internal",
            "_private",
            "_reserved",
        ]
    )

    @pytest.mark.parametrize("field_name", ALLOWED_FIELD_NAMES)
    def test_make_artefact_with_allowed_field_names(
        self,
        field_name: str,
        load_empty_library: Callable[[], None],
    ):
        """Test that creating an artefact works with field names that look like they might conflict.

        Users should be able to use field names like 'content', 'stuff_name', etc.
        These don't conflict because internal metadata fields use underscore prefixes.
        """
        load_empty_library()
        domain_code = "test"
        concept_library = get_concept_library()

        # Create a ConceptBlueprint with a structure containing the field name
        concept_blueprint = ConceptBlueprint(
            description=f"A concept with {field_name} field",
            structure={
                field_name: ConceptStructureBlueprint(
                    description=f"The {field_name} field",
                    type=ConceptStructureBlueprintFieldType.TEXT,
                ),
            },
        )

        # Make a Concept using ConceptFactory
        concept = ConceptFactory.make_from_blueprint(
            domain_code=domain_code,
            concept_code=f"Concept{field_name.replace('_', '').title()}",
            blueprint_or_string_description=concept_blueprint,
        )

        concept_library.add_new_concept(concept)

        # Create content for the concept
        content = StuffContentFactory.make_stuff_content_from_concept_required(
            concept=concept,
            value={field_name: f"This is my {field_name}"},
        )

        # Create a stuff with the content
        stuff = StuffFactory.make_stuff(
            concept=concept,
            content=content,
            name="my_stuff",
        )

        # Calling make_artefact should work without errors
        stuff.make_artefact()

    @pytest.mark.parametrize("field_name", FAILING_FIELD_NAMES)
    def test_reserved_field_names_raise_error(
        self,
        field_name: str,
        load_empty_library: Callable[[], None],
    ):
        """Test that reserved field names raise a validation error.

        The following should NOT be allowed as user field names:
        - Pydantic BaseModel reserved attributes (model_config, model_fields, etc.)
        - Internal underscore-prefixed fields (_stuff_name, _content_class, etc.)
        - Any field name starting with underscore (reserved for internal Pipelex use)
        """
        load_empty_library()

        # Creating a ConceptBlueprint with a reserved field name in structure should raise ValueError
        with pytest.raises(ValueError, match=r"(reserved field|underscore)"):
            ConceptBlueprint(
                description=f"A concept with {field_name} field",
                structure={
                    field_name: ConceptStructureBlueprint(
                        description=f"The {field_name} field",
                        type=ConceptStructureBlueprintFieldType.TEXT,
                    ),
                },
            )
