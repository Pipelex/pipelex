from typing import Any, Dict, Optional, Type, Union

from pydantic import ConfigDict
from typing_extensions import override

from pipelex import log
from pipelex.core.concept import Concept
from pipelex.core.stuff_artefact import StuffArtefact
from pipelex.core.stuff_content import (
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
from pipelex.exceptions import StuffError
from pipelex.tools.misc.string_utils import pascal_case_to_snake_case
from pipelex.tools.typing.pydantic_utils import CustomBaseModel


class Stuff(CustomBaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    stuff_code: str
    stuff_name: Optional[str] = None
    concept_code: str
    content: StuffContent

    def make_artefact(self) -> StuffArtefact:
        artefact_dict: Dict[str, Any] = self.content.model_dump(serialize_as_any=True)

        def set_artefact_field(key: str, value: Optional[Union[str, StuffContent]]):
            if value is None:
                return
            if key in artefact_dict:
                stuff_name = self.stuff_name or f"unnamed using concept code {self.concept_code}"
                raise StuffError(
                    f"""Cannot create stuff artefact for stuff {stuff_name} because reserved field {key} already exists in the stuff content.
                    Forbidden fields are: `stuff_name`, `content_class`, `concept_code`, `stuff_code`, `content`"""
                )
            artefact_dict[key] = value

        set_artefact_field("stuff_name", self.stuff_name)
        set_artefact_field("content_class", self.content.__class__.__name__)
        set_artefact_field("concept_code", self.concept_code)
        set_artefact_field("stuff_code", self.stuff_code)
        set_artefact_field("content", self.content)
        return StuffArtefact(artefact_dict)

    @classmethod
    def make_stuff_name(cls, concept_str: str) -> str:
        if Concept.concept_str_contains_domain(concept_str):
            return pascal_case_to_snake_case(Concept.extract_concept_name_from_str(concept_str=concept_str))
        else:
            log.error(f"Generating stuff name for Concept str '{concept_str}' which does not contain a domain")
            return pascal_case_to_snake_case(name=concept_str)

    @property
    def title(self) -> str:
        name_from_concept = Stuff.make_stuff_name(concept_str=self.concept_code)
        concept_display = Concept.sentence_from_concept_code(concept_code=self.concept_code)
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
{self.concept_code} — {type(self.content).__name__}:
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
        if not isinstance(self.content, content_type):
            raise TypeError(f"Content is of type '{type(self.content)}', instead of the expected '{content_type}'")
        return self.content

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
        for i, item in enumerate(list_content.items):
            if not isinstance(item, item_type):
                raise TypeError(f"Item {i} in list is of type {type(item)}, not {item_type}, in {self.stuff_name=} and {self.concept_code=}")

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
