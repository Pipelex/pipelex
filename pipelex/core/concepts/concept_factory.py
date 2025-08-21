from typing import Any, Dict, List, Union

from pydantic import ValidationError

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_code_factory import ConceptCodeFactory
from pipelex.core.concepts.concept_native import NativeConceptData
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.stuffs.stuff_content import TextContent
from pipelex.create.structured_output_generator import generate_structured_output_from_inline_definition
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
    def _make_refines(cls, domain: str, refines: Union[str, List[str]]) -> List[str]:
        refines_list = refines if isinstance(refines, list) else [refines]

        new_refines: List[str] = []
        for refine in refines_list:
            concept_code = ConceptCodeFactory.make_concept_code_from_str(concept_str=refine, domain=domain, fallback_domain=domain)
            new_refines.append(concept_code)
        return new_refines
    
    @classmethod
    def make_concept_from_blueprint(
        cls,
        domain: str,
        code: str,
        concept_blueprint: ConceptBlueprint,
    ) -> Concept:
        current_refines: List[str]
        if concept_blueprint.refines:
            current_refines = cls._make_refines(domain=domain, refines=concept_blueprint.refines)
        else:
            current_refines = []

        structure_class_name: str = code
        if concept_blueprint.structure:
            if isinstance(concept_blueprint.structure, str):
                # Structure is defined inline - generate Python class dynamically
                if not Concept.is_valid_structure_class(structure_class_name=concept_blueprint.structure):
                    raise StructureClassError(
                        f"Structure class '{concept_blueprint.structure}' set for concept '{code}' in domain '{domain}' "
                        "is not a registered subclass of StuffContent"
                    )
                structure_class_name = concept_blueprint.structure
            else:
                # Structure is defined as a ConceptStructureBlueprint
                try:
                    # Generate Python class from inline definition
                    python_code = generate_structured_output_from_inline_definition(
                        class_name=code,
                        fields_def=concept_blueprint.structure_to_field_def(),
                        enums=None,  # TODO: Handle enums if needed in the future
                    )

                    # Execute the generated Python code to register the class
                    exec_globals: Dict[str, Any] = {}
                    exec(python_code, exec_globals)

                    # Get the generated class and register it
                    generated_class = exec_globals[code]
                    get_class_registry().register_class(generated_class)

                except Exception as exc:
                    raise ConceptFactoryError(f"Error generating structure class for concept '{code}' in domain '{domain}': {exc}") from exc
        elif Concept.is_valid_structure_class(structure_class_name=code):
            # No structure defined on the blueprint, but the concept code is a valid structure class
            pass
        else:
            if concept_blueprint.refines:
                # Has a refining element
                pass
            else:
                # Fallback to Text structure
                structure_class_name = TextContent.__name__
                current_refines = [get_native_concept_code("Text")]

        refines = cls._make_refines(domain=domain, refines=current_refines)
        return Concept(
            code=ConceptCodeFactory.make_concept_code(domain, code),
            domain=domain,
            definition=concept_blueprint.definition,
            structure_class_name=structure_class_name,
            refines=refines,
        )
