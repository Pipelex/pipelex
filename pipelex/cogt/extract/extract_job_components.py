from pydantic import BaseModel

from pipelex.system.configuration.config_model import ConfigModel


class ExtractJobParams(BaseModel):
    should_include_images: bool
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
            should_include_images=True,
            page_views_dpi=None,
        )


class ExtractJobConfig(ConfigModel):
    pass


########################################################################
### Outputs
########################################################################


class ExtractJobReport(ConfigModel):
    pass
