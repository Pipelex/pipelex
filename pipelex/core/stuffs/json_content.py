import json
from typing import Any

from json2html import json2html
from pydantic import field_validator
from rich.json import JSON
from typing_extensions import override

from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.tools.misc.markdown_utils import convert_to_markdown
from pipelex.tools.misc.pretty import PrettyPrintable


# TODO: use pipelex.tools.misc.json_utils.JsonContent to support lists in addition to dicts
class JSONContent(StuffContent):
    json_obj: dict[str, Any]

    @field_validator("json_obj", mode="before")
    @classmethod
    def check_valid_json(cls, value: dict[str, Any]) -> dict[str, Any]:
        try:
            json.dumps(value)
        except TypeError as exc:
            msg = f"json_obj is not valid JSON: {exc}"
            raise TypeError(msg) from exc
        except json.JSONDecodeError as exc:
            msg = f"json_obj is not valid JSON: {exc}"
            raise ValueError(msg) from exc
        return value

    @override
    def rendered_html(self) -> str:
        html: str = json2html.convert(  # pyright: ignore[reportAssignmentType, reportUnknownVariableType]
            json=self.json_obj,  # pyright: ignore[reportArgumentType]
            clubbing=True,
            table_attributes="",
        )
        return html

    @override
    def rendered_markdown(self, level: int = 1, is_pretty: bool = False) -> str:
        return convert_to_markdown(data=self.json_obj, level=level, is_pretty=is_pretty)

    @override
    def rendered_plain(self) -> str:
        return json.dumps(self.json_obj, indent=4)

    @override
    def rendered_json(self) -> str:
        return json.dumps(self.json_obj, indent=4)

    @override
    def rendered_pretty(self, title: str | None = None, depth: int = 0) -> PrettyPrintable:
        return JSON.from_data(self.json_obj, indent=4)
