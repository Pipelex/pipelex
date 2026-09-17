import pytest
from rich.errors import MarkupError
from rich.text import Text

from pipelex.tools.misc.pretty import plain_markup_text


class TestPlainMarkupText:
    @pytest.mark.parametrize(
        "markup",
        [
            "",
            "no markup at all",
            "Output of pipe [red]greet[/red] → [bold cyan]Text[/bold cyan]",
            "[bold]nested [italic]styles[/italic] close[/]",
            "implicit [green]close[/]",
            "[bold red]order[/red bold] does not matter",
            "[bold]case[/BOLD] does not matter in a closing tag",
            "a [link=https://pipelex.com]link[/link] with parameters",
            "an unclosed [yellow]tag is fine",
            r"an escaped \[bold] tag",
            r"a literal backslash \\[bold]then a tag[/bold]",
            "brackets that are no tag: [1, 2, 3] and [A] and [ ]",
            r"an open brace escape \[ alone",
            "a list[str] type and dict[str, Any]",
        ],
    )
    def test_renders_the_plain_text_rich_renders(self, markup: str) -> None:
        """What the ``poor`` mode prints as a title is what Rich's panel title would read."""
        assert plain_markup_text(markup=markup) == Text.from_markup(markup, emoji=False).plain

    @pytest.mark.parametrize(
        "markup",
        [
            "a closing tag [/bold] with nothing open",
            "an implicit close [/] with nothing open",
            "[bold]a mismatched[/italic] close",
        ],
    )
    def test_refuses_the_markup_rich_refuses(self, markup: str) -> None:
        """Where Rich raises ``MarkupError``, the Rich-free reading says so with ``None``, and the caller keeps the title as written."""
        with pytest.raises(MarkupError):
            Text.from_markup(markup)
        assert plain_markup_text(markup=markup) is None
