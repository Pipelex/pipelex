# pyright: reportImportCycles=false
from typing import Any, cast

from kajson import kajson
from pydantic import ConfigDict, ValidationError
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


class Stuff(PrettyRenderable, CustomBaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    stuff_code: str
    stuff_name: str | None = None
    concept: Concept
    content: StuffContent

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
        try:
            # Check if class names match (quick filter before attempting validation)
            if type(content).__name__ == content_type.__name__:
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


class DictStuff(CustomBaseModel):
    """Stuff with content as dict[str, Any] instead of StuffContent.

    This is used for serialization where the content needs to be a plain dict.
    Has the exact same structure as Stuff but with dict content.
    """

    model_config = ConfigDict(extra="forbid", strict=True)
    concept: str
    content: Any
