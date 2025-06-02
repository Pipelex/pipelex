from abc import ABC, abstractmethod
from typing import Any, Optional, Tuple

from jinja2.runtime import Context

from pipelex.types import StrEnum


class Jinja2FilterName(StrEnum):
    FORMAT = "format"
    TAG = "tag"


class Jinja2ContextKey(StrEnum):
    TAG_STYLE = "tag_style"
    TEXT_FORMAT = "text_format"


class Jinja2TaggableAbstract(ABC):
    @abstractmethod
    def render_tagged_for_jinja2(self, context: Context, tag_name: Optional[str] = None) -> Tuple[Any, Optional[str]]:
        pass
