import base64
import json
from abc import ABC, abstractmethod
from io import BytesIO
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar, Union

import markdown
from json2html import json2html
from kajson import kajson
from PIL import Image
from pydantic import BaseModel
from typing_extensions import Self, override
from yattag import Doc

from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.ocr.ocr_output import ExtractedImage
from pipelex.tools.misc.base_64_utils import save_base64_to_binary_file
from pipelex.tools.misc.file_utils import ensure_directory_exists, get_incremental_file_path, save_text_to_path
from pipelex.tools.misc.filetype_utils import detect_file_type_from_base64
from pipelex.tools.misc.markdown_utils import convert_to_markdown
from pipelex.tools.misc.path_utils import InterpretedPathOrUrl, interpret_path_or_url
from pipelex.tools.templating.templating_models import TextFormat
from pipelex.tools.typing.pydantic_utils import CustomBaseModel, clean_model_to_dict

ObjectContentType = TypeVar("ObjectContentType", bound=BaseModel)
StuffContentType = TypeVar("StuffContentType", bound="StuffContent")

# TODO: split in separate files


class StuffContent(ABC, CustomBaseModel):
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

    def save_to_directory(self, directory: str):
        ensure_directory_exists(directory)
        filename = "text_content.txt"
        save_text_to_path(text=self.text, path=f"{directory}/{filename}")


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
    caption: Optional[str] = None
    base_64: Optional[str] = None

    @property
    @override
    def short_desc(self) -> str:
        url_desc = interpret_path_or_url(path_or_uri=self.url).desc
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

    @classmethod
    def make_from_extracted_image(cls, extracted_image: ExtractedImage) -> Self:
        return cls(
            url=extracted_image.image_id,
            base_64=extracted_image.base_64,
            caption=extracted_image.caption,
        )

    @classmethod
    def make_from_image(cls, image: Image.Image) -> Self:
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        base_64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return cls(
            url=f"data:image/png;base64,{base_64}",
            base_64=base_64,
        )

    def save_to_directory(self, directory: str, base_name: Optional[str] = None, extension: Optional[str] = None):
        ensure_directory_exists(directory)
        base_name = base_name or "img"
        if base_64 := self.base_64:
            if not extension:
                match interpret_path_or_url(path_or_uri=self.url):
                    case InterpretedPathOrUrl.FILE_NAME:
                        parts = self.url.rsplit(".", 1)
                        base_name = parts[0]
                        extension = parts[1]
                    case _:
                        file_type = detect_file_type_from_base64(b64=base_64)
                        base_name = base_name or "img"
                        extension = file_type.extension
                file_path = get_incremental_file_path(
                    base_path=directory,
                    base_name=base_name,
                    extension=extension,
                    avoid_suffix_if_possible=True,
                )
                save_base64_to_binary_file(b64=base_64, file_path=file_path)

        if caption := self.caption:
            caption_file_path = get_incremental_file_path(
                base_path=directory,
                base_name=f"{base_name}_caption",
                extension="txt",
                avoid_suffix_if_possible=True,
            )
            save_text_to_path(text=caption, path=caption_file_path)
        if source_prompt := self.source_prompt:
            source_prompt_file_path = get_incremental_file_path(
                base_path=directory,
                base_name=f"{base_name}_source_prompt",
                extension="txt",
                avoid_suffix_if_possible=True,
            )
            save_text_to_path(text=source_prompt, path=source_prompt_file_path)


class PDFContent(StuffContentInitableFromStr):
    url: str

    @property
    @override
    def short_desc(self) -> str:
        url_desc = interpret_path_or_url(path_or_uri=self.url).desc
        return f"{url_desc} of a PDF document"

    @classmethod
    @override
    def make_from_str(cls, str_value: str) -> "PDFContent":
        return PDFContent(url=str_value)

    @override
    def rendered_plain(self) -> str:
        return self.url

    @override
    def rendered_html(self) -> str:
        doc = Doc()
        doc.stag("a", href=self.url, klass="msg-pdf")
        doc.text(self.url)

        return doc.getvalue()

    @override
    def rendered_markdown(self, level: int = 1, is_pretty: bool = False) -> str:
        return f"[{self.url}]({self.url})"


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


class TextAndImagesContent(StuffContent):
    text: Optional[TextContent]
    images: Optional[List[ImageContent]]

    @property
    @override
    def short_desc(self) -> str:
        text_count = 1 if self.text else 0
        image_count = len(self.images) if self.images else 0
        return f"text and image content ({text_count} text, {image_count} images)"

    @override
    def rendered_markdown(self, level: int = 1, is_pretty: bool = False) -> str:
        if self.text:
            rendered = self.text.rendered_markdown(level=level, is_pretty=is_pretty)
        else:
            rendered = ""
        return rendered

    @override
    def rendered_html(self) -> str:
        if self.text:
            rendered = self.text.rendered_html()
        else:
            rendered = ""
        return rendered

    def save_to_directory(self, directory: str):
        ensure_directory_exists(directory)
        if text_content := self.text:
            text_content.save_to_directory(directory=directory)
        if images := self.images:
            for image_content in images:
                image_content.save_to_directory(directory=directory)


class PageContent(StructuredContent):
    text_and_images: TextAndImagesContent
    page_view: Optional[ImageContent] = None

    def save_to_directory(self, directory: str):
        ensure_directory_exists(directory)
        self.text_and_images.save_to_directory(directory=directory)
        if page_view := self.page_view:
            page_view.save_to_directory(directory=directory, base_name="page_view")
