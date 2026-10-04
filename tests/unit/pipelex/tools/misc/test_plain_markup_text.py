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
            # A style alias: Rich normalizes both sides of the pair, so `b` and `bold` are one style to it.
            "[b]an alias[/bold] pair",
            "[bold]the other way[/b] round",
            "[i]italic[/italic] by its alias",
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
        """What the ``poor`` mode prints as a title is what Rich's panel title would read.

        Compared against ``emoji=False`` deliberately: substituting an emoji code needs Rich's own code table,
        so the Rich-free reading leaves ``:rocket:`` as written. That difference is a documented behaviour
        change of the ``poor`` mode rather than a divergence this test is meant to catch.
        """
        assert plain_markup_text(markup=markup) == Text.from_markup(markup, emoji=False).plain

    @pytest.mark.parametrize(
        "markup",
        [
            "a closing tag [/bold] with nothing open",
            "an implicit close [/] with nothing open",
            "text [green]then[/green] a stray [/red] close",
        ],
    )
    def test_refuses_a_close_with_nothing_open(self, markup: str) -> None:
        """The one thing that cannot be read as tags at all: a closing tag where nothing is open.

        Rich raises ``MarkupError`` here too, and the caller keeps the title as it was written.
        """
        with pytest.raises(MarkupError):
            Text.from_markup(markup)
        assert plain_markup_text(markup=markup) is None

    @pytest.mark.parametrize(
        ("markup", "expected"),
        [
            # Rich matches a closing tag against the style it names, which needs its style grammar. This
            # reading tracks nesting depth instead, so it closes the innermost open tag whatever it is named.
            ("[bold]a mismatched[/italic] close", "a mismatched close"),
            ("[red on blue]a reordered pair[/blue on red]", "a reordered pair"),
            # Rich parses a `@` tag's parameters and refuses malformed ones. This reading drops them unread.
            ("[@click=foo(]a malformed handler[/@click]", "a malformed handler"),
        ],
    )
    def test_is_deliberately_more_permissive_than_rich(self, markup: str, expected: str) -> None:
        """Where Rich refuses markup this reading accepts, it strips the tags rather than keeping them.

        The ``poor`` mode prints whatever happens, and a title that reads as text is better than one that
        prints its own tags. Accepting more than Rich costs a reader nothing; refusing more would cost them
        the title.
        """
        with pytest.raises(MarkupError):
            Text.from_markup(markup)
        assert plain_markup_text(markup=markup) == expected
