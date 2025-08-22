from typing import Any, Dict, List, Optional

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_blueprint import (
    ConceptBlueprint,
    ConceptStructureBlueprint,
    ConceptStructureBlueprintFieldType,
    ConceptStructureBlueprintType,
)
from pipelex.core.concepts.concept_native import NativeConceptEnum, NativeConceptEnumData
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.stuffs.stuff_content import TextContent
from pipelex.create.structured_output_generator import StructureGenerator
from pipelex.exceptions import ConceptFactoryError, StructureClassError
from pipelex.hub import get_class_registry


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
    def make(cls, concept_code: str, domain: str, definition: str, structure_class_name: str, refines: Optional[List[str]] = None) -> Concept:
        return Concept(
            code=concept_code,
            domain=domain,
            definition=definition,
            structure_class_name=structure_class_name,
            refines=refines or [],
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
    def make_refine(cls, domain: str, refine: str) -> str:
        if "." not in refine:
            if refine in [native_concept.value for native_concept in NativeConceptEnum]:
                for native_concept in NativeConceptEnum:
                    if native_concept.value == refine:
                        return f"{SpecialDomain.NATIVE.value}.{refine}"
            else:
                return f"{domain}.{refine}"
        return refine

    @classmethod
    def make_refines(cls, domain: str, blueprint: ConceptBlueprint) -> List[str]:
        if isinstance(blueprint.refines, str):
            return [cls.make_refine(domain=domain, refine=blueprint.refines)]
        elif isinstance(blueprint.refines, list):
            return [cls.make_refine(domain=domain, refine=refine) for refine in blueprint.refines]
        return []

    @classmethod
    def make_from_blueprint(
        cls,
        domain: str,
        concept_code: str,
        concept_blueprint: ConceptBlueprint,
    ) -> Concept:
        structure_class_name: str
        current_refines: List[str] = []

        # Handle structure definition
        if concept_blueprint.structure:
            if isinstance(concept_blueprint.structure, str):
                # Structure is defined as a string - check if the class is in the registry and is valid
                if not Concept.is_valid_structure_class(structure_class_name=concept_blueprint.structure):
                    raise StructureClassError(
                        f"Structure class '{concept_blueprint.structure}' set for concept '{concept_code}' in domain '{domain}' "
                        "is not a registered subclass of StuffContent"
                    )
                structure_class_name = concept_blueprint.structure
            else:
                # Structure is defined as a ConceptStructureBlueprint - run the structure generator and put it in the class registry
                try:
                    # Normalize the structure blueprint to ensure all values are ConceptStructureBlueprint objects
                    normalized_structure = cls.normalize_structure_blueprint(concept_blueprint.structure)

                    python_code = StructureGenerator().generate_from_structure_blueprint(
                        class_name=concept_code,
                        structure_blueprint=normalized_structure,
                    )

                    # Execute the generated Python code to register the class
                    exec_globals: Dict[str, Any] = {}
                    exec(python_code, exec_globals)

                    # Get the generated class and register it
                    generated_class = exec_globals[concept_code]
                    get_class_registry().register_class(generated_class)

                    # The structure_class_name of the concept is the concept_code
                    structure_class_name = concept_code

                except Exception as exc:
                    raise ConceptFactoryError(f"Error generating structure class for concept '{concept_code}' in domain '{domain}': {exc}") from exc

        # Handle refines definition
        elif concept_blueprint.refines:
            # If we have refines, validate that there is no structure related to the concept code in the class registry
            if Concept.is_valid_structure_class(structure_class_name=concept_code):
                raise ConceptFactoryError(
                    f"Concept '{concept_code}' in domain '{domain}' has refines but also has a structure class registered. "
                    "A concept cannot have both structure and refines."
                )
            # pass for now
            current_refines = cls.make_refines(domain=domain, blueprint=concept_blueprint)
            structure_class_name = TextContent.__name__  # Default structure for refined concepts

        # Handle neither structure nor refines - check the class registry
        else:
            # If there is a class, use it. structure_class_name is then the concept_code
            if Concept.is_valid_structure_class(structure_class_name=concept_code):
                structure_class_name = concept_code
            else:
                # If there is NO class, the fallback class is TextContent.__name__
                structure_class_name = TextContent.__name__
                # Also add Text as a refines since we're using TextContent
                current_refines = []

        return Concept(
            code=concept_code,
            domain=domain,
            definition=concept_blueprint.definition,
            structure_class_name=structure_class_name,
            refines=current_refines,
        )
