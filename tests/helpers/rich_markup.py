"""What Rich would read as console markup in a piece of text: the tags it applies as styling rather than prints.

A tag-shaped span is not markup by its shape alone. Rich's tag pattern also matches the ``[int]`` of ``list[int]``,
a ``[cycle]`` marker and a backend's table, ``[openai]``, yet none of them names a style, and a log message holding
one is plain text that prints as written. So a tag counts as markup only when Rich would style with it: a closing
tag, ``[/]`` or ``[/red]``; an ``@`` handler, ``[@click=app.bell]``; or an opening tag whose text Rich parses as a
style, ``[bold]``, ``[on blue]``, ``[link=https://pipelex.com]``, or that names a style of Rich's default theme,
``[repr.number]``. A tag escaped with a backslash is text. It is the rule the log-call guard holds the literals of
Pipelex's log calls to, applied here to what a run actually logged.
"""

from __future__ import annotations

from rich.default_styles import DEFAULT_STYLES
from rich.errors import StyleSyntaxError
from rich.markup import RE_TAGS
from rich.style import Style


def _reads_as_style(*, tag_text: str) -> bool:
    """Whether Rich applies a tag's text as styling, rather than leaving the reader a bracketed word.

    A closing tag and an ``@`` handler are markup whatever they name. An opening tag is markup when it names a style
    of the default theme, or when Rich parses its text as a style, ``name=parameters`` read the way Rich's own
    ``Tag`` reads it.
    """
    if tag_text.startswith(("/", "@")):
        return True
    if tag_text in DEFAULT_STYLES:
        return True
    name, separator, parameters = tag_text.partition("=")
    style_text = f"{name} {parameters}" if separator else name
    try:
        Style.parse(style_text)
    except StyleSyntaxError:
        return False
    return True


def find_markup_tags(*, text: str) -> list[str]:
    """The unescaped tags in the text that Rich would apply as markup, in order, each as written."""
    tags: list[str] = []
    for match in RE_TAGS.finditer(text):
        full_text, escapes, tag_text = match.groups()
        # An odd run of backslashes escapes the tag, which then prints as written.
        if len(escapes) % 2 == 1:
            continue
        if _reads_as_style(tag_text=tag_text):
            tags.append(full_text[len(escapes) :])
    return tags
