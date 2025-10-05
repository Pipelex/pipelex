from json2html import json2html
from typing_extensions import override

from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.tools.misc.markdown_utils import convert_to_markdown
from pipelex.tools.typing.pydantic_utils import clean_model_to_dict


class StructuredContent(StuffContent):
    @property
    @override
    def short_desc(self) -> str:
        return f"some structured content of class {self.__class__.__name__}"

    @override
    def smart_dump(self):
        return self.model_dump(serialize_as_any=True)

    @override
    def rendered_html(self) -> str:
        dict_dump = clean_model_to_dict(obj=self)

        html: str = json2html.convert(  # pyright: ignore[reportAssignmentType, reportUnknownVariableType]
            json=dict_dump,  # pyright: ignore[reportArgumentType]
            clubbing=True,
            table_attributes="",
        )
        return html

    @override
    def rendered_markdown(self, level: int = 1, is_pretty: bool = False) -> str:
        dict_dump = clean_model_to_dict(obj=self)
        return convert_to_markdown(data=dict_dump, level=level, is_pretty=is_pretty)
