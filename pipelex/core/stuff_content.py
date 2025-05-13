# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

import json
from abc import ABC, abstractmethod
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar, Union

import markdown
from json2html import json2html
from kajson import kajson
from pydantic import BaseModel
from typing_extensions import override
from yattag import Doc

from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.tools.misc.markdown_helpers import convert_to_markdown
from pipelex.tools.misc.model_helpers import clean_model_to_dict
from pipelex.tools.templating.templating_models import TextFormat
from pipelex.tools.utils.path_utils import interpret_path_or_url

ObjectContentType = TypeVar("ObjectContentType", bound=BaseModel)
StuffContentType = TypeVar("StuffContentType", bound="StuffContent")


class StuffContentError(Exception):
    pass


class StuffContent(ABC, BaseModel):
    @property
    def short_desc(self) -> str:
        return f"some {self.__class__.__name__}"

    def smart_dump(self) -> Union[str, Dict[str, Any], List[str], List[Dict[str, Any]]]:
        return self.model_dump(serialize_as_any=True)

    @override
    def __str__(self) -> str:
        return self.rendered_plain()

    def rendered_str(self, text_format: TextFormat = TextFormat.PLAIN) -> str:
        match text_format:
            case TextFormat.PLAIN:
                return self.rendered_plain()
            case TextFormat.HTML:
                return self.rendered_html()
            case TextFormat.MARKDOWN:
                return self.rendered_markdown()
            case TextFormat.JSON:
                return self.rendered_json()
            case TextFormat.SPREADSHEET:
                return self.render_spreadsheet()

    def rendered_plain(self) -> str:
        return self.rendered_markdown()

    @abstractmethod
    def rendered_html(self) -> str:
        pass

    @abstractmethod
    def rendered_markdown(self, level: int = 1, is_pretty: bool = False) -> str:
        pass

    def render_spreadsheet(self) -> str:
        return self.rendered_plain()

    def rendered_json(self) -> str:
        return kajson.dumps(self.smart_dump(), indent=4)


class StuffContentInitableFromStr(StuffContent):
    @classmethod
    @abstractmethod
    def make_from_str(cls, str_value: str) -> "StuffContentInitableFromStr":
        pass


class TextContent(StuffContentInitableFromStr):
    text: str

    @override
    def smart_dump(self) -> Union[str, Dict[str, Any], List[str], List[Dict[str, Any]]]:
        return self.text

    @property
    @override
    def short_desc(self) -> str:
        return f"some text ({len(self.text)} chars)"

    @classmethod
    @override
    def make_from_str(cls, str_value: str) -> "TextContent":
        return TextContent(text=str_value)

    @override
    def __str__(self) -> str:
        return self.text

    @override
    def rendered_plain(self) -> str:
        return self.text

    @override
    def rendered_html(self) -> str:
        # Convert a markdown string to HTML and return HTML as a Unicode string.
        html = markdown.markdown(self.text)
        return html

    @override
    def rendered_markdown(self, level: int = 1, is_pretty: bool = False) -> str:
        return self.text

    @override
    def rendered_json(self) -> str:
        return json.dumps({"text": self.text})


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


class NumberContent(StuffContentInitableFromStr):
    number: Union[int, float]

    @override
    def smart_dump(self) -> Union[str, Dict[str, Any], List[str], List[Dict[str, Any]]]:
        return str(self.number)

    @property
    @override
    def short_desc(self) -> str:
        return f"some number ({self.number})"

    @classmethod
    @override
    def make_from_str(cls, str_value: str) -> "NumberContent":
        try:
            int_value = int(str_value)
            return NumberContent(number=int_value)
        except ValueError:
            float_value = float(str_value)
            return NumberContent(number=float_value)

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


class ImageContent(StuffContentInitableFromStr):
    url: str
    source_prompt: Optional[str] = None

    @property
    @override
    def short_desc(self) -> str:
        url_desc = interpret_path_or_url(path_or_url=self.url).desc
        return f"{url_desc} or an image"

    @classmethod
    @override
    def make_from_str(cls, str_value: str) -> "ImageContent":
        return ImageContent(url=str_value)

    @override
    def rendered_plain(self) -> str:
        return self.url

    @override
    def rendered_html(self) -> str:
        doc = Doc()
        doc.stag("img", src=self.url, klass="msg-img")

        return doc.getvalue()

    @override
    def rendered_markdown(self, level: int = 1, is_pretty: bool = False) -> str:
        return f"![{self.url}]({self.url})"

    @override
    def rendered_json(self) -> str:
        return json.dumps({"image_url": self.url, "source_prompt": self.source_prompt})


class HtmlContent(StuffContent):
    inner_html: str
    css_class: str

    @property
    @override
    def short_desc(self) -> str:
        return f"some html ({len(self.inner_html)} chars)"

    @override
    def __str__(self) -> str:
        return self.rendered_html()

    @override
    def rendered_plain(self) -> str:
        return self.inner_html

    @override
    def rendered_html(self) -> str:
        doc, tag, text = Doc().tagtext()
        with tag("div", klass=self.css_class):
            text(self.inner_html)
        return doc.getvalue()

    @override
    def rendered_markdown(self, level: int = 1, is_pretty: bool = False) -> str:
        return self.inner_html

    @override
    def rendered_json(self) -> str:
        return json.dumps({"html": self.inner_html, "css_class": self.css_class})


class MermaidContent(StuffContent):
    mermaid_code: str
    mermaid_url: str

    @property
    @override
    def short_desc(self) -> str:
        return f"some mermaid code ({len(self.mermaid_code)} chars)"

    @override
    def __str__(self) -> str:
        return self.mermaid_code

    @override
    def rendered_plain(self) -> str:
        return self.mermaid_code

    @override
    def rendered_html(self) -> str:
        doc, tag, text = Doc().tagtext()
        with tag("div", klass="mermaid"):
            text(self.mermaid_code)
        return doc.getvalue()

    @override
    def rendered_markdown(self, level: int = 1, is_pretty: bool = False) -> str:
        return self.mermaid_code

    @override
    def rendered_json(self) -> str:
        return json.dumps({"mermaid": self.mermaid_code})


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

        html: str = json2html.convert(  # pyright: ignore[reportAssignmentType]
            json=dict_dump,  # pyright: ignore[reportArgumentType]
            clubbing=True,
            table_attributes="",
        )
        return html

    @override
    def rendered_markdown(self, level: int = 1, is_pretty: bool = False) -> str:
        dict_dump = clean_model_to_dict(obj=self)
        return convert_to_markdown(data=dict_dump, level=level, is_pretty=is_pretty)


class LLMPromptContent(StructuredContent, LLMPrompt):
    pass


class ListContent(StuffContent, Generic[StuffContentType]):
    items: List[StuffContentType]

    @property
    def nb_items(self) -> int:
        return len(self.items)

    def get_items(self, item_type: Type[StuffContent]) -> List[StuffContent]:
        return [item for item in self.items if isinstance(item, item_type)]

    @property
    @override
    def short_desc(self) -> str:
        nb_items = len(self.items)
        if nb_items == 0:
            return "empty list"
        elif nb_items == 1:
            return f"list of 1 {self.items[0].__class__.__name__}"
        else:
            item_classes: List[str] = [item.__class__.__name__ for item in self.items]
            item_classes_set = set(item_classes)
            nb_classes = len(item_classes_set)
            if nb_classes == 1:
                return f"list of {len(self.items)} {item_classes[0]}s"
            elif nb_items == nb_classes:
                return f"list of {len(self.items)} items of different types"
            else:
                return f"list of {len(self.items)} items of {nb_classes} different types"

    @property
    def _single_class_name(self) -> Optional[str]:
        item_classes: List[str] = [item.__class__.__name__ for item in self.items]
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

        html: str = json2html.convert(  # pyright: ignore[reportAssignmentType]
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
