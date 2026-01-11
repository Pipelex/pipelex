from abc import ABC, abstractmethod
from typing import Any

from jinja2.runtime import Context

from pipelex.types import StrEnum


class Jinja2FilterName(StrEnum):
    FORMAT = "format"
    TAG = "tag"
    ESCAPE_SCRIPT_TAG = "escape_script_tag"
    WITH_IMAGES = "with_images"


class Jinja2ContextKey(StrEnum):
    TAG_STYLE = "tag_style"
    TEXT_FORMAT = "text_format"
    IMAGE_REGISTRY = "image_registry"


class Jinja2TaggableAbstract(ABC):
    @abstractmethod
    async def render_tagged_for_jinja2(self, context: Context, tag_name: str | None = None) -> tuple[Any, str | None]:
        pass
