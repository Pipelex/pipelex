# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Dict, List, Optional

from pydantic import BaseModel


class ExtractedImage(BaseModel):
    image_id: str
    base_64: Optional[str] = None
    caption: Optional[str] = None


class ExtractedImageFromPage(ExtractedImage):
    top_left_x: Optional[int] = None
    top_left_y: Optional[int] = None
    bottom_right_x: Optional[int] = None
    bottom_right_y: Optional[int] = None


class Page(BaseModel):
    text: Optional[str] = None
    extracted_images: List[ExtractedImageFromPage] = []
    screenshot: Optional[ExtractedImageFromPage] = None


class OcrOutput(BaseModel):
    pages: Dict[int, Page]

    @property
    def concatenated_text(self) -> str:
        return "\n".join([page.text for page in self.pages.values() if page.text])
