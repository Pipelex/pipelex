import json

from typing_extensions import override

from pipelex.core.stuffs.stuff_content import StuffContent


class NumberContent(StuffContent):
    number: int | float

    @property
    @override
    def short_desc(self) -> str:
        return f"some number ({self.number})"

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
