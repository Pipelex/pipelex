import json

from pydantic import Field
from typing_extensions import override

from pipelex.core.stuffs.stuff_content import StuffContent


class YesNoContent(StuffContent):
    yes_no: bool = Field(description="Whether the answer is yes (true) or no (false).")

    @property
    @override
    def short_desc(self) -> str:
        return f"a yes/no answer ({'yes' if self.yes_no else 'no'})"

    @override
    def rendered_plain(self) -> str:
        return "yes" if self.yes_no else "no"

    @override
    def rendered_html(self) -> str:
        return "yes" if self.yes_no else "no"

    @override
    def rendered_markdown(self, *, level: int = 1, is_pretty: bool = False) -> str:
        return "yes" if self.yes_no else "no"

    @override
    def rendered_json(self) -> str:
        return json.dumps({"yes_no": self.yes_no})
