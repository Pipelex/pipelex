from typing import Any, cast

import shortuuid
from pydantic import BaseModel, ValidationError, field_validator

from pipelex.client.protocol import StuffContentOrData
from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_native import NativeConceptCode
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.exceptions import PipelexException
from pipelex.hub import get_class_registry, get_concept_library, get_native_concept, get_required_concept
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error


class StuffFactoryError(PipelexException):
    pass


class StuffBlueprint(BaseModel):
    stuff_name: str
    concept_string: str
    content: dict[str, Any] | str

    @field_validator("concept_string")
    @classmethod
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
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
            content=TextContent(text=str_value),
            name=name,
        )

    @classmethod
    def make_from_concept_string(cls, concept_string: str, name: str, content: StuffContent) -> Stuff:
        ConceptBlueprint.validate_concept_string(concept_string)
        concept = get_required_concept(concept_string=concept_string)
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
        name: str | None = None,
        code: str | None = None,
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
    def make_from_blueprint(cls, blueprint: StuffBlueprint) -> "Stuff":
        concept_library = get_concept_library()
        if isinstance(blueprint.content, str) and concept_library.is_compatible(
            tested_concept=concept_library.get_required_concept(concept_string=blueprint.concept_string),
            wanted_concept=get_native_concept(native_concept=NativeConceptCode.TEXT),
        ):
            the_stuff = cls.make_stuff(
                concept=get_native_concept(native_concept=NativeConceptCode.TEXT),
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
        stuff_contents: dict[str, StuffContent],
        name: str | None = None,
    ) -> Stuff:
        # TODO: Add unit tests for this method
        """Combine a dictionary of stuffs into a single stuff."""
        the_subclass = get_class_registry().get_required_subclass(name=concept.structure_class_name, base_class=StuffContent)
        try:
            the_stuff_content = the_subclass.model_validate(obj=stuff_contents)
        except ValidationError as exc:
            msg = f"Error combining stuffs for concept {concept.code}, stuff named `{name}`: {format_pydantic_validation_error(exc=exc)}"
            raise StuffFactoryError(msg) from exc
        return cls.make_stuff(
            concept=concept,
            content=the_stuff_content,
            name=name,
        )

    @classmethod
    def make_stuff_using_concept_name_and_search_domains(
        cls,
        concept_name: str,
        search_domains: list[str],
        content: StuffContent,
        name: str | None = None,
        code: str | None = None,
    ) -> Stuff:
        # TODO: Add unit tests for this method
        concept_library = get_concept_library()
        concept = concept_library.search_for_concept_in_domains(
            concept_code=concept_name,
            search_domains=search_domains,
        )
        if not concept:
            msg = f"Could not find a concept named '{concept_name}' in domains {search_domains}"
            raise StuffFactoryError(msg)
        return cls.make_stuff(concept=concept, content=content, name=name, code=code)

    @classmethod
    def make_stuff_from_stuff_content_using_search_domains(
        cls,
        name: str,
        stuff_content_or_data: StuffContentOrData,
        search_domains: list[str],
        stuff_code: str | None = None,
    ) -> Stuff:
        # TODO: Add unit tests for this method
        content: StuffContent
        concept_name: str
        if isinstance(stuff_content_or_data, ListContent):
            content = cast("ListContent[Any]", stuff_content_or_data)
            if len(content.items) == 0:
                msg = "ListContent in compact memory has no items"
                raise StuffFactoryError(msg)
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
                msg = f"Could not make stuff for ListContent '{name}': {exc}"
                raise StuffFactoryError(msg) from exc
        elif isinstance(stuff_content_or_data, StuffContent):
            content = stuff_content_or_data
            concept_class_name = type(content).__name__
            native_concept_class_names = NativeConceptCode.native_concept_class_names()

            if concept_class_name in native_concept_class_names:
                concept = get_native_concept(native_concept=NativeConceptCode(concept_class_name.split("Content")[0]))
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
                msg = f"Could not make stuff for StuffContent '{name}': {exc}"
                raise StuffFactoryError(msg) from exc
        elif isinstance(stuff_content_or_data, list):
            items = stuff_content_or_data
            if len(items) == 0:
                msg = "List in compact memory has no items"
                raise StuffFactoryError(msg)
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
                msg = f"Could not make stuff for list of StuffContent '{name}': {exc}"
                raise StuffFactoryError(msg) from exc
        elif isinstance(stuff_content_or_data, str):
            str_stuff: str = stuff_content_or_data
            return StuffFactory.make_stuff(
                concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
                content=TextContent(text=str_stuff),
                name=name,
            )
        else:
            stuff_content_dict: dict[str, Any] = stuff_content_or_data
            try:
                concept_code = stuff_content_dict.get("concept") or stuff_content_dict.get("concept_code")
                if not concept_code:
                    msg = "Stuff content data dict is badly formed: no concept code"
                    raise StuffFactoryError(msg)
                content_value = stuff_content_dict["content"]
                if NativeConceptCode.get_validated_native_concept_string(concept_string_or_code=concept_code):
                    concept = ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode(concept_code))
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
                msg = f"Stuff content data dict is badly formed: {exc}"
                raise StuffFactoryError(msg) from exc

            concept_library = get_concept_library()
            concept = concept_library.get_required_concept(concept_string=concept_code)

            if isinstance(content_value, StuffContent):
                return StuffFactory.make_stuff(
                    concept=concept,
                    name=name,
                    content=content_value,
                    code=stuff_code,
                )
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


class StuffContentFactoryError(PipelexException):
    pass


class StuffContentFactory:
    @classmethod
    def make_content_from_value(cls, stuff_content_subclass: type[StuffContent], value: dict[str, Any] | str) -> StuffContent:
        if isinstance(value, str) and stuff_content_subclass == TextContent:
            return TextContent(text=value)
        return stuff_content_subclass.model_validate(obj=value)

    @classmethod
    def make_stuff_content_from_concept_required(cls, concept: Concept, value: dict[str, Any] | str) -> StuffContent:
        """Create StuffContent from concept code, requiring the concept to be linked to a class in the registry.
        Raises StuffContentFactoryError if no registry class is found.
        """
        the_subclass_name = concept.structure_class_name
        the_subclass = get_class_registry().get_required_subclass(name=the_subclass_name, base_class=StuffContent)
        return cls.make_content_from_value(stuff_content_subclass=the_subclass, value=value)

    @classmethod
    def make_stuff_content_from_concept_with_fallback(cls, concept: Concept, value: dict[str, Any] | str) -> StuffContent:
        """Create StuffContent from concept code, falling back to TextContent if no registry class is found."""
        the_structure_class = get_class_registry().get_class(name=concept.structure_class_name)

        if the_structure_class is None:
            return cls.make_content_from_value(stuff_content_subclass=TextContent, value=value)

        if not issubclass(the_structure_class, StuffContent):
            msg = f"Concept '{concept.code}', subclass '{the_structure_class}' is not a subclass of StuffContent"
            raise StuffContentFactoryError(msg)

        return cls.make_content_from_value(stuff_content_subclass=the_structure_class, value=value)
