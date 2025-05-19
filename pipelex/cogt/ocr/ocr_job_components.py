from pydantic import BaseModel

from pipelex.tools.config.models import ConfigModel


class OcrJobParams(BaseModel):
    should_caption_images: bool
    should_add_screenshots: bool
    screenshots_dpi: int

    @classmethod
    def make_default_ocr_job_params(cls) -> "OcrJobParams":
        return OcrJobParams(
            should_caption_images=False,
            should_add_screenshots=False,
            screenshots_dpi=300,
        )


class OcrJobConfig(ConfigModel):
    pass


########################################################################
### Outputs
########################################################################


class OcrJobReport(ConfigModel):
    pass
