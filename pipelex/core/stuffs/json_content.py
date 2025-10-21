from typing import Any

from json2html import json2html
from kajson import kajson
from typing_extensions import override

from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.tools.misc.markdown_utils import convert_to_markdown


class JSONContent(StuffContent):
    json_obj: dict[str, Any]

    @override
    def rendered_html(self) -> str:
        return str(json2html.convert(json=kajson.dumps(self.json_obj, indent=4), clubbing=True))  # pyright: ignore[reportUnknownArgumentType]

    @override
    def rendered_markdown(self, level: int = 1, is_pretty: bool = False) -> str:
        return convert_to_markdown(self.json_obj)
