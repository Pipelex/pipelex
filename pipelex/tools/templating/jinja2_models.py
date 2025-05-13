# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any, Optional, Tuple

from jinja2.runtime import Context


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
