import base64
import json
from io import BytesIO

from PIL import Image
from typing_extensions import override
from yattag import Doc

from pipelex.cogt.exceptions import ImageContentError
from pipelex.cogt.extract.extract_output import ExtractedImage
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.tools.misc.base_64_utils import prefixed_base64_str_from_base64_str, save_base_64_str_to_binary_file
from pipelex.tools.misc.file_utils import ensure_directory_exists, get_incremental_file_path, save_text_to_path
from pipelex.tools.misc.filetype_utils import detect_file_type_from_base64
from pipelex.tools.misc.path_utils import InterpretedPathOrUrl, interpret_path_or_url
from pipelex.types import Self


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
        return self.url[:500]

    @override
    def rendered_html(self) -> str:
        doc = Doc()
        doc.stag("img", src=self.url, klass="msg-img")

        return doc.getvalue()

    @override
    def rendered_markdown(self, level: int = 1, is_pretty: bool = False) -> str:
        return f"![{self.url[:100]}]({self.url})"

    @override
    def rendered_json(self) -> str:
        return json.dumps({"image_url": self.url, "source_prompt": self.source_prompt})

    @classmethod
    def make_from_extracted_image(cls, extracted_image: ExtractedImage) -> Self:
        if base_64 := extracted_image.base_64:
            prefixed_base64_str = prefixed_base64_str_from_base64_str(b64_str=base_64)
            return cls(
                url=prefixed_base64_str,
                base_64=extracted_image.base_64,
                caption=extracted_image.caption,
            )
        else:
            msg = f"Base 64 is required for image content: {extracted_image}"
            raise ImageContentError(msg)

    @classmethod
    def make_from_image(cls, image: Image.Image) -> Self:
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        base_64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        prefixed_base64_str = prefixed_base64_str_from_base64_str(b64_str=base_64)
        return cls(
            url=prefixed_base64_str,
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
            save_base_64_str_to_binary_file(base_64_str=base_64, file_path=file_path)

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
