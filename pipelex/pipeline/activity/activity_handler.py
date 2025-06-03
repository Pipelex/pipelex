import os
from typing import Set, cast

from pipelex import log
from pipelex.config import get_config
from pipelex.core.stuff import Stuff, StuffContent
from pipelex.core.stuff_content import (
    HtmlContent,
    ImageContent,
    ListContent,
    MermaidContent,
    NumberContent,
    StructuredContent,
    TextContent,
)
from pipelex.pipeline.activity.activity_models import ActivityReport
from pipelex.tools.misc.file_fetch_utils import fetch_file_from_url_httpx
from pipelex.tools.misc.file_utils import ensure_path, save_text_to_path
from pipelex.tools.misc.json_utils import save_as_json_to_path


class ActivityHandlerForResultFiles:
    def __init__(self, result_dir_path: str):
        self.result_dir_path = result_dir_path
        self.images_dir_path = os.path.join(result_dir_path, "images")
        ensure_path(self.images_dir_path)
        imgg_config = get_config().cogt.imgg_config
        imgg_param_defaults = imgg_config.imgg_param_defaults
        self.image_output_format = imgg_param_defaults.output_format
        self.already_handled_stuff: Set[str] = set()

    def _generate_stuff_id(self, stuff: Stuff) -> str:
        # Use name if available, otherwise just use code
        name_part = stuff.stuff_name.replace(" ", "_") if stuff.stuff_name else ""
        return f"{name_part}_{stuff.stuff_code}" if name_part else stuff.stuff_code

    def handle_activity(self, activity_report: ActivityReport) -> None:
        if isinstance(activity_report.content, Stuff):
            the_stuff = activity_report.content
            if the_stuff.stuff_code in self.already_handled_stuff:
                log.info(f"Already handled stuff: {the_stuff.stuff_name}")
                return
            self.handle_stuff(stuff=the_stuff)
            if code := the_stuff.stuff_code:
                self.already_handled_stuff.add(code)
        else:
            log.error(f"Unhandled activity_report: {activity_report}")

    def handle_stuff(self, stuff: Stuff) -> None:
        # Create a directory for this stuff using its code and name
        stuff_id = self._generate_stuff_id(stuff)

        # Handle different content types
        if isinstance(stuff.content, TextContent):
            self._handle_text_content(content=stuff.content, stuff_id=stuff_id)
        elif isinstance(stuff.content, NumberContent):
            self._handle_number_content(content=stuff.content, stuff_id=stuff_id)
        elif isinstance(stuff.content, ImageContent):
            self._handle_image_content(content=stuff.content, stuff_id=stuff_id)
        elif isinstance(stuff.content, HtmlContent):
            self._handle_html_content(content=stuff.content, stuff_id=stuff_id)
        elif isinstance(stuff.content, MermaidContent):
            self._handle_mermaid_content(content=stuff.content, stuff_id=stuff_id)
        elif isinstance(stuff.content, StructuredContent):
            self._handle_structured_content(content=stuff.content, stuff_id=stuff_id)
        elif isinstance(stuff.content, ListContent):
            # TODO: check that all items are StuffContent
            self._handle_list_content(content=cast(ListContent[StuffContent], stuff.content), stuff_id=stuff_id)  # type: ignore
        else:
            log.error(f"Unhandled stuff content type: {type(stuff.content)}")

    def _handle_text_content(self, content: TextContent, stuff_id: str) -> None:
        stuff_dir = os.path.join(self.result_dir_path, stuff_id)
        ensure_path(stuff_dir)

        save_text_to_path(content.text, os.path.join(stuff_dir, f"{stuff_id}.txt"))
        # Also save rendered versions
        save_text_to_path(content.rendered_html(), os.path.join(stuff_dir, f"{stuff_id}.html"))
        save_text_to_path(content.rendered_markdown(), os.path.join(stuff_dir, f"{stuff_id}.md"))

    def _handle_number_content(self, content: NumberContent, stuff_id: str) -> None:
        stuff_dir = os.path.join(self.result_dir_path, stuff_id)
        ensure_path(stuff_dir)
        save_text_to_path(str(content.number), os.path.join(stuff_dir, f"{stuff_id}.txt"))

    def _handle_image_content(self, content: ImageContent, stuff_id: str) -> None:
        # Save the image
        image_path = os.path.join(self.images_dir_path, f"{stuff_id}.{self.image_output_format}")
        if content.url.startswith("http"):
            image_bytes: bytes = fetch_file_from_url_httpx(url=content.url, timeout=10)
            with open(image_path, "wb") as image_file:
                image_file.write(image_bytes)
        else:
            image_path = content.url

        ensure_path(self.images_dir_path)

    def _handle_html_content(self, content: HtmlContent, stuff_id: str) -> None:
        stuff_dir = os.path.join(self.result_dir_path, stuff_id)
        ensure_path(stuff_dir)
        # Save the raw HTML
        save_text_to_path(content.inner_html, os.path.join(stuff_dir, f"{stuff_id}.html"))
        # Save CSS class
        save_text_to_path(content.css_class, os.path.join(stuff_dir, f"{stuff_id}_css.txt"))

    def _handle_mermaid_content(self, content: MermaidContent, stuff_id: str) -> None:
        # Save the Mermaid code
        save_text_to_path(content.mermaid_code, os.path.join(self.result_dir_path, f"{stuff_id}.mmd"))

    def _handle_structured_content(self, content: StructuredContent, stuff_id: str) -> None:
        stuff_dir = os.path.join(self.result_dir_path, stuff_id)
        ensure_path(stuff_dir)
        # Save the structured content as JSON
        save_as_json_to_path(content, os.path.join(stuff_dir, f"{stuff_id}.json"))
        # Save rendered versions
        save_text_to_path(content.rendered_markdown(), os.path.join(stuff_dir, f"{stuff_id}.md"))

    def _handle_list_content(self, content: ListContent[StuffContent], stuff_id: str) -> None:
        stuff_dir = os.path.join(self.result_dir_path, stuff_id)
        ensure_path(stuff_dir)
        # Save each item in the list
        items_dir = os.path.join(stuff_dir, f"{stuff_id}_items")
        ensure_path(items_dir)
        for i, item in enumerate(content.items):
            item_dir = os.path.join(items_dir, f"item_{i}")
            ensure_path(item_dir)
            save_text_to_path(str(item), os.path.join(item_dir, f"{stuff_id}_item_{i}.txt"))

        # Save rendered versions of the full list
        save_text_to_path(content.rendered_markdown(), os.path.join(stuff_dir, f"{stuff_id}.md"))
        save_text_to_path(content.rendered_json(), os.path.join(stuff_dir, f"{stuff_id}.json"))
