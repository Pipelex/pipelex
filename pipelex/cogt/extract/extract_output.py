from pydantic import Field

from pipelex.cogt.extract.bounding_box import BoundingBox
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails
from pipelex.tools.typing.pydantic_utils import CustomBaseModel, empty_list_factory_of


class ExtractedImageFromPage(GeneratedImageRawDetails):
    bounding_box: BoundingBox | None = None


class Page(CustomBaseModel):
    text: str | None = None
    extracted_images: list[ExtractedImageFromPage] = Field(default_factory=empty_list_factory_of(ExtractedImageFromPage))


class ExtractOutput(CustomBaseModel):
    pages: dict[int, Page]

    @property
    def concatenated_text(self) -> str:
        return "\n".join([page.text for page in self.pages.values() if page.text])
