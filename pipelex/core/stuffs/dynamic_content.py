from typing_extensions import override

from pipelex.core.stuffs.stuff_content import StuffContent


class DynamicContent(StuffContent):
    @property
    @override
    def short_desc(self) -> str:
        return "some dynamic concept"

    @override
    def rendered_html(self) -> str:
        return str(self.smart_dump())

    @override
    def rendered_markdown(self, level: int = 1, is_pretty: bool = False) -> str:
        return str(self.smart_dump())
