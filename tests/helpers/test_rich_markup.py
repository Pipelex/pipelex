from __future__ import annotations

import pytest

from pipelex.cli.dev_cli.commands.log_call_guard import find_markup_tags


class TestFindMarkupTags:
    @pytest.mark.parametrize(
        "text",
        [
            "Expected list[int], got str",
            "The content refers to itself: [cycle]",
            "Add 'enabled = false' under '[openai]' in '.pipelex/inference/backends.toml'",
            "[Errno 2] No such file or directory: 'graph.json'",
            "Read /work/[draft]/graph.json",
            "An escaped tag prints as written: \\[bold]",
            "Pipe run starts",
        ],
        ids=["a type", "the cycle marker", "a backend table", "an errno", "a bracketed path", "an escaped tag", "no bracket at all"],
    )
    def test_a_bracketed_word_rich_applies_no_style_for_is_not_markup(self, text: str) -> None:
        assert find_markup_tags(text=text) == []

    @pytest.mark.parametrize(
        ("text", "expected_tags"),
        [
            ("[bold]x[/bold]", ["[bold]", "[/bold]"]),
            ("[red]x[/]", ["[red]", "[/]"]),
            ("[link=https://x]y[/link]", ["[link=https://x]", "[/link]"]),
            ("Click [@click=app.bell]here", ["[@click=app.bell]"]),
            ("A number in [repr.number]the theme's style", ["[repr.number]"]),
            ("Expected list[int], got [on blue]str", ["[on blue]"]),
        ],
        ids=["a style and its closing tag", "a colour closed by the bare tag", "a link", "a handler", "a theme style", "beside a type"],
    )
    def test_a_tag_rich_would_style_with_is_markup(self, text: str, expected_tags: list[str]) -> None:
        assert find_markup_tags(text=text) == expected_tags
