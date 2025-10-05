import base64
import json
import types
import typing
from abc import ABC, abstractmethod
from io import BytesIO
from typing import Any, Generic, TypeVar

import markdown
from json2html import json2html
from kajson import kajson
from PIL import Image
from pydantic import BaseModel
from typing_extensions import override
from yattag import Doc

from pipelex.cogt.ocr.ocr_output import ExtractedImage
from pipelex.tools.misc.base_64_utils import save_base64_to_binary_file
from pipelex.tools.misc.file_utils import ensure_directory_exists, get_incremental_file_path, save_text_to_path
from pipelex.tools.misc.filetype_utils import detect_file_type_from_base64
from pipelex.tools.misc.markdown_utils import convert_to_markdown
from pipelex.tools.misc.path_utils import InterpretedPathOrUrl, interpret_path_or_url
from pipelex.tools.templating.templating_models import TextFormat
from pipelex.tools.typing.pydantic_utils import CustomBaseModel, clean_model_to_dict
from pipelex.types import Self

ObjectContentType = TypeVar("ObjectContentType", bound=BaseModel)
StuffContentType = TypeVar("StuffContentType", bound="StuffContent")


class StuffContent(ABC, CustomBaseModel):
    @property
    def short_desc(self) -> str:
        return f"some {self.__class__.__name__}"

    def smart_dump(self) -> str | dict[str, Any] | list[str] | list[dict[str, Any]]:
        return self.model_dump(serialize_as_any=True)

    @override
    def __str__(self) -> str:
        return self.rendered_json()

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

    @classmethod
    def search_for_nested_image_fields(cls, current_path: str, paths: list[str]) -> list[str]:
        """Recursively search for image fields in a structure class."""
        # Iterate through all fields
        for field_name, field_info in cls.model_fields.items():
            # Build the path for this field
            field_path = f"{current_path}.{field_name}" if current_path else field_name

            # Get the field type annotation
            field_type = field_info.annotation

            # Handle Optional types (Union with None)
            is_union = False
            union_args = None

            # Check for typing.Union (typing.Optional)
            is_typing_union = hasattr(field_type, "__origin__") and field_type.__origin__ is typing.Union  # type: ignore[union-attr] # pyright: ignore[reportOptionalMemberAccess]
            is_types_union = hasattr(types, "UnionType") and isinstance(field_type, types.UnionType)  # pyright: ignore[reportUnnecessaryIsInstance]
            if is_typing_union or is_types_union:
                is_union = True
                union_args = field_type.__args__  # type: ignore[union-attr]

            potential_types: list[Any] = []
            potential_field_types: list[Any] = []  # Keep track of the full type with generics
            if is_union and union_args:
                potential_types = union_args
                potential_field_types = union_args  # In union case, each arg is a complete type
            else:
                potential_types = [field_type]
                potential_field_types = [field_type]

            for idx, field_specific_type in enumerate(potential_types):
                # Get the corresponding field type with full generic info
                current_field_type = potential_field_types[idx]

                # Check if it's a ListContent generic type (e.g., ListContent[PhotoAlbumItem])
                if hasattr(field_specific_type, "__origin__"):  # type: ignore[union-attr]
                    origin = field_specific_type.__origin__  # type: ignore[union-attr]
                    # Check for list, tuple, or ListContent
                    try:
                        is_list_or_tuple = origin in (list, tuple)
                        is_list_content = isinstance(origin, type) and issubclass(origin, ListContent)
                    except TypeError:
                        is_list_or_tuple = False
                        is_list_content = False

                    if is_list_or_tuple or is_list_content:
                        # Get the args (item types) from the generic
                        container_args = getattr(field_specific_type, "__args__", ())
                        # Check if any of the args contain images (directly or nested)
                        has_images = False
                        for arg_type in container_args:
                            # Check if arg_type is itself a generic (nested list/tuple)
                            if hasattr(arg_type, "__origin__") and arg_type.__origin__ in (list, tuple):  # type: ignore[union-attr]
                                # Recursively check nested generics (e.g., list[tuple[A, B]])
                                # Create a temporary field to check
                                temp_paths = cls._check_container_for_images(arg_type)
                                if temp_paths:
                                    has_images = True
                            elif isinstance(arg_type, type):
                                try:
                                    # Check if it's directly ImageContent
                                    if issubclass(arg_type, ImageContent):
                                        has_images = True
                                    # Check if it's a StuffContent that might have nested images
                                    elif issubclass(arg_type, StuffContent) and not issubclass(arg_type, ListContent):
                                        # Recursively check if this type has nested images
                                        nested_paths = arg_type.search_for_nested_image_fields(current_path="", paths=[])
                                        if nested_paths:
                                            # Found nested images in the container's item type
                                            has_images = True
                                except TypeError:
                                    # Handle edge cases where issubclass fails
                                    continue
                        # Add the field path once if any of the container items have images
                        if has_images:
                            paths.append(field_path)
                        continue  # Move to next field after handling list/tuple/ListContent

                # Skip if field type is not a class
                if not isinstance(field_specific_type, type):
                    continue
                if field_specific_type is type(None):
                    continue

                # Try-except to handle Python 3.10 compatibility with generic types
                try:
                    # Check if it's a direct ImageContent first
                    if issubclass(field_specific_type, ImageContent):
                        paths.append(field_path)
                        continue

                    # Check if it's a ListContent subclass (Pydantic creates actual classes, not generic aliases)
                    if issubclass(field_specific_type, ListContent):
                        # For ListContent, check if the items have images
                        # Get the generic argument from Pydantic v2's __pydantic_generic_metadata__
                        list_item_types = None
                        if hasattr(field_specific_type, "__pydantic_generic_metadata__"):  # pyright: ignore[reportUnknownArgumentType]
                            # Pydantic v2 stores generic info as a dict
                            generic_metadata = field_specific_type.__pydantic_generic_metadata__  # type: ignore[attr-defined]
                            # generic_metadata is PydanticGenericMetadata which inherits from dict
                            if "args" in generic_metadata:  # pyright: ignore[reportUnnecessaryIsInstance]
                                list_item_types = generic_metadata["args"]
                        elif hasattr(current_field_type, "__args__"):
                            list_item_types = current_field_type.__args__  # type: ignore[union-attr]

                        if list_item_types:
                            has_images_in_list = False
                            for list_item_type in list_item_types:
                                if isinstance(list_item_type, type):
                                    try:
                                        # Check if the item type is ImageContent
                                        if issubclass(list_item_type, ImageContent):
                                            has_images_in_list = True
                                            break
                                        # Check if the item type has nested images
                                        if issubclass(list_item_type, StuffContent) and not issubclass(list_item_type, ListContent):
                                            nested_paths = list_item_type.search_for_nested_image_fields(current_path="", paths=[])
                                            if nested_paths:
                                                has_images_in_list = True
                                                break
                                    except TypeError:
                                        continue
                            if has_images_in_list:
                                paths.append(field_path)
                        continue

                    # If it's a StuffContent subclass (excluding ListContent which we just handled), recurse into it
                    if issubclass(field_specific_type, StuffContent):
                        paths = field_specific_type.search_for_nested_image_fields(current_path=field_path, paths=paths)
                except TypeError:
                    # In Python 3.10, some generic types may pass isinstance(type) but fail issubclass()
                    continue

        return paths

    @classmethod
    def _check_container_for_images(cls, container_type: Any) -> bool:
        """Helper method to recursively check if a container type (list/tuple) contains images.

        Args:
            container_type: A generic type like list[...], tuple[...], or ListContent[...]

        Returns:
            True if the container or its nested contents contain ImageContent
        """
        if not hasattr(container_type, "__origin__") or container_type.__origin__ not in (list, tuple):  # type: ignore[union-attr]
            return False

        container_args = getattr(container_type, "__args__", ())
        for arg_type in container_args:
            # Check if arg_type is itself a generic (nested list/tuple)
            if hasattr(arg_type, "__origin__") and arg_type.__origin__ in (list, tuple):  # type: ignore[union-attr]
                if cls._check_container_for_images(arg_type):
                    return True
            elif isinstance(arg_type, type):
                try:
                    # Check if it's directly ImageContent
                    if issubclass(arg_type, ImageContent):
                        return True
                    # Check if it's a ListContent - need to check its items
                    if issubclass(arg_type, ListContent):
                        # For ListContent, we'd need the field_type with generic args
                        # For now, conservatively assume it might have images
                        # This is safe because we're just deciding whether to include the field path
                        return True
                    # Check if it's a StuffContent that might have nested images
                    if issubclass(arg_type, StuffContent):
                        # Recursively check if this type has nested images
                        nested_paths = arg_type.search_for_nested_image_fields(current_path="", paths=[])
                        if nested_paths:
                            return True
                except TypeError:
                    # Handle edge cases where issubclass fails
                    continue
        return False


class TextContent(StuffContent):
    text: str

    @override
    def smart_dump(self) -> str | dict[str, Any] | list[str] | list[dict[str, Any]]:
        return self.text

    @property
    @override
    def short_desc(self) -> str:
        return f"some text ({len(self.text)} chars)"

    @override
    def __str__(self) -> str:
        return self.text

    @override
    def rendered_plain(self) -> str:
        return self.text

    @override
    def rendered_html(self) -> str:
        # Convert a markdown string to HTML and return HTML as a Unicode string.
        return markdown.markdown(self.text)

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


class NumberContent(StuffContent):
    number: int | float

    @override
    def smart_dump(self) -> str | dict[str, Any] | list[str] | list[dict[str, Any]]:
        return str(self.number)

    @property
    @override
    def short_desc(self) -> str:
        return f"some number ({self.number})"

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


class ImageContent(StuffContent):
    url: str
    source_prompt: str | None = None
    caption: str | None = None
    base_64: str | None = None

    @property
    @override
    def short_desc(self) -> str:
        url_desc = interpret_path_or_url(path_or_uri=self.url).desc
        return f"{url_desc} or an image"

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

    def save_to_directory(self, directory: str, base_name: str | None = None, extension: str | None = None):
        ensure_directory_exists(directory)
        base_name = base_name or "img"
        if (base_64 := self.base_64) and not extension:
            match interpret_path_or_url(path_or_uri=self.url):
                case InterpretedPathOrUrl.FILE_NAME:
                    parts = self.url.rsplit(".", 1)
                    base_name = parts[0]
                    extension = parts[1]
                case InterpretedPathOrUrl.FILE_PATH | InterpretedPathOrUrl.FILE_URI | InterpretedPathOrUrl.URL | InterpretedPathOrUrl.BASE_64:
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


class PDFContent(StuffContent):
    url: str

    @property
    @override
    def short_desc(self) -> str:
        url_desc = interpret_path_or_url(path_or_uri=self.url).desc
        return f"{url_desc} of a PDF document"

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


class TextAndImagesContent(StuffContent):
    text: TextContent | None
    images: list[ImageContent] | None

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
    page_view: ImageContent | None = None

    def save_to_directory(self, directory: str):
        ensure_directory_exists(directory)
        self.text_and_images.save_to_directory(directory=directory)
        if page_view := self.page_view:
            page_view.save_to_directory(directory=directory, base_name="page_view")
