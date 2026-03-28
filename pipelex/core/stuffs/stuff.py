# pyright: reportImportCycles=false
from typing import Any, cast, get_args, get_origin

from kajson import kajson
from mthds.models.stuff import DictStuffAbstract, StuffAbstract
from pydantic import ValidationError
from typing_extensions import override

from pipelex import log
from pipelex.core.concepts.concept import Concept
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.exceptions import StuffContentTypeError, StuffContentValidationError
from pipelex.core.stuffs.html_content import HtmlContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.mermaid_content import MermaidContent
from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.stuff_artefact import StuffArtefact
from pipelex.core.stuffs.stuff_content import StuffContent, StuffContentType
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.tools.misc.pretty import PrettyPrintable, PrettyRenderable
from pipelex.tools.misc.string_utils import pascal_case_to_snake_case
from pipelex.tools.typing.pydantic_utils import CustomBaseModel, format_pydantic_validation_error


class Stuff(PrettyRenderable, CustomBaseModel, StuffAbstract[Concept, StuffContent]):
    def make_artefact(self) -> StuffArtefact:
        """Create a Jinja2-compatible artefact from this Stuff.

        Returns:
            StuffArtefact that provides template access to content fields and metadata.
        """
        return StuffArtefact(stuff=self)

    @classmethod
    def make_stuff_name(cls, concept: Concept) -> str:
        return pascal_case_to_snake_case(name=concept.code)

    @property
    def title(self) -> str:
        name_from_concept = Stuff.make_stuff_name(concept=self.concept)
        concept_display = Concept.sentence_from_concept(concept=self.concept)
        if self.is_list:
            return f"List of [{concept_display}]"
        elif self.stuff_name:
            if self.stuff_name == name_from_concept:
                return concept_display
            else:
                return f"{self.stuff_name} (a {concept_display})"
        else:
            return concept_display

    @property
    def short_desc(self) -> str:
        return f"""{self.stuff_code}:
{self.concept.code} — {type(self.content).__name__}:
{self.content.short_desc}"""

    @property
    def header(self) -> str:
        """A descriptive header with stuff_code, stuff_name, and concept."""
        name_part = f" ({self.stuff_name})" if self.stuff_name else ""
        return f"Stuff[{self.stuff_code}{name_part}] <{self.concept.code}>"

    @override
    def __repr__(self) -> str:
        return f"{self.header}\n{kajson.dumps(self.content.smart_dump(), indent=4)}"

    @override
    def __str__(self) -> str:
        return f"{self.title}\n{kajson.dumps(self.content.smart_dump(), indent=4)}"

    @property
    def is_list(self) -> bool:
        return isinstance(self.content, ListContent)

    @property
    def is_image(self) -> bool:
        return isinstance(self.content, ImageContent)

    @property
    def is_document(self) -> bool:
        return isinstance(self.content, DocumentContent)

    @property
    def is_text(self) -> bool:
        return isinstance(self.content, TextContent)

    @property
    def is_number(self) -> bool:
        return isinstance(self.content, NumberContent)

    def content_as(self, content_type: type[StuffContentType]) -> StuffContentType:
        """Get content with proper typing if it's of the expected type."""
        return self.verify_content_type(self.content, content_type)

    @classmethod
    def verify_content_type(cls, content: StuffContent, content_type: type[StuffContentType]) -> StuffContentType:
        """Verify and convert content to the expected type."""
        # First try the direct isinstance check for performance
        if isinstance(content, content_type):
            return content

        # If isinstance failed, try model validation approach
        # This handles cases where the same class is loaded from different import paths,
        # or where a domain-qualified dynamic class (e.g., "domain__Invoice") matches
        # a pre-existing class with the bare name (e.g., "Invoice")
        try:
            actual_name = type(content).__name__
            expected_name = content_type.__name__
            # Check if class names match — exact match or domain-qualified match.
            # Domain-qualified names have the format "domain__ConceptCode", so we
            # extract the concept code (after the last "__") for comparison.
            # Only allow the fallback when at least one side is bare (no domain prefix)
            # to prevent silent cross-domain conversion between e.g. alpha__Result and beta__Result.
            actual_code = actual_name.rsplit("__", 1)[-1]
            expected_code = expected_name.rsplit("__", 1)[-1]
            at_least_one_bare = ("__" not in actual_name) or ("__" not in expected_name)
            names_match = (actual_name == expected_name) or (at_least_one_bare and actual_code == expected_code)
            if names_match:
                content_dict = content.smart_dump()
                validated_content = content_type.model_validate(content_dict)
                log.verbose(f"Model validation passed: converted {type(content).__name__} to {content_type.__name__}")
                return validated_content
        except ValidationError as exc:
            formatted_error = format_pydantic_validation_error(exc)
            raise StuffContentValidationError(
                original_type=type(content).__name__,
                target_type=content_type.__name__,
                validation_error=formatted_error,
            ) from exc

        actual_type = type(content)

        # Check if user is trying to use ListContent[Something] - suggest get_stuff_as_list() instead
        origin = get_origin(content_type)
        if origin is None:
            # For Pydantic generics, check __pydantic_generic_metadata__
            pydantic_metadata: dict[str, Any] | None = getattr(content_type, "__pydantic_generic_metadata__", None)
            if pydantic_metadata is not None:
                origin = pydantic_metadata.get("origin")

        if origin is not None and issubclass(origin, ListContent):
            # User passed ListContent[Something] - extract the item type and suggest the correct method
            type_args = get_args(content_type)
            if not type_args:
                pydantic_metadata = getattr(content_type, "__pydantic_generic_metadata__", None)
                if pydantic_metadata is not None:
                    type_args = pydantic_metadata.get("args", ())

            if type_args:
                item_type_name = type_args[0].__name__
                msg = (
                    f"Cannot use ListContent[{item_type_name}] with get_stuff_as() or content_as(). "
                    f'Use get_stuff_as_list("<name>", {item_type_name}) instead.'
                )
            else:
                msg = 'Cannot use ListContent[...] with get_stuff_as() or content_as(). Use get_stuff_as_list("<name>", ItemType) instead.'
            raise StuffContentTypeError(message=msg, expected_type=content_type.__name__, actual_type=actual_type.__name__)

        msg = f"Content is of type '{actual_type}', instead of the expected '{content_type}'"
        raise StuffContentTypeError(message=msg, expected_type=content_type.__name__, actual_type=actual_type.__name__)

    def as_list_content(self) -> ListContent:  # pyright: ignore[reportMissingTypeArgument, reportUnknownParameterType]
        """Get content as ListContent with items of any type."""
        return self.content_as(content_type=ListContent)  # pyright: ignore[reportUnknownVariableType]

    def as_list_of_fixed_content_type(self, item_type: type[StuffContentType]) -> ListContent[StuffContentType]:
        """Get content as ListContent with items of type T.

        Args:
            item_type: The expected type of items in the list.

        Returns:
            A typed ListContent[StuffContentType] with proper type information

        Raises:
            TypeError: If content is not ListContent or items don't match expected type

        """
        list_content = cast("ListContent[StuffContentType]", self.content_as(content_type=ListContent))

        converted_items: list[StuffContentType] = []
        for item in list_content.items:
            converted_item = self.verify_content_type(item, item_type)
            converted_items.append(converted_item)

        return ListContent[StuffContentType](items=converted_items)

    @property
    def as_text(self) -> TextContent:
        """Get content as TextContent if applicable."""
        return self.content_as(content_type=TextContent)

    @property
    def as_str(self) -> str:
        """Get content as string if applicable."""
        return self.as_text.text

    @property
    def as_image(self) -> ImageContent:
        """Get content as ImageContent if applicable."""
        return self.content_as(content_type=ImageContent)

    @property
    def as_document(self) -> DocumentContent:
        """Get content as DocumentContent if applicable."""
        return self.content_as(content_type=DocumentContent)

    @property
    def as_text_and_image(self) -> TextAndImagesContent:
        """Get content as TextAndImageContent if applicable."""
        return self.content_as(content_type=TextAndImagesContent)

    @property
    def as_number(self) -> NumberContent:
        """Get content as NumberContent if applicable."""
        return self.content_as(content_type=NumberContent)

    @property
    def as_html(self) -> HtmlContent:
        """Get content as HtmlContent if applicable."""
        return self.content_as(content_type=HtmlContent)

    @property
    def as_mermaid(self) -> MermaidContent:
        """Get content as MermaidContent if applicable."""
        return self.content_as(MermaidContent)

    @override
    def rendered_pretty(self, title: str | None = None, depth: int = 0) -> PrettyPrintable:
        """Render stuff for pretty printing.

        Args:
            title: Optional title for the rendering
            depth: Current nesting depth, used to prevent nesting too many sub-tables which would end up too narrow in the console
        """
        if title and self.stuff_name:
            title = f"[cyan]{title}:[/cyan] — {self.stuff_name} ([bold green]{self.concept.code}[/bold green]"
        elif self.stuff_name:
            title = f"[cyan]{self.stuff_name}[/cyan] ([bold green]{self.concept.code}[/bold green])"
        elif title:
            title = f"[cyan]{title}:[/cyan] some stuff ([bold green]{self.concept.code}[/bold green])"
        else:
            title = f"Some stuff ([bold green]{self.concept.code}[/bold green])"
        return self.content.rendered_pretty(title=title, depth=depth)

    def pretty_print_stuff(self, title: str | None = None) -> None:
        title = title or f"[cyan]{self.stuff_name}[/cyan] ([bold green]{self.concept.code}[/bold green])"
        self.content.pretty_print_content(title=title)


class DictStuff(CustomBaseModel, DictStuffAbstract):
    """Stuff with content as dict[str, Any] instead of StuffContent.

    This is used for serialization where the content needs to be a plain dict.
    Has the exact same structure as Stuff but with dict content.
    """
