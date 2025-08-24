from abc import ABC
from typing import Union

from pydantic import BaseModel
from typing_extensions import override

from pipelex.tools.misc.attribute_utils import AttributePolisher
from pipelex.tools.misc.filetype_utils import FileType, detect_file_type_from_base64, detect_file_type_from_path
from pipelex.tools.typing.pydantic_utils import CustomBaseModel


class PromptImageTypedBytes(CustomBaseModel):
    base_64: bytes
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
        truncated_url = AttributePolisher.get_truncated_value(name="url", value=self.url)
        return f"PromptImageUrl(url='{truncated_url!r}')"

    @override
    def __format__(self, format_spec: str) -> str:
        return self.__str__()


class PromptImageBytes(PromptImage):
    base_64: bytes

    def get_file_type(self) -> FileType:
        return detect_file_type_from_base64(self.base_64)

    @override
    def __str__(self) -> str:
        base_64_str = str(self.base_64)
        truncated_base_64 = AttributePolisher.get_truncated_value(name="base_64", value=base_64_str)
        return f"PromptImageBytes(image_bytes={truncated_base_64!r})"

    @override
    def __repr__(self) -> str:
        return self.__str__()

    @override
    def __format__(self, format_spec: str) -> str:
        return self.__str__()

    def make_prompt_image_typed_bytes(self) -> PromptImageTypedBytes:
        return PromptImageTypedBytes(base_64=self.base_64, file_type=self.get_file_type())
