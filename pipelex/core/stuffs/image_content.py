import json

from typing_extensions import override

from pipelex.cogt.exceptions import ImageContentError
from pipelex.cogt.extract.extract_output import ExtractedImage
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.tools.jinja2.jinja2_rendering import render_jinja2_sync
from pipelex.tools.misc.base_64_utils import prefixed_base64_str_from_base64_str
from pipelex.tools.misc.file_utils import ensure_directory_exists, get_incremental_file_path, save_text_to_path
from pipelex.tools.misc.path_utils import interpret_path_or_url
from pipelex.types import Self


class ImageContent(StuffContent):
    url: str
    source_prompt: str | None = None
    caption: str | None = None

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
        template_source = '<img src="{{ url|e }}" class="msg-img">'
        return render_jinja2_sync(
            template_source=template_source,
            template_category=TemplateCategory.HTML,
            temlating_context={
                "url": self.url,
            },
        )

    @override
    def rendered_markdown(self, level: int = 1, is_pretty: bool = False) -> str:
        return f"![{self.url[:100]}]({self.url})"

    @override
    def rendered_json(self) -> str:
        return json.dumps({"image_url": self.url, "source_prompt": self.source_prompt})

    @classmethod
    def make_from_extracted_image(cls, extracted_image: ExtractedImage) -> Self:
        if base_64 := extracted_image.base_64:
            # Check if it's already a prefixed base64 string
            if base_64.startswith("data:"):
                prefixed_base64_str = base_64
            else:
                prefixed_base64_str = prefixed_base64_str_from_base64_str(b64_str=base_64)
            return cls(
                url=prefixed_base64_str,
                caption=extracted_image.caption,
            )
        else:
            msg = f"Base 64 is required for image content: {extracted_image}"
            raise ImageContentError(msg)

    def save_to_directory(self, directory: str, base_name: str | None = None):
        ensure_directory_exists(directory)
        base_name = base_name or "img"

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
