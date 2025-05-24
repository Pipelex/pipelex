# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Dict, List, Optional

from pydantic import Field

from pipelex import log
from pipelex.tools.misc.base_64 import save_base64_to_binary_file
from pipelex.tools.misc.custom_base_model import CustomBaseModel
from pipelex.tools.utils.file_utils import ensure_directory_exists, save_text_to_path


class ExtractedImage(CustomBaseModel):
    image_id: str
    base_64: Optional[str] = None
    caption: Optional[str] = None

    def save_to_directory(self, directory: str):
        ensure_directory_exists(directory)
        log.debug(f"Saving image to directory: {directory}")
        if base_64 := self.base_64:
            filename = self.image_id
            file_path = f"{directory}/{filename}"
            save_base64_to_binary_file(b64=base_64, file_path=file_path)


class ExtractedImageFromPage(ExtractedImage):
    top_left_x: Optional[int] = None
    top_left_y: Optional[int] = None
    bottom_right_x: Optional[int] = None
    bottom_right_y: Optional[int] = None


class Page(CustomBaseModel):
    text: Optional[str] = None
    extracted_images: List[ExtractedImageFromPage] = Field(default_factory=list)
    page_view: Optional[ExtractedImageFromPage] = None

    def save_to_directory(self, directory: str, page_text_file_name: str):
        ensure_directory_exists(directory)
        log.debug(f"Saving page to directory: {directory}")
        if text := self.text:
            filename = page_text_file_name
            save_text_to_path(text=text, path=f"{directory}/{filename}")
        for image in self.extracted_images:
            image.save_to_directory(directory=directory)
        if page_view := self.page_view:
            page_view.save_to_directory(directory=directory)


class OcrOutput(CustomBaseModel):
    pages: Dict[int, Page]

    @property
    def concatenated_text(self) -> str:
        return "\n".join([page.text for page in self.pages.values() if page.text])

    def save_to_directory(self, directory: str, page_text_file_name: str):
        ensure_directory_exists(directory)
        full_text = self.concatenated_text
        save_text_to_path(text=full_text, path=f"{directory}/full_text.txt")
        for page_number, page in self.pages.items():
            directory_for_page = f"{directory}/page_{page_number}"
            page.save_to_directory(directory=directory_for_page, page_text_file_name=page_text_file_name)
