from typing import Any, cast

import shortuuid
from pydantic import BaseModel, ValidationError, field_validator

from pipelex.client.protocol import StuffContentOrData
from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_library import ConceptLibraryConceptNotFoundError
from pipelex.core.concepts.concept_native import NativeConceptCode
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.stuff import DictStuff, Stuff
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
    def make_stuff_from_stuff_content_or_data(
        cls,
        stuff_content_or_data: StuffContentOrData,
        name: str | None = None,
        code: str | None = None,
        search_domains: list[str] | None = None,
    ) -> Stuff:
        """Create a Stuff from StuffContentOrData covering all pipeline inputs cases.

        Case 1: Direct content (no 'concept' key)
            1.1: str → TextContent with Text concept
            1.2: list[str] → ListContent[TextContent] with Text concept
            1.3: StructuredContent → Use the StructuredContent, infer concept from class name
            1.4: list[StuffContent] → ListContent[StuffContent], infer concept from first item
            1.5: ListContent[StuffContent] → Use the ListContent, infer concept from first item

        Note: StructuredContent (1.3) and ListContent (1.5) are separate cases at the same level.
              Both inherit from StuffContent but handle different content types.

        Case 2: Dict with 'concept' AND 'content' keys (can be plain dict or DictStuff instance)
            2.1/2.1b: {"concept": "Text"/"native.Text", "content": str} → TextContent with Text concept
            2.1c: {"concept": "domain.Concept", "content": str} → TextContent with that concept (if compatible)
            2.2/2.2b: {"concept": "...", "content": list[str]} → ListContent[TextContent]
            2.3: {"concept": "...", "content": StuffContent} → Use the StuffContent
            2.4: {"concept": "...", "content": list[StuffContent]} → ListContent[StuffContent]
            2.5: {"concept": "...", "content": dict} → Create StuffContent from dict
            2.6: {"concept": "...", "content": list[dict]} → ListContent[StuffContent] from dicts
        """
        concept_library = get_concept_library()

        # ==================== CASE 1: Direct content (no concept key) ====================
        if not isinstance(stuff_content_or_data, dict):
            # Case 1.1: str → TextContent with Text concept
            if isinstance(stuff_content_or_data, str):
                return cls.make_stuff(
                    concept=get_native_concept(native_concept=NativeConceptCode.TEXT),
                    content=TextContent(text=stuff_content_or_data),
                    name=name,
                    code=code,
                )

            # Case 1.5: ListContent[StuffContent] → Use the ListContent, infer concept from first item
            # Must check BEFORE Case 1.3 because ListContent is also a StuffContent
            if isinstance(stuff_content_or_data, ListContent):
                list_content = cast("ListContent[StuffContent]", stuff_content_or_data)

                if len(list_content.items) == 0:
                    msg = f"Cannot create Stuff '{name}' from empty ListContent"
                    raise StuffFactoryError(msg)

                first_item = list_content.items[0]

                # Check that items are StuffContent
                if not isinstance(first_item, StuffContent):  # pyright: ignore[reportUnnecessaryIsInstance]
                    msg = (
                        f"Trying to create a Stuff '{name}' from a ListContent but "
                        f"the items are not StuffContent. First item is of type {type(first_item).__name__}. "
                        "ListContent items must be subclasses of StuffContent."
                    )
                    raise StuffFactoryError(msg)

                # Check all items are of the same type
                for item in list_content.items:
                    if not isinstance(item, type(first_item)):
                        msg = (
                            f"Trying to create a Stuff '{name}' from a ListContent of '{type(first_item).__name__}' "
                            f"but the items are not of the same type. Especially, items {item} is of type {type(item).__name__}. "
                            "Every items of the list should be an identical type."
                        )
                        raise StuffFactoryError(msg)

                # Get concept from first item's class name
                content_class_name = type(first_item).__name__

                # Check if it's a native concept
                if "Content" in content_class_name and NativeConceptCode.is_native_concept(concept_code=content_class_name.split("Content")[0]):
                    concept = get_native_concept(native_concept=NativeConceptCode(content_class_name.split("Content")[0]))
                else:
                    try:
                        concept = concept_library.get_required_concept_from_concept_string_or_code(
                            concept_string_or_code=content_class_name, search_domains=search_domains
                        )
                    except ConceptLibraryConceptNotFoundError as exc:
                        msg = (
                            f"Trying to create a Stuff '{name}' from a ListContent but "
                            f"the concept of name '{content_class_name}' is not found in the library"
                        )
                        raise StuffFactoryError(msg) from exc

                return cls.make_stuff(
                    concept=concept,
                    content=list_content,
                    name=name,
                    code=code,
                )

            # Case 1.3: StuffContent object (includes both native and StructuredContent) → Infer concept from class name
            if isinstance(stuff_content_or_data, StuffContent):
                stuff_content = stuff_content_or_data
                content_class_name = stuff_content_or_data.__class__.__name__

                # Check if it's a native concept
                if "Content" in content_class_name and NativeConceptCode.is_native_concept(concept_code=content_class_name.split("Content")[0]):
                    # It's a native concept like TextContent, ImageContent, etc.
                    concept = get_native_concept(native_concept=NativeConceptCode(content_class_name.split("Content")[0]))
                else:
                    # It's a StructuredContent, try to find the concept
                    try:
                        concept = concept_library.get_required_concept_from_concept_string_or_code(
                            concept_string_or_code=content_class_name, search_domains=search_domains
                        )
                    except ConceptLibraryConceptNotFoundError as exc:
                        msg = (
                            f"Trying to create a Stuff '{name}' from a StuffContent '{content_class_name}' "
                            f"but the concept of name '{content_class_name}' is not found in the library"
                        )
                        raise StuffFactoryError(msg) from exc

                return cls.make_stuff(
                    concept=concept,
                    content=stuff_content,
                    name=name,
                    code=code,
                )

            # Case 1.2 or 1.4: list → ListContent
            if isinstance(stuff_content_or_data, list):
                if len(stuff_content_or_data) == 0:
                    msg = f"Cannot create Stuff '{name}' from empty list"
                    raise StuffFactoryError(msg)

                first_item = stuff_content_or_data[0]

                # Case 1.2: list[str] → ListContent[TextContent] with Text concept
                if isinstance(first_item, str):
                    for item in stuff_content_or_data:
                        if not isinstance(item, str):
                            msg = (
                                f"Trying to create a Stuff '{name}' from a list of strings but the item {item} is not a string. "
                                "Every items of the list should be a identical type. If its a string, everything should be a string."
                            )
                            raise StuffFactoryError(msg)

                    items = [TextContent(text=item) for item in cast("list[str]", stuff_content_or_data)]
                    return cls.make_stuff(
                        concept=get_native_concept(native_concept=NativeConceptCode.TEXT),
                        content=ListContent(items=items),
                        name=name,
                        code=code,
                    )

                # Case 1.4: list[StuffContent] → ListContent[StuffContent]
                elif isinstance(first_item, StuffContent):  # pyright: ignore[reportUnnecessaryIsInstance]
                    # Get the concept from the first item's class name
                    content_class_name = type(first_item).__name__

                    # Check all items are of the same type
                    for item in stuff_content_or_data:
                        if not isinstance(item, type(first_item)):
                            msg = (
                                f"Trying to create a Stuff '{name}' from a list of '{type(first_item).__name__}' "
                                f"but the items are not of the same type. Especially, items {item} is of type {type(item).__name__}. "
                                "Every items of the list should be a identical type. If its a string, everything should be a string."
                            )
                            raise StuffFactoryError(msg)

                    # Check if it's a native concept
                    if "Content" in content_class_name and NativeConceptCode.is_native_concept(concept_code=content_class_name.split("Content")[0]):
                        concept = get_native_concept(native_concept=NativeConceptCode(content_class_name.split("Content")[0]))
                    else:
                        try:
                            concept = concept_library.get_required_concept_from_concept_string_or_code(
                                concept_string_or_code=content_class_name, search_domains=search_domains
                            )
                        except ConceptLibraryConceptNotFoundError as exc:
                            msg = (
                                f"Trying to create a Stuff '{name}' from a list of StuffContent but "
                                f"the concept of name '{content_class_name}' is not found in the library"
                            )
                            raise StuffFactoryError(msg) from exc

                    return cls.make_stuff(
                        concept=concept,
                        content=ListContent(items=cast("list[StuffContent]", stuff_content_or_data)),
                        name=name,
                        code=code,
                    )
                else:
                    msg = f"Cannot create Stuff from list of {type(first_item)}. Type should be {StuffContentOrData}."
                    raise StuffFactoryError(msg)

        # ==================== CASE 2: Dict with 'concept' AND 'content' keys ====================
        # Convert DictStuff instance to plain dict if needed
        if isinstance(stuff_content_or_data, DictStuff):
            stuff_content_or_data = stuff_content_or_data.model_dump()

        if not isinstance(stuff_content_or_data, dict):
            msg = f"Unexpected type for stuff_content_or_data: {type(stuff_content_or_data)}.Type should be {StuffContentOrData}."
            raise StuffFactoryError(msg)

        # Check if it's a dict with concept and content keys
        if "concept" not in stuff_content_or_data:
            msg = f"Trying to create a Stuff '{name}' from a dict that should represent a StuffContentOrData but does not have a 'concept' key."
            raise StuffFactoryError(msg)

        if "content" not in stuff_content_or_data:
            msg = f"Trying to create a Stuff '{name}' from a dict that should represent a StuffContentOrData but does not have a 'content' key."
            raise StuffFactoryError(msg)

        # All Case 2 variants - dict with concept and content
        if len(stuff_content_or_data) != 2:
            msg = (
                f"Trying to create a Stuff '{name}' from a dict that should represent a StuffContentOrData but does not have "
                "exactly keys 'concept' and 'content'."
            )
            raise StuffFactoryError(msg)

        concept_string = stuff_content_or_data["concept"]
        content = stuff_content_or_data["content"]

        # Get the concept from the library
        try:
            concept = concept_library.get_required_concept_from_concept_string_or_code(
                concept_string_or_code=concept_string, search_domains=search_domains
            )
        except ConceptLibraryConceptNotFoundError as exc:
            msg = (
                f"Trying to create a Stuff '{name}' in the inputs of your pipe, from a dict that should represent a StuffContentOrData "
                f"but the concept of name '{concept_string}' is not found in the library"
            )
            raise StuffFactoryError(msg) from exc

        # Case 2.1: content is a string
        if isinstance(content, str):
            # Check if concept is strictly compatible with Text (refinement = strict compatibility)
            text_concept = get_native_concept(native_concept=NativeConceptCode.TEXT)
            if concept_library.is_compatible(tested_concept=concept, wanted_concept=text_concept, strict=True):
                return cls.make_stuff(
                    concept=concept,
                    content=TextContent(text=content),
                    name=name,
                    code=code,
                )
            msg = (
                f"Trying to create a Stuff '{name}' in the inputs of your pipe, from a dict that should represent a StuffContentOrData "
                f"but the concept of name '{concept_string}' is not compatible with native concept 'native.Text'"
            )
            raise StuffFactoryError(msg)

        # Case 2.3: content is a StructuredContent object
        if isinstance(content, StructuredContent):
            if concept.structure_class_name != content.__class__.__name__:
                msg = (
                    f"Trying to create a Stuff '{name}' in the inputs of your pipe, from a dict that should represent a StuffContentOrData "
                    f"but the concept of name '{concept_string}' is not compatible with the content of type {content.__class__.__name__}"
                )
                raise StuffFactoryError(msg)

            return cls.make_stuff(
                concept=concept,
                content=content,
                name=name,
                code=code,
            )

        # Case 2.5: content is a dict
        if isinstance(content, dict):
            the_class = get_class_registry().get_class(name=concept.structure_class_name)
            if the_class is None:
                msg = (
                    f"Trying to create a Stuff '{name}' in the inputs of your pipe, from a dict that should represent a StuffContentOrData "
                    f"but the concept of name '{concept_string}' is not compatible with a dict content"
                )
                raise StuffFactoryError(msg)

            return cls.make_stuff(
                name=name,
                code=code,
                concept=concept,
                content=the_class.model_validate(obj=content),
            )

        # Case 2.2/2.2b/2.4/2.5/2.6: content is a list
        if isinstance(content, list):
            list_content_2 = cast("list[Any]", content)
            if len(list_content_2) == 0:
                msg = "Cannot create Stuff from empty list in content"
                raise StuffFactoryError(msg)

            first_item = list_content_2[0]

            # Case 2.2/2.2b: list[str]
            if isinstance(first_item, str):
                for item in list_content_2:
                    if not isinstance(item, str):
                        msg = (
                            f"Trying to create a Stuff '{name}' in the inputs of your pipe, from a list of strings but the item {item} "
                            "is not a string. Every items of the list should be a identical type. If its a string, everything should be a string."
                        )
                        raise StuffFactoryError(msg)

                text_concept = get_native_concept(native_concept=NativeConceptCode.TEXT)
                if concept_library.is_compatible(tested_concept=concept, wanted_concept=text_concept, strict=True):
                    items = [TextContent(text=item) for item in list_content_2]
                    return cls.make_stuff(
                        concept=concept,
                        content=ListContent(items=items),
                        name=name,
                        code=code,
                    )

                msg = f"Concept '{concept_string}' is not compatible with list of text content"
                raise StuffFactoryError(msg)

            # Case 2.4: list[StructuredContent]
            if isinstance(first_item, StructuredContent):
                for item in list_content_2:
                    if not isinstance(item, type(first_item)):
                        msg = (
                            f"Trying to create a Stuff '{name}' in the inputs of your pipe, from a list of StructuredContent "
                            "but the items are not of the same type. Every items of the list should be a identical type. "
                            f"If its a '{type(first_item).__name__}', everything should be a '{type(first_item).__name__}'."
                        )
                        raise StuffFactoryError(msg)

                return cls.make_stuff(
                    concept=concept,
                    content=ListContent(items=cast("list[StructuredContent]", list_content_2)),
                    name=name,
                    code=code,
                )

            # Case 2.6: list[dict]
            if isinstance(first_item, dict):
                for item_dict in list_content_2:
                    if not isinstance(item_dict, dict):
                        msg = (
                            f"Trying to create a Stuff '{name}' in the inputs of your pipe, from a list of dicts but "
                            f"the item {item_dict} is not a dict. Every items of the list should be a identical type. "
                            "If its a dict, everything should be a dict."
                        )
                        raise StuffFactoryError(msg)

                # Create StuffContent objects from dicts
                stuff_items: list[StuffContent] = []
                for item_dict in list_content_2:
                    stuff_content = StuffContentFactory.make_stuff_content_from_concept_with_fallback(
                        concept=concept,
                        value=item_dict,
                    )
                    stuff_items.append(stuff_content)

                return cls.make_stuff(
                    concept=concept,
                    content=ListContent(items=stuff_items),
                    name=name,
                    code=code,
                )

            msg = f"Cannot create Stuff from list of {type(first_item)} in content"
            raise StuffFactoryError(msg)

        msg = f"Unexpected type for content value: {type(content)}"
        raise StuffFactoryError(msg)


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
