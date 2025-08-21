from typing import Any, Dict, List

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_native import NativeConcept, NativeConceptData
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.stuffs.stuff_content import TextContent
from pipelex.create.structured_output_generator import generate_structured_output_from_blueprint_dict
from pipelex.exceptions import ConceptFactoryError, StructureClassError
from pipelex.hub import get_class_registry


class ConceptFactory:
    @classmethod
    def make_native_concept(cls, native_concept_data: NativeConceptData) -> Concept:
        return Concept(
            code=native_concept_data.code,
            domain=SpecialDomain.NATIVE,
            definition=native_concept_data.definition,
            structure_class_name=native_concept_data.content_class_name,
        )

    @classmethod
    def _make_refine(cls, domain: str, refine: str) -> str:
        if "." not in refine:
            if refine in [native_concept.value for native_concept in NativeConcept]:
                for native_concept in NativeConcept:
                    if native_concept.value == refine:
                        return f"{SpecialDomain.NATIVE.value}.{refine}"
            else:
                return f"{domain}.{refine}"
        return refine

    @classmethod
    def _make_refines(cls, domain: str, blueprint: ConceptBlueprint) -> List[str]:
        if isinstance(blueprint.refines, str):
            return [cls._make_refine(domain=domain, refine=blueprint.refines)]
        elif isinstance(blueprint.refines, list):
            return [cls._make_refine(domain=domain, refine=refine) for refine in blueprint.refines]
        return []

    @classmethod
    def make_concept_from_blueprint(
        cls,
        domain: str,
        concept_code: str,
        concept_blueprint: ConceptBlueprint,
    ) -> Concept:
        # Ok so the way to do it is. At this point, we know that we cannot have structure AND refines at the same time.
        # Then if we have neither refine, neither structure, check the class registry. If there is a class, use it.
        # structure_class_name is then the concept_code. If there is NO class, the fallback class is TextContent.__name__

        # If we have refines:
        # pass for now.

        # If we have structure: If isintance(structure, str), check if the class is in the classregistry and that its valid.
        # And the structure_class_name is the structure
        # if (isinstance(structure, ConceptStructureBlueprint)): run the structure generator and put it in the class registry,
        # then the structure_class_name of the concept is the concept_name
        # If we have refines, validate that there is no structure related to the concept code in the class registry.

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
                    # Generate Python class from blueprint definition
                    python_code = generate_structured_output_from_blueprint_dict(
                        class_name=concept_code,
                        structure_blueprint=concept_blueprint.structure,  # type: ignore
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
            current_refines = cls._make_refines(domain=domain, blueprint=concept_blueprint)
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
