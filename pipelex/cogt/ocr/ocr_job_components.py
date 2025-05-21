# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Optional

from pydantic import BaseModel

from pipelex.tools.config.models import ConfigModel


class OcrJobParams(BaseModel):
    should_include_images: bool
    should_caption_images: bool
    should_include_screenshots: bool
    screenshots_dpi: int

    @classmethod
    def make_default_ocr_job_params(cls) -> "OcrJobParams":
        return OcrJobParams(
            should_caption_images=False,
            should_include_screenshots=False,
            should_include_images=True,
            screenshots_dpi=300,
        )


class OcrJobConfig(ConfigModel):
    pass


########################################################################
### Outputs
########################################################################


class OcrJobReport(ConfigModel):
    pass
