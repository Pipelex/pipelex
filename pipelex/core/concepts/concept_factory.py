from typing import Any, Dict, List, Optional

from kajson.kajson_manager import KajsonManager
from pydantic import BaseModel

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_blueprint import (
    ConceptBlueprint,
    ConceptStructureBlueprint,
    ConceptStructureBlueprintFieldType,
    ConceptStructureBlueprintType,
)
from pipelex.core.concepts.concept_native import NativeConceptEnumData, is_native_concept
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.stuffs.stuff_content import TextContent
from pipelex.create.structured_output_generator import StructureGenerator
from pipelex.exceptions import ConceptFactoryError, StructureClassError


class DomainAndConceptCode(BaseModel):
    """Small model to represent domain and concept code pair."""

    domain: str
    concept_code: str


class ConceptFactory:
    @classmethod
    def normalize_structure_blueprint(cls, structure_dict: Dict[str, ConceptStructureBlueprintType]) -> Dict[str, ConceptStructureBlueprint]:
        """Convert a mixed structure dictionary to a proper ConceptStructureBlueprint dictionary.

        Args:
            structure_dict: Dictionary that may contain strings or ConceptStructureBlueprint objects

        Returns:
            Dictionary with all values as ConceptStructureBlueprint objects
        """
        normalized: Dict[str, ConceptStructureBlueprint] = {}

        for field_name, field_value in structure_dict.items():
            if isinstance(field_value, str):
                # Convert string definition to ConceptStructureBlueprint for text field
                normalized[field_name] = ConceptStructureBlueprint(
                    definition=field_value,
                    type=ConceptStructureBlueprintFieldType.TEXT,  # Explicitly set as text field
                    required=True,  # Default for simple string definitions
                )
            else:
                normalized[field_name] = field_value

        return normalized

    @classmethod
    def make_implicit_concept(cls, concept_string: str) -> Concept:
        ConceptBlueprint.validate_concept_string(concept_string=concept_string)
        return Concept(
            code=concept_string.split(".")[1],
            domain=SpecialDomain.IMPLICIT,
            definition=concept_string,
            structure_class_name=TextContent.__name__,
        )

    @classmethod
    def construct_concept_string_with_domain(cls, domain: str, concept_code: str) -> str:
        return f"{domain}.{concept_code}"

    @classmethod
    def make(cls, concept_code: str, domain: str, definition: str, structure_class_name: str, refines: Optional[str] = None) -> Concept:
        return Concept(
            code=concept_code,
            domain=domain,
            definition=definition,
            structure_class_name=structure_class_name,
            refines=refines,
        )

    @classmethod
    def make_native_concept(cls, native_concept_data: NativeConceptEnumData) -> Concept:
        return Concept(
            code=native_concept_data.code,
            domain=SpecialDomain.NATIVE,
            definition=native_concept_data.definition,
            structure_class_name=native_concept_data.content_class_name,
        )

    @classmethod
    def make_domain_and_concept_code_from_concept_string_or_concept_code(
        cls, domain: str, concept_string_or_concept_code: str, concept_codes_from_the_same_domain: Optional[List[str]] = None
    ) -> DomainAndConceptCode:
        # At this point, the concept_string_or_concept_code is already validated
        if "." in concept_string_or_concept_code:
            # Is a concept string.
            parts = concept_string_or_concept_code.rsplit(".")
            return DomainAndConceptCode(domain=parts[0], concept_code=parts[1])
        else:
            if is_native_concept(concept_string_or_concept_code=concept_string_or_concept_code):
                return DomainAndConceptCode(domain=SpecialDomain.NATIVE, concept_code=concept_string_or_concept_code)

            elif (
                concept_codes_from_the_same_domain and concept_string_or_concept_code in concept_codes_from_the_same_domain
            ):  # Is a concept code from the same domain
                return DomainAndConceptCode(domain=domain, concept_code=concept_string_or_concept_code)
            else:
                return DomainAndConceptCode(domain=SpecialDomain.IMPLICIT.value, concept_code=concept_string_or_concept_code)

    @classmethod
    def make_refine(cls, refine: str) -> str:
        if ConceptBlueprint.is_native_concept_string_or_concept_code(concept_string_or_concept_code=refine):
            if "." in refine:
                return refine
            else:
                return f"{SpecialDomain.NATIVE}.{refine}"
        else:
            raise ConceptFactoryError(f"Refine '{refine}' is not a native concept")

    @classmethod
    def make_refines(cls, blueprint: ConceptBlueprint) -> Optional[str]:
        if blueprint.refines:
            return cls.make_refine(refine=blueprint.refines)
        return None

    @classmethod
    def make_from_blueprint(
        cls,
        domain: str,
        concept_code: str,
        blueprint: ConceptBlueprint,
        concept_codes_from_the_same_domain: Optional[List[str]] = None,
    ) -> Concept:
        ConceptBlueprint.validate_concept_code(concept_code=concept_code)
        structure_class_name: str
        current_refine: Optional[str] = None

        # Handle structure definition
        if blueprint.structure:
            if isinstance(blueprint.structure, str):
                # Structure is defined as a string - check if the class is in the registry and is valid
                if not Concept.is_valid_structure_class(structure_class_name=blueprint.structure):
                    raise StructureClassError(
                        f"Structure class '{blueprint.structure}' set for concept '{concept_code}' in domain '{domain}' "
                        "is not a registered subclass of StuffContent"
                    )
                structure_class_name = blueprint.structure
            else:
                # Structure is defined as a ConceptStructureBlueprint - run the structure generator and put it in the class registry
                try:
                    # Normalize the structure blueprint to ensure all values are ConceptStructureBlueprint objects
                    normalized_structure = cls.normalize_structure_blueprint(blueprint.structure)

                    python_code = StructureGenerator().generate_from_structure_blueprint(
                        class_name=concept_code,
                        structure_blueprint=normalized_structure,
                    )

                    # Execute the generated Python code to register the class
                    exec_globals: Dict[str, Any] = {}
                    exec(python_code, exec_globals)

                    # Register the generated class
                    KajsonManager.get_class_registry().register_class(exec_globals[concept_code])

                    # The structure_class_name of the concept is the concept_code
                    structure_class_name = concept_code

                except Exception as exc:
                    raise ConceptFactoryError(f"Error generating structure class for concept '{concept_code}' in domain '{domain}': {exc}") from exc

        # Handle refines definition
        elif blueprint.refines:
            # If we have refines, validate that there is no structure related to the concept code in the class registry
            if Concept.is_valid_structure_class(structure_class_name=concept_code):
                raise ConceptFactoryError(
                    f"Concept '{concept_code}' in domain '{domain}' has refines but also has a structure class registered. "
                    "A concept cannot have both structure and refines."
                )
            current_refine = cls.make_refines(blueprint=blueprint)
            structure_class_name = current_refine.split(".")[1] + "Content" if current_refine else TextContent.__name__
        # Handle neither structure nor refines - check the class registry
        else:
            # If there is a class, use it. structure_class_name is then the concept_code
            if Concept.is_valid_structure_class(structure_class_name=concept_code):
                structure_class_name = concept_code
            else:
                # If there is NO class, the fallback class is TextContent.__name__
                structure_class_name = TextContent.__name__

        domain_and_concept_code = cls.make_domain_and_concept_code_from_concept_string_or_concept_code(
            domain=domain,
            concept_string_or_concept_code=concept_code,
            concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
        )

        return Concept(
            domain=domain_and_concept_code.domain,
            code=domain_and_concept_code.concept_code,
            definition=blueprint.definition,
            structure_class_name=structure_class_name,
            refines=current_refine,
        )
