from typing import Any, Dict, Optional, Type, Union

from pydantic import ConfigDict, ValidationError
from typing_extensions import override

from pipelex import log
from pipelex.core.concepts.concept import Concept
from pipelex.core.stuffs.stuff_artefact import StuffArtefact
from pipelex.core.stuffs.stuff_content import (
    HtmlContent,
    ImageContent,
    ListContent,
    MermaidContent,
    NumberContent,
    PDFContent,
    StuffContent,
    StuffContentType,
    TextAndImagesContent,
    TextContent,
)
from pipelex.exceptions import StuffContentValidationError, StuffError
from pipelex.tools.misc.string_utils import pascal_case_to_snake_case
from pipelex.tools.typing.pydantic_utils import CustomBaseModel, format_pydantic_validation_error


class Stuff(CustomBaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    stuff_code: str
    stuff_name: Optional[str] = None
    concept: Concept
    content: StuffContent

    def make_artefact(self) -> StuffArtefact:
        artefact_dict: Dict[str, Any] = self.content.model_dump(serialize_as_any=True)

        def set_artefact_field(key: str, value: Optional[Union[str, StuffContent]]):
            if value is None:
                return
            if key in artefact_dict:
                stuff_name = self.stuff_name or f"unnamed using concept code {self.concept.code}"
                raise StuffError(
                    f"""Cannot create stuff artefact for stuff '{stuff_name}' of concept '{self.concept.code}' because reserved field '{key}' 
in the structured output '{self.content.__class__.__name__}' already exists in the stuff content.
Forbidden fields are: 'stuff_name', 'content_class', 'concept_code', 'stuff_code', 'content'."""
                )
            artefact_dict[key] = value

        set_artefact_field("stuff_name", self.stuff_name)
        set_artefact_field("content_class", self.content.__class__.__name__)
        set_artefact_field("concept_code", self.concept.code)
        set_artefact_field("stuff_code", self.stuff_code)
        set_artefact_field("content", self.content)
        return StuffArtefact(artefact_dict)

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
        return f"{self.title}\n{self.content.rendered_json()}"

    @property
    def is_list(self) -> bool:
        return isinstance(self.content, ListContent)

    @property
    def is_image(self) -> bool:
        return isinstance(self.content, ImageContent)

    @property
    def is_pdf(self) -> bool:
        return isinstance(self.content, PDFContent)

    @property
    def is_text(self) -> bool:
        return isinstance(self.content, TextContent)

    @property
    def is_number(self) -> bool:
        return isinstance(self.content, NumberContent)

    def content_as(self, content_type: Type[StuffContentType]) -> StuffContentType:
        """Get content with proper typing if it's of the expected type."""
        return self.verify_content_type(self.content, content_type)

    @classmethod
    def verify_content_type(cls, content: StuffContent, content_type: Type[StuffContentType]) -> StuffContentType:
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
                log.debug(f"Model validation passed: converted {type(content).__name__} to {content_type.__name__}")
                return validated_content
        except ValidationError as exc:
            formatted_error = format_pydantic_validation_error(exc)
            raise StuffContentValidationError(
                original_type=type(content).__name__, target_type=content_type.__name__, validation_error=formatted_error
            ) from exc

        raise TypeError(f"Content is of type '{type(content)}', instead of the expected '{content_type}'")

    def as_list_content(self) -> ListContent:  # pyright: ignore[reportMissingTypeArgument, reportUnknownParameterType]
        """Get content as ListContent with items of any type."""
        return self.content_as(content_type=ListContent)  # pyright: ignore[reportUnknownVariableType]

    def as_list_of_fixed_content_type(self, item_type: Type[StuffContentType]) -> ListContent[StuffContentType]:
        """
        Get content as ListContent with items of type T.

        Args:
            item_type: The expected type of items in the list.

        Returns:
            A typed ListContent[StuffContentType] with proper type information

        Raises:
            TypeError: If content is not ListContent or items don't match expected type
        """
        list_content: ListContent[StuffContentType] = self.content_as(content_type=ListContent)

        # Validate all items are of the expected type
        for item in list_content.items:
            self.verify_content_type(item, item_type)

        return list_content

    @property
    def as_text(self) -> TextContent:
        """Get content as TextContent if applicable."""
        return self.content_as(TextContent)

    @property
    def as_str(self) -> str:
        """Get content as string if applicable."""
        return self.as_text.text

    @property
    def as_image(self) -> ImageContent:
        """Get content as ImageContent if applicable."""
        return self.content_as(ImageContent)

    @property
    def as_pdf(self) -> PDFContent:
        """Get content as PDFContent if applicable."""
        return self.content_as(PDFContent)

    @property
    def as_text_and_image(self) -> TextAndImagesContent:
        """Get content as TextAndImageContent if applicable."""
        return self.content_as(TextAndImagesContent)

    @property
    def as_number(self) -> NumberContent:
        """Get content as NumberContent if applicable."""
        return self.content_as(NumberContent)

    @property
    def as_html(self) -> HtmlContent:
        """Get content as HtmlContent if applicable."""
        return self.content_as(HtmlContent)

    @property
    def as_mermaid(self) -> MermaidContent:
        """Get content as MermaidContent if applicable."""
        return self.content_as(MermaidContent)
