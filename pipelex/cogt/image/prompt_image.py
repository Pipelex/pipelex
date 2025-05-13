# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from abc import ABC
from typing import Union

from pydantic import BaseModel
from typing_extensions import override

from pipelex.tools.utils.filetype_utils import FileType, detect_file_type_from_base64, detect_file_type_from_path


class PromptImageTypedBytes(BaseModel):
    image_bytes: bytes
    file_type: FileType


PromptImageTypedBytesOrUrl = Union[PromptImageTypedBytes, str]


class PromptImage(BaseModel, ABC):
    pass


class PromptImagePath(PromptImage):
    file_path: str

    def get_file_type(self) -> FileType:
        return detect_file_type_from_path(self.file_path)

    @override
    def __str__(self) -> str:
        return f"PromptImagePath(file_path='{self.file_path}')"


class PromptImageUrl(PromptImage):
    url: str

    @override
    def __str__(self) -> str:
        return f"PromptImageUrl(url='{self.url}')"


class PromptImageBytes(PromptImage):
    b64_image_bytes: bytes

    def get_file_type(self) -> FileType:
        return detect_file_type_from_base64(self.b64_image_bytes)

    @override
    def __str__(self) -> str:
        bytes_sample: str = str(self.b64_image_bytes[:20])
        if len(self.b64_image_bytes) > 20:
            bytes_sample += "..."
        bytes_preview = f"{len(self.b64_image_bytes)} bytes: {bytes_sample}"
        return f"PromptImageBytes(image_bytes={bytes_preview})"

    @override
    def __repr__(self) -> str:
        return self.__str__()

    def make_prompt_image_typed_bytes(self) -> PromptImageTypedBytes:
        return PromptImageTypedBytes(image_bytes=self.b64_image_bytes, file_type=self.get_file_type())
