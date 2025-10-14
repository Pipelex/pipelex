import base64
from abc import ABC
from typing import Union

from pydantic import BaseModel
from typing_extensions import override

from pipelex.tools.misc.attribute_utils import AttributePolisher
from pipelex.tools.misc.filetype_utils import (
    FileType,
    detect_file_type_from_base64,
    detect_file_type_from_bytes,
    detect_file_type_from_path,
)
from pipelex.tools.typing.pydantic_utils import CustomBaseModel


class PromptImageTypedBase64(CustomBaseModel):
    base_64: bytes
    file_type: FileType


PromptImageTypedUrlOrBase64 = Union[str, PromptImageTypedBase64]


class PromptImage(BaseModel, ABC):
    pass


class PromptImagePath(PromptImage):
    file_path: str

    def get_file_type(self) -> FileType:
        return detect_file_type_from_path(self.file_path)

    def get_mime_type(self) -> str:
        return self.get_file_type().mime

    @override
    def __str__(self) -> str:
        return f"PromptImagePath(file_path='{self.file_path}')"


class PromptImageUrl(PromptImage):
    url: str

    @override
    def __str__(self) -> str:
        truncated_url = AttributePolisher.get_truncated_value(name="url", value=self.url)
        return f"PromptImageUrl(url='{truncated_url!r}')"

    @override
    def __format__(self, format_spec: str) -> str:
        return self.__str__()


class PromptImageBase64(PromptImage):
    base_64: bytes

    def get_file_type(self) -> FileType:
        return detect_file_type_from_base64(self.base_64)

    def get_mime_type(self) -> str:
        return self.get_file_type().mime

    def get_decoded_bytes(self) -> bytes:
        return base64.b64decode(self.base_64)

    @override
    def __str__(self) -> str:
        base_64_str = str(self.base_64)
        truncated_base_64 = AttributePolisher.get_truncated_value(name="base_64", value=base_64_str)
        return f"PromptImageBase64(base_64={truncated_base_64!r})"

    @override
    def __repr__(self) -> str:
        return self.__str__()

    @override
    def __format__(self, format_spec: str) -> str:
        return self.__str__()

    def make_prompt_image_typed_base64(self) -> PromptImageTypedBase64:
        return PromptImageTypedBase64(base_64=self.base_64, file_type=self.get_file_type())


class PromptImageBinary(PromptImage):
    binary: bytes

    def get_file_type(self) -> FileType:
        return detect_file_type_from_bytes(self.binary)

    def get_mime_type(self) -> str:
        return self.get_file_type().mime

    @override
    def __str__(self) -> str:
        return "PromptImageBinary(binary=...)"

    @override
    def __repr__(self) -> str:
        return self.__str__()
