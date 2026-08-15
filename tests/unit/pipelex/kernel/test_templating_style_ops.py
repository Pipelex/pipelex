"""Unit tests for the total templating-style resolver (kernel semantics, deck-free)."""

from pipelex.config import get_config
from pipelex.kernel.templating_style_ops import resolve_templating_style
from pipelex.tools.templating.templating_style import TagStyle, TemplatingStyle
from pipelex.tools.templating.text_format import TextFormat


class TestResolveTemplatingStyle:
    def test_none_resolves_to_config_default(self):
        """Totality: with nothing authored, the resolver returns the config default — never None."""
        resolved = resolve_templating_style(authored=None)
        assert resolved == get_config().inference.templating.default_templating_style

    def test_house_default_is_xml_plain(self):
        """Pins the shipped default declared in pipelex.toml: xml tags, plain text format."""
        resolved = resolve_templating_style(authored=None)
        assert resolved == TemplatingStyle(tag_style=TagStyle.XML, text_format=TextFormat.PLAIN)

    def test_authored_wins_over_config_default(self):
        authored = TemplatingStyle(tag_style=TagStyle.SQUARE_BRACKETS, text_format=TextFormat.MARKDOWN)
        assert resolve_templating_style(authored=authored) is authored
