from typing import Any, Dict, List, Optional, Type, cast

import shortuuid
from pydantic import BaseModel, ValidationError, field_validator

from pipelex.client.protocol import StuffContentOrData
from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_native import NATIVE_CONCEPTS_DATA, NativeConceptEnum
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_content import (
    ListContent,
    StuffContent,
    TextContent,
)
from pipelex.exceptions import PipelexError
from pipelex.hub import get_class_registry, get_concept_provider
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error


class StuffFactoryError(PipelexError):
    pass


class StuffBlueprint(BaseModel):
    stuff_name: str
    concept_string: str
    content: Dict[str, Any] | str

    @field_validator("concept_string")
    def validate_concept_string(cls, concept_string: str) -> str:
        ConceptBlueprint.validate_concept_string(concept_string)
        return concept_string


class StuffFactory:
    @classmethod
    def make_stuff_name(cls, concept: Concept) -> str:
        return Stuff.make_stuff_name(concept=concept)

    @classmethod
    def make_from_str(cls, str_value: str, name: str) -> Stuff:
        return cls.make_stuff(
            concept=ConceptFactory.make_native_concept(native_concept_data=NATIVE_CONCEPTS_DATA[NativeConceptEnum.TEXT]),
            content=TextContent(text=str_value),
            name=name,
        )

    @classmethod
    def make_from_concept_string(cls, concept_string: str, name: str, content: StuffContent) -> Stuff:
        ConceptBlueprint.validate_concept_string(concept_string)
        concept = get_concept_provider().get_required_concept(concept_string=concept_string)
        return cls.make_stuff(
            concept=concept,
            content=content,
            name=name,
        )

    @classmethod
    def make_stuff(
        cls,
        concept: Concept,
        content: StuffContent,
        name: Optional[str] = None,
        code: Optional[str] = None,
    ) -> Stuff:
        if not name:
            name = cls.make_stuff_name(concept=concept)
        return Stuff(
            concept=concept,
            content=content,
            stuff_name=name,
            stuff_code=code or shortuuid.uuid()[:5],
        )

    @classmethod
    def make_stuff_using_concept_name_and_search_domains(
        cls,
        concept_name: str,
        search_domains: List[str],
        content: StuffContent,
        name: Optional[str] = None,
        code: Optional[str] = None,
    ) -> Stuff:
        # TODO: Add unit tests for this method
        concept_provider = get_concept_provider()
        concept = concept_provider.search_for_concept_in_domains(
            concept_code=concept_name,
            search_domains=search_domains,
        )
        if not concept:
            raise StuffFactoryError(f"Could not find a concept named '{concept_name}' in domains {search_domains}")
        return cls.make_stuff(concept=concept, content=content, name=name, code=code)

    @classmethod
    def make_from_blueprint(cls, blueprint: StuffBlueprint) -> "Stuff":
        concept_library = get_concept_provider()
        if isinstance(blueprint.content, str) and concept_library.is_compatible(
            tested_concept=concept_library.get_required_concept(concept_string=blueprint.concept_string),
            wanted_concept=concept_library.get_native_concept(native_concept=NativeConceptEnum.TEXT),
        ):
            the_stuff = cls.make_stuff(
                concept=concept_library.get_native_concept(native_concept=NativeConceptEnum.TEXT),
                content=TextContent(text=blueprint.content),
                name=blueprint.stuff_name,
            )
        else:
            the_stuff_content = StuffContentFactory.make_stuff_content_from_concept_required(
                concept=concept_library.get_required_concept(concept_string=blueprint.concept_string),
                value=blueprint.content,
            )
            the_stuff = cls.make_stuff(
                concept=concept_library.get_required_concept(concept_string=blueprint.concept_string),
                content=the_stuff_content,
                name=blueprint.stuff_name,
            )
        return the_stuff

    @classmethod
    def combine_stuffs(
        cls,
        concept: Concept,
        stuff_contents: Dict[str, StuffContent],
        name: Optional[str] = None,
    ) -> Stuff:
        # TODO: Add unit tests for this method
        """
        Combine a dictionary of stuffs into a single stuff.
        """
        the_subclass = get_class_registry().get_required_subclass(name=concept.structure_class_name, base_class=StuffContent)
        try:
            the_stuff_content = the_subclass.model_validate(obj=stuff_contents)
        except ValidationError as exc:
            raise StuffFactoryError(f"Error combining stuffs: {format_pydantic_validation_error(exc=exc)}") from exc
        return cls.make_stuff(
            concept=concept,
            content=the_stuff_content,
            name=name,
        )

    @classmethod
    def make_stuff_from_stuff_content_using_search_domains(
        cls,
        name: str,
        stuff_content_or_data: StuffContentOrData,
        search_domains: List[str],
        stuff_code: Optional[str] = None,
    ) -> Stuff:
        # TODO: Add unit tests for this method
        content: StuffContent
        concept_name: str
        if isinstance(stuff_content_or_data, ListContent):
            content = cast(ListContent[Any], stuff_content_or_data)
            if len(content.items) == 0:
                raise StuffFactoryError("ListContent in compact memory has no items")
            concept_name = type(content.items[0]).__name__
            try:
                return cls.make_stuff_using_concept_name_and_search_domains(
                    concept_name=concept_name,
                    search_domains=search_domains,
                    content=content,
                    name=name,
                    code=stuff_code,
                )
            except StuffFactoryError as exc:
                raise StuffFactoryError(f"Could not make stuff for ListContent '{name}': {exc}") from exc
        elif isinstance(stuff_content_or_data, StuffContent):
            content = stuff_content_or_data
            concept_class_name = type(content).__name__
            native_concept_class_names = [data.content_class_name for data in NATIVE_CONCEPTS_DATA.values()]

            if concept_class_name in native_concept_class_names:
                concept = get_concept_provider().get_required_concept(
                    concept_string=SpecialDomain.NATIVE.value + "." + concept_class_name.split("Content")[0]
                )
                return cls.make_stuff(
                    concept=concept,
                    content=content,
                    name=name,
                    code=stuff_code,
                )
            # For non-native StuffContent, we need to define concept_name
            concept_name = concept_class_name.split("Content")[0]
            try:
                return cls.make_stuff_using_concept_name_and_search_domains(
                    concept_name=concept_name,
                    search_domains=search_domains,
                    content=content,
                    name=name,
                    code=stuff_code,
                )
            except StuffFactoryError as exc:
                raise StuffFactoryError(f"Could not make stuff for StuffContent '{name}': {exc}") from exc
        elif isinstance(stuff_content_or_data, list):
            items = stuff_content_or_data
            if len(items) == 0:
                raise StuffFactoryError("List in compact memory has no items")
            first_item = items[0]
            concept_name = type(first_item).__name__
            content = ListContent[Any](items=items)
            try:
                return cls.make_stuff_using_concept_name_and_search_domains(
                    concept_name=concept_name,
                    search_domains=search_domains,
                    content=content,
                    name=name,
                    code=stuff_code,
                )
            except StuffFactoryError as exc:
                raise StuffFactoryError(f"Could not make stuff for list of StuffContent '{name}': {exc}") from exc
        elif isinstance(stuff_content_or_data, str):
            str_stuff: str = stuff_content_or_data
            return StuffFactory.make_stuff(
                concept=ConceptFactory.make_native_concept(native_concept_data=NATIVE_CONCEPTS_DATA[NativeConceptEnum.TEXT]),
                content=TextContent(text=str_stuff),
                name=name,
            )
        else:
            stuff_content_dict: Dict[str, Any] = stuff_content_or_data
            try:
                concept_code = stuff_content_dict.get("concept") or stuff_content_dict.get("concept_code")
                if not concept_code:
                    raise StuffFactoryError("Stuff content data dict is badly formed: no concept code")
                content_value = stuff_content_dict["content"]
                if ConceptBlueprint.is_native_concept_string_or_concept_code(concept_string_or_concept_code=concept_code):
                    concept = ConceptFactory.make_native_concept(native_concept_data=NATIVE_CONCEPTS_DATA[NativeConceptEnum(concept_code)])
                    content = StuffContentFactory.make_stuff_content_from_concept_with_fallback(
                        concept=concept,
                        value=content_value,
                    )
                    return StuffFactory.make_stuff(
                        concept=concept,
                        name=name,
                        content=content,
                        code=stuff_code,
                    )
            except KeyError as exc:
                raise StuffFactoryError(f"Stuff content data dict is badly formed: {exc}") from exc

            if isinstance(content_value, StuffContent):
                return StuffFactory.make_stuff(
                    concept=get_concept_provider().get_required_concept(concept_string=concept_code),
                    name=name,
                    content=content_value,
                    code=stuff_code,
                )
            else:
                content = StuffContentFactory.make_stuff_content_from_concept_with_fallback(
                    concept=get_concept_provider().get_required_concept(concept_string=concept_code),
                    value=content_value,
                )
                return StuffFactory.make_stuff(
                    concept=get_concept_provider().get_required_concept(concept_string=concept_code),
                    name=name,
                    content=content,
                    code=stuff_code,
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
    def make_stuff_content_from_concept_required(cls, concept: Concept, value: Dict[str, Any] | str) -> StuffContent:
        """
        Create StuffContent from concept code, requiring the concept to be linked to a class in the registry.
        Raises StuffContentFactoryError if no registry class is found.
        """
        the_subclass_name = concept.structure_class_name
        the_subclass = get_class_registry().get_required_subclass(name=the_subclass_name, base_class=StuffContent)
        return cls.make_content_from_value(stuff_content_subclass=the_subclass, value=value)

    @classmethod
    def make_stuff_content_from_concept_with_fallback(cls, concept: Concept, value: Dict[str, Any] | str) -> StuffContent:
        """
        Create StuffContent from concept code, falling back to TextContent if no registry class is found.
        """
        the_structure_class = get_class_registry().get_class(name=concept.structure_class_name)

        if the_structure_class is None:
            return cls.make_content_from_value(stuff_content_subclass=TextContent, value=value)

        if not issubclass(the_structure_class, StuffContent):
            raise StuffContentFactoryError(f"Concept '{concept.code}', subclass '{the_structure_class}' is not a subclass of StuffContent")

        return cls.make_content_from_value(stuff_content_subclass=the_structure_class, value=value)
