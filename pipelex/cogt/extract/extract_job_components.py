from pydantic import BaseModel

from pipelex.system.configuration.config_model import ConfigModel


class ExtractJobParams(BaseModel):
    """Parameters for extraction jobs.

    Attributes:
        max_nb_images: Maximum number of images to extract from pages.
            - None: Extract all images (unlimited)
            - 0: Extract no images
            - Positive int: Limit to N images
        image_min_size: Minimum size in pixels for extracted images.
        should_caption_images: Whether to generate captions for images.
        should_include_page_views: Whether to include rendered page views.
        page_views_dpi: DPI for rendered page views.
    """

    max_nb_images: int | None
    image_min_size: int | None
    should_caption_images: bool
    should_include_page_views: bool
    page_views_dpi: int | None

    @classmethod
    def make_default_extract_job_params(cls) -> "ExtractJobParams":
        return ExtractJobParams(
            should_caption_images=False,
            max_nb_images=None,
            image_min_size=None,
            should_include_page_views=False,
            page_views_dpi=None,
        )


class ExtractJobConfig(ConfigModel):
    pass


########################################################################
# Outputs
########################################################################


class ExtractJobReport(ConfigModel):
    pass
