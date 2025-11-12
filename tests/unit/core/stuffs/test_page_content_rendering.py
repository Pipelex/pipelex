import re

from pytest import CaptureFixture

from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.page_content import PageContent
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.tools.misc.pretty import pretty_print


def remove_ansi_escape_codes(text: str) -> str:
    """Remove ANSI color codes from terminal output."""
    ansi_escape = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
    return ansi_escape.sub("", text)


class TestPageContentRendering:
    """Test PageContent.rendered_pretty()"""

    def test_page_content_without_view(self, capsys: CaptureFixture[str]):
        """Test rendering page content without page view."""
        page = PageContent(
            text_and_images=TextAndImagesContent(
                text=TextContent(text="Page text"),
                images=None,
            ),
            page_view=None,
        )
        pretty_print(page.rendered_pretty(title="Page"))

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.out)

        assert "Page" in output
        assert "Page text" in output

    def test_page_content_with_view(self, capsys: CaptureFixture[str]):
        """Test rendering page content with page view."""
        page = PageContent(
            text_and_images=TextAndImagesContent(
                text=TextContent(text="Page text"),
                images=None,
            ),
            page_view=ImageContent(url="https://example.com/page_screenshot.png"),
        )
        pretty_print(page.rendered_pretty())

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.out)

        assert "Page text" in output
        assert "Page View" in output
        assert "page_screenshot.png" in output
