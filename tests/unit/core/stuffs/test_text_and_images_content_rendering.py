import re

from pytest import CaptureFixture

from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.tools.misc.pretty import pretty_print


def remove_ansi_escape_codes(text: str) -> str:
    """Remove ANSI color codes from terminal output."""
    ansi_escape = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
    return ansi_escape.sub("", text)


class TestTextAndImagesContentRendering:
    """Test TextAndImagesContent.rendered_pretty()"""

    def test_text_only(self, capsys: CaptureFixture[str]):
        """Test rendering text without images."""
        content = TextAndImagesContent(text=TextContent(text="Hello world"), images=None)
        # Note: title is passed to pretty_print, not rendered_pretty for TextAndImagesContent
        pretty_print(content.rendered_pretty())

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.out)

        assert "Hello world" in output

    def test_text_and_images(self, capsys: CaptureFixture[str]):
        """Test rendering text with images."""
        content = TextAndImagesContent(
            text=TextContent(text="Document content"),
            images=[
                ImageContent(url="https://example.com/image1.png"),
                ImageContent(url="https://example.com/image2.png", caption="Second image"),
            ],
        )
        pretty_print(content.rendered_pretty())

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.out)

        assert "Document content" in output
        assert "Images" in output
        assert "image1.png" in output
        assert "image2.png" in output
        assert "Second image" in output

    def test_images_only(self, capsys: CaptureFixture[str]):
        """Test rendering images without text."""
        content = TextAndImagesContent(
            text=None,
            images=[ImageContent(url="https://example.com/photo.jpg")],
        )
        pretty_print(content.rendered_pretty())

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.out)

        assert "photo.jpg" in output

    def test_empty_text_and_images(self, capsys: CaptureFixture[str]):
        """Test rendering empty text and images."""
        content = TextAndImagesContent(text=None, images=None)
        pretty_print(content.rendered_pretty())

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.out)

        # TextAndImagesContent returns a Text object with "(empty)"
        assert "empty" in output.lower()
