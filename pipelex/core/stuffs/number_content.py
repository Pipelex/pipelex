import json
from typing import Any

from typing_extensions import override

from pipelex.core.stuffs.stuff_content import StuffContent


class NumberContent(StuffContent):
    number: int | float

    @override
    def smart_dump(self) -> str | dict[str, Any] | list[str] | list[dict[str, Any]]:
        return str(self.number)

    @property
    @override
    def short_desc(self) -> str:
        return f"some number ({self.number})"

    @override
    def __str__(self) -> str:
        return str(self.number)

    @override
    def rendered_plain(self) -> str:
        return str(self.number)

    @override
    def rendered_html(self) -> str:
        return str(self.number)

    @override
    def rendered_markdown(self, level: int = 1, is_pretty: bool = False) -> str:
        return str(self.number)

    @override
    def rendered_json(self) -> str:
        return json.dumps({"number": self.number})
