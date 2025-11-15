from typing import Any

from json2html import json2html
from kajson import kajson
from typing_extensions import override

from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.tools.misc.markdown_utils import convert_to_markdown
from pipelex.tools.typing.pydantic_utils import clean_model_to_dict


class JSONContent(StuffContent):
    json_obj: dict[Any, Any]

    @override
    def rendered_html(self) -> str:
        return str(json2html.convert(json=kajson.dumps(self.json_obj, indent=4), clubbing=True))  # pyright: ignore[reportUnknownArgumentType]

    @override
    def rendered_markdown(self, level: int = 1, is_pretty: bool = False) -> str:
        dict_dump = clean_model_to_dict(obj=self)
        return convert_to_markdown(data=dict_dump, level=level, is_pretty=is_pretty)

    @override
    def rendered_plain(self) -> str:
        return kajson.dumps(self.json_obj, indent=4)
