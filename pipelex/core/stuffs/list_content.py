from typing import Any, Generic

from json2html import json2html
from typing_extensions import override

from pipelex.cogt.templating.templating_style import TextFormat
from pipelex.core.stuffs.stuff_content import StuffContent, StuffContentType


class ListContent(StuffContent, Generic[StuffContentType]):
    items: list[StuffContentType]

    @property
    def nb_items(self) -> int:
        return len(self.items)

    def get_items(self, item_type: type[StuffContent]) -> list[StuffContent]:
        return [item for item in self.items if isinstance(item, item_type)]

    @property
    @override
    def short_desc(self) -> str:
        nb_items = len(self.items)
        if nb_items == 0:
            return "empty list"
        if nb_items == 1:
            return f"list of 1 {self.items[0].__class__.__name__}"
        item_classes: list[str] = [item.__class__.__name__ for item in self.items]
        item_classes_set = set(item_classes)
        nb_classes = len(item_classes_set)
        if nb_classes == 1:
            return f"list of {len(self.items)} {item_classes[0]}s"
        elif nb_items == nb_classes:
            return f"list of {len(self.items)} items of different types"
        else:
            return f"list of {len(self.items)} items of {nb_classes} different types"

    @property
    def _single_class_name(self) -> str | None:
        item_classes: list[str] = [item.__class__.__name__ for item in self.items]
        item_classes_set = set(item_classes)
        nb_classes = len(item_classes_set)
        if nb_classes == 1:
            return item_classes[0]
        else:
            return None

    @override
    def model_dump(self, *args: Any, **kwargs: Any):
        obj_dict = super().model_dump(*args, **kwargs)
        obj_dict["items"] = [item.model_dump(*args, **kwargs) for item in self.items]
        return obj_dict

    @override
    def rendered_plain(self) -> str:
        return self.rendered_markdown()

    @override
    def rendered_html(self) -> str:
        list_dump = [item.smart_dump() for item in self.items]

        html: str = json2html.convert(  # pyright: ignore[reportAssignmentType, reportUnknownVariableType]
            json=list_dump,  # pyright: ignore[reportArgumentType]
            clubbing=True,
            table_attributes="",
        )
        return html

    @override
    def rendered_markdown(self, level: int = 1, is_pretty: bool = False) -> str:
        rendered = ""
        if self._single_class_name == "TextContent":
            for item in self.items:
                rendered += f" • {item}\n"
        else:
            for item_index, item in enumerate(self.items):
                rendered += f"\n • item #{item_index + 1}:\n\n"
                rendered += item.rendered_str(text_format=TextFormat.MARKDOWN)
                rendered += "\n"
        return rendered
