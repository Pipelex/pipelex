from typing import Any, Dict, List, Optional, Tuple, Type

import shortuuid
from pydantic import BaseModel, ValidationError

from pipelex.core.concept import Concept
from pipelex.core.concept_code_factory import ConceptCodeFactory
from pipelex.core.concept_native import NativeConcept
from pipelex.core.stuff import Stuff
from pipelex.core.stuff_content import StuffContent, StuffContentInitableFromStr, TextContent
from pipelex.exceptions import ConceptError, PipelexError
from pipelex.hub import get_class_registry, get_concept_provider, get_required_concept
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error


class StuffFactoryError(PipelexError):
    pass


class StuffBlueprint(BaseModel):
    stuff_name: str
    concept_code: str
    content: Dict[str, Any] | str


class StuffFactory:
    @classmethod
    def make_stuff_name(cls, concept_str: str) -> str:
        return Stuff.make_stuff_name(concept_str=concept_str)

    @classmethod
    def make_stuff(
        cls,
        concept_str: str,
        content: StuffContent,
        name: Optional[str] = None,
        code: Optional[str] = None,
    ) -> Stuff:
        try:
            concept_code = ConceptCodeFactory.make_concept_code_from_str(concept_str=concept_str)
        except ConceptError:
            stuff_ref = name or code or "unnamed"
            raise StuffFactoryError(f"Concept '{concept_str}' does not contain a domain, could not make stuff '{stuff_ref}'")
        if not name:
            name = cls.make_stuff_name(concept_code)
        return Stuff(
            concept_code=concept_code,
            content=content,
            stuff_name=name,
            stuff_code=code or shortuuid.uuid()[:5],
        )

    @classmethod
    def make_stuff_using_concept(
        cls,
        concept: Concept,
        content: StuffContent,
        name: Optional[str] = None,
        code: Optional[str] = None,
    ) -> Stuff:
        if not name:
            name = cls.make_stuff_name(concept_str=concept.code)
        return Stuff(
            concept_code=concept.code,
            content=content,
            stuff_name=name,
            stuff_code=code or shortuuid.uuid()[:5],
        )

    @classmethod
    def make_from_blueprint(cls, blueprint: StuffBlueprint) -> "Stuff":
        if isinstance(blueprint.content, str) and get_concept_provider().is_compatible_by_concept_code(
            tested_concept_code=blueprint.concept_code, wanted_concept_code=NativeConcept.TEXT.code
        ):
            the_stuff = cls.make_from_str(
                concept_str=NativeConcept.TEXT.code,
                str_value=blueprint.content,
                name=blueprint.stuff_name,
            )
        else:
            the_stuff_content = StuffContentFactory.make_stuffcontent_from_concept_code_required(
                concept_code=blueprint.concept_code, value=blueprint.content
            )
            the_stuff = cls.make_stuff(
                concept_str=blueprint.concept_code,
                content=the_stuff_content,
                name=blueprint.stuff_name,
            )
        return the_stuff

    @classmethod
    def make_from_blueprint_dict(cls, blueprint: StuffBlueprint) -> "Stuff":
        return cls.make_from_blueprint(blueprint=blueprint)

    @classmethod
    def make_from_str(
        cls,
        str_value: str,
        name: Optional[str] = None,
        concept_str: str = NativeConcept.TEXT.code,
    ) -> Stuff:
        try:
            concept_code = ConceptCodeFactory.make_concept_code_from_str(concept_str=concept_str)
        except ConceptError:
            stuff_ref = name or "unnamed"
            raise StuffFactoryError(f"Concept '{concept_str}' does not contain a domain, could not make stuff '{stuff_ref}'")
        the_concept = get_required_concept(concept_code=concept_code)
        the_subclass_name = the_concept.structure_class_name
        the_subclass = get_class_registry().get_class(name=the_subclass_name) or eval(the_subclass_name)
        if not issubclass(the_subclass, StuffContentInitableFromStr):
            raise StuffFactoryError(f"Concept '{concept_code}', subclass '{the_subclass}' is not InitableFromStr")
        stuff_content: StuffContent = the_subclass.make_from_str(str_value)

        if not name:
            name = cls.make_stuff_name(concept_str)

        return Stuff(
            concept_code=concept_str,
            content=stuff_content,
            stuff_name=name,
            stuff_code=shortuuid.uuid()[:5],
        )

    @classmethod
    def make_multiple_text_from_str(cls, str_text_dict: Dict[str, str]) -> List[Stuff]:
        """
        Make multiple stuffs from a dictionary of strings.
        It is implied that each string value should be associated with a native.Text concept.
        """
        return [cls.make_from_str(concept_str=NativeConcept.TEXT.code, str_value=str_value, name=name) for name, str_value in str_text_dict.items()]

    @classmethod
    def make_multiple_stuff_from_str(cls, str_stuff_and_concepts_dict: Dict[str, Tuple[str, str]]) -> List[Stuff]:
        """
        Make multiple stuffs from a dictionary of strings.
        It is implied that each string value should be associated with a native.Text concept.
        """
        result: List[Stuff] = []
        for name, (concept_code, str_value) in str_stuff_and_concepts_dict.items():
            stuff = cls.make_from_str(concept_str=concept_code, str_value=str_value, name=name)
            result.append(stuff)
        return result

    @classmethod
    def combine_stuffs(
        cls,
        concept_code: str,
        stuff_contents: Dict[str, StuffContent],
        name: Optional[str] = None,
    ) -> Stuff:
        """
        Combine a dictionary of stuffs into a single stuff.
        """
        the_concept = get_required_concept(concept_code=concept_code)
        the_subclass_name = the_concept.structure_class_name
        the_subclass = get_class_registry().get_required_subclass(name=the_subclass_name, base_class=StuffContent)
        try:
            the_stuff_content = the_subclass.model_validate(obj=stuff_contents)
        except ValidationError as exc:
            raise StuffFactoryError(f"Error combining stuffs: {format_pydantic_validation_error(exc=exc)}") from exc
        return cls.make_stuff(
            concept_str=concept_code,
            content=the_stuff_content,
            name=name,
        )


class StuffContentFactoryError(PipelexError):
    pass


class StuffContentFactory:
    @classmethod
    def make_content_from_value(cls, stuff_content_subclass: Type[StuffContent], value: Dict[str, Any] | str) -> StuffContent:
        if isinstance(value, str) and stuff_content_subclass == TextContent:
            return TextContent(text=value)
        return stuff_content_subclass.model_validate(obj=value)

    @classmethod
    def make_stuffcontent_from_concept_code_required(cls, concept_code: str, value: Dict[str, Any] | str) -> StuffContent:
        """
        Create StuffContent from concept code, requiring the concept to be linked to a class in the registry.
        Raises StuffContentFactoryError if no registry class is found.
        """
        concept = get_required_concept(concept_code=concept_code)
        the_subclass_name = concept.structure_class_name
        the_subclass = get_class_registry().get_required_subclass(name=the_subclass_name, base_class=StuffContent)
        return cls.make_content_from_value(stuff_content_subclass=the_subclass, value=value)

    @classmethod
    def make_stuffcontent_from_concept_code_with_fallback(cls, concept_code: str, value: Dict[str, Any] | str) -> StuffContent:
        """
        Create StuffContent from concept code, falling back to TextContent if no registry class is found.
        """
        concept = get_required_concept(concept_code=concept_code)
        the_subclass_name = concept.structure_class_name
        the_subclass = get_class_registry().get_class(name=the_subclass_name)

        if the_subclass is None:
            return cls.make_content_from_value(stuff_content_subclass=TextContent, value=value)

        if not issubclass(the_subclass, StuffContent):
            raise StuffContentFactoryError(f"Concept '{concept_code}', subclass '{the_subclass}' is not a subclass of StuffContent")

        return cls.make_content_from_value(stuff_content_subclass=the_subclass, value=value)
