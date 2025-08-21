from typing import Any, Dict, List, Union

from pydantic import ValidationError

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_code_factory import ConceptCodeFactory
from pipelex.core.concepts.concept_native import NativeConcept, NativeConceptClass
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.stuffs.stuff_content import TextContent
from pipelex.create.structured_output_generator import generate_structured_output_from_inline_definition
from pipelex.exceptions import ConceptFactoryError, StructureClassError
from pipelex.hub import get_class_registry


class ConceptFactory:
    @classmethod
    def make_refines(cls, domain: str, refines: Union[str, List[str]]) -> List[str]:
        if isinstance(refines, str):
            concept_str_list = [refines]
        else:
            concept_str_list = refines
        new_refines: List[str] = []
        for concept_str in concept_str_list:
            concept_code = ConceptCodeFactory.make_concept_code_from_str(concept_str=concept_str, domain=domain, fallback_domain=domain)
            new_refines.append(concept_code)
        return new_refines

    @classmethod
    def make_concept_from_definition_str(
        cls,
        domain_code: str,
        concept_str: str,
        definition: str,
    ) -> Concept:
        structure_class_name: str
        refines: List[str]
        if Concept.concept_str_contains_domain(concept_str=concept_str):
            concept_name = Concept.extract_concept_name_from_str(concept_str=concept_str)
        else:
            concept_name = concept_str
        if Concept.is_valid_structure_class(structure_class_name=concept_name):
            # structure is set implicitly, by the concept's code
            structure_class_name = concept_name
            refines = []
        else:
            structure_class_name = TextContent.__name__
            refines = [NativeConcept.TEXT.code]

        try:
            the_concept = Concept(
                code=ConceptCodeFactory.make_concept_code(domain_code, concept_name),
                domain=domain_code,
                definition=definition,
                structure_class_name=structure_class_name,
                refines=refines,
            )
            return Concept.model_validate(the_concept)
        except ValidationError as exc:
            raise ConceptFactoryError(f"Error validating concept: {exc}") from exc

    @classmethod
    def make_concept_from_blueprint(
        cls,
        domain: str,
        code: str,
        concept_blueprint: ConceptBlueprint,
    ) -> Concept:
        current_refines: List[str]
        if concept_blueprint.refines:
            current_refines = cls.make_refines(domain=domain, refines=concept_blueprint.refines)
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
                current_refines = [NativeConcept.TEXT.code]

        refines = cls.make_refines(domain=domain, refines=current_refines)
        return Concept(
            code=ConceptCodeFactory.make_concept_code(domain, code),
            domain=domain,
            definition=concept_blueprint.definition,
            structure_class_name=structure_class_name,
            refines=refines,
        )

    @classmethod
    def make_native_concept(cls, native_concept: NativeConcept) -> Concept:
        definition: str
        match native_concept:
            case NativeConcept.TEXT:
                definition = "A text"
            case NativeConcept.IMAGE:
                definition = "An image"
            case NativeConcept.PDF:
                definition = "A PDF"
            case NativeConcept.TEXT_AND_IMAGES:
                definition = "A text and an image"
            case NativeConcept.NUMBER:
                definition = "A number"
            case NativeConcept.LLM_PROMPT:
                definition = "A prompt for an LLM"
            case NativeConcept.DYNAMIC:
                definition = "A dynamic concept"
            case NativeConcept.PAGE:
                definition = "The content of a page of a document, comprising text and linked images as well as an optional page view image"
            case NativeConcept.ANYTHING:
                raise RuntimeError("NativeConcept.ANYTHING cannot be used as a concept")

        return Concept(
            code=native_concept.code,
            domain=SpecialDomain.NATIVE,
            definition=definition,
            structure_class_name=native_concept.content_class_name,
        )

    @classmethod
    def make_native_concept_from_native_concept_class(cls, native_concept_class: NativeConceptClass) -> Concept:
        native_concept = native_concept_class.native_concept
        return cls.make_native_concept(native_concept=native_concept)

    @classmethod
    def list_native_concepts(cls) -> List[Concept]:
        concepts: List[Concept] = []
        for native_concept in NativeConcept:
            if native_concept == NativeConcept.ANYTHING:
                continue
            concepts.append(cls.make_native_concept(native_concept=native_concept))
        return concepts
