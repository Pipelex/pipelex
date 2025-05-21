# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Dict, List, Optional

from pipelex.tools.misc.custom_base import TruncatableBase64BaseModel  # Import the new base model


class ExtractedImage(TruncatableBase64BaseModel):  # Inherit from the new base model
    image_id: str
    base_64: Optional[str] = None
    caption: Optional[str] = None


class ExtractedImageFromPage(ExtractedImage):
    top_left_x: Optional[int] = None
    top_left_y: Optional[int] = None
    bottom_right_x: Optional[int] = None
    bottom_right_y: Optional[int] = None


class Page(TruncatableBase64BaseModel):  # Inherit from the new base model for consistency if it might have base64 fields in future
    text: Optional[str] = None
    extracted_images: List[ExtractedImageFromPage] = []
    screenshot: Optional[ExtractedImageFromPage] = None


class OcrOutput(TruncatableBase64BaseModel):  # Inherit from the new base model for consistency
    pages: Dict[int, Page]

    @property
    def concatenated_text(self) -> str:
        return "\n".join([page.text for page in self.pages.values() if page.text])
