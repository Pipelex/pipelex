from inspect import getsource
from typing import Any, Dict, List, Optional, Type, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pipelex.core.concept import Concept
from pipelex.core.concept_code_factory import ConceptCodeFactory
from pipelex.core.concept_native import NativeConcept
from pipelex.core.domain import SpecialDomain
from pipelex.core.stuff_content import TextContent
from pipelex.exceptions import ConceptFactoryError, StructureClassError
from pipelex.hub import get_class_registry


class ConceptBlueprint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    definition: str
    structure: Optional[str] = None
    refines: Union[str, List[str]] = Field(default_factory=list)
    domain: Optional[str] = None


class ConceptFactory:
    @classmethod
    def make_refines(cls, domain: str, refines: Union[str, List[str]]) -> List[str]:
        if isinstance(refines, str):
            concept_str_list = [refines]
        else:
            concept_str_list = refines
        new_refines: List[str] = []
        for concept_str in concept_str_list:
            concept_code = ConceptCodeFactory.make_concept_code_from_str(concept_str=concept_str, fallback_domain=domain)
            new_refines.append(concept_code)
        return new_refines

    @classmethod
    def make_from_details_dict_if_possible(
        cls,
        domain: str,
        code: str,
        details_dict: Dict[str, Any],
    ) -> Optional[Concept]:
        if concept_definition := details_dict.pop("Concept", None):
            details_dict["definition"] = concept_definition
            details_dict["refines"] = ConceptFactory.make_refines(domain=domain, refines=details_dict.pop("refines", []))
            concept_blueprint = ConceptBlueprint.model_validate(details_dict)
            the_concept = ConceptFactory.make_concept_from_blueprint(domain=domain, code=code, concept_blueprint=concept_blueprint)
            return the_concept
        elif "definition" in details_dict:
            # legacy format
            details_dict["domain"] = domain
            details_dict["refines"] = ConceptFactory.make_refines(domain=domain, refines=details_dict.pop("refines", []))
            details_dict["code"] = ConceptCodeFactory.make_concept_code(domain, code)
            try:
                the_concept = Concept.model_validate(details_dict)
            except ValidationError as e:
                raise ConceptFactoryError(f"Error validating concept: {e}") from e
            return the_concept
        else:
            return None

    @classmethod
    def make_from_details_dict(
        cls,
        domain_code: str,
        code: str,
        details_dict: Dict[str, Any],
    ) -> Concept:
        concept_definition = details_dict.pop("Concept", None)
        if not concept_definition:
            raise ConceptFactoryError(f"Concept '{code}' in domain '{domain_code}' has no definition")
        details_dict["definition"] = concept_definition
        details_dict["domain"] = domain_code
        refines = ConceptFactory.make_refines(domain=domain_code, refines=details_dict.pop("refines", []))
        if not refines and not details_dict.get("structure"):
            # No structure? this refines Text
            refines = [NativeConcept.TEXT.code]
        details_dict["refines"] = refines
        concept_blueprint = ConceptBlueprint.model_validate(details_dict)
        the_concept = ConceptFactory.make_concept_from_blueprint(domain=domain_code, code=code, concept_blueprint=concept_blueprint)
        return the_concept

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
        except ValidationError as e:
            raise ConceptFactoryError(f"Error validating concept: {e}") from e

    @classmethod
    def make_concept_from_blueprint(
        cls,
        domain: str,
        code: str,
        concept_blueprint: ConceptBlueprint,
    ) -> Concept:
        structure_class_name: str
        if structure := concept_blueprint.structure:
            # structure is set explicitly
            if not Concept.is_valid_structure_class(structure_class_name=structure):
                raise StructureClassError(
                    f"Structure class '{structure}' set for concept '{code}' in domain '{domain}' is not a registered subclass of StuffContent"
                )
            structure_class_name = structure
        elif Concept.is_valid_structure_class(structure_class_name=code):
            # structure is set implicitly, by the concept's code
            structure_class_name = code
        else:
            structure_class_name = TextContent.__name__

        refines_list: List[str]
        if isinstance(concept_blueprint.refines, str):
            refines_list = [concept_blueprint.refines]
        else:
            refines_list = concept_blueprint.refines

        return Concept(
            code=ConceptCodeFactory.make_concept_code(domain, code),
            domain=domain,
            definition=concept_blueprint.definition,
            structure_class_name=structure_class_name,
            refines=refines_list,
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
    def list_native_concepts(cls) -> List[Concept]:
        concepts: List[Concept] = []
        for native_concept in NativeConcept:
            if native_concept == NativeConcept.ANYTHING:
                continue
            concepts.append(cls.make_native_concept(native_concept=native_concept))
        return concepts

    @classmethod
    def get_concept_class_source_code(cls, concept_name: str, base_class: Type[Any]) -> str:
        if not get_class_registry().has_class(concept_name):
            raise RuntimeError(f"Class '{concept_name}' not found in registry")

        cls = get_class_registry().get_required_subclass(name=concept_name, base_class=base_class)
        return getsource(cls)
