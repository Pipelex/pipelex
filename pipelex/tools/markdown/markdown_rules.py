"""The rules by which the built-in PDF engine, and the formatting other document engines print from, read Markdown.

The built-in PDF engine (`pipelex/providers/reportlab/markdown_flowables.py`) and the formatting a document engine
prints from when it formats Markdown in its own format (`markdown_formatting.py`) both walk markdown-it's syntax tree,
and both read it by these rules:

- only an `http`, `https` or `mailto` target becomes a link, any other printing its text alone;
- the bullets of nested bullet lists alternate a bullet and an en dash by depth, and an ordered list is numbered
  from its own `start`;
- a heading has its level from its tag, a code block prints as written with its tabs expanded, and a table cell has
  the alignment its column's delimiter sets;
- an image is never fetched, and prints as `[image: alt]`.

The HTML conversion (`render_markdown_as_html`) is not one of them: it follows markdown-it's own rules, which keep a
link to any target but a `javascript:`, `vbscript:`, `file:` or non-image `data:` one, a relative one included, and
show an image as an `<img>`.

They live here, under `tools/`, rather than in the document engine contract or the PDF engine, because both read
them and the contract (`pipelex/cogt/doc_gen/formatted_markdown.py`) builds on `tools/` rather than the other way
round.
"""

from typing import Final, Literal, TypeAlias
from urllib.parse import urlsplit

from markdown_it.tree import SyntaxTreeNode

LINKED_SCHEMES: Final = frozenset({"http", "https", "mailto"})

# The bullets of nested bullet lists, by depth, alternating: a bullet and an en dash.
_BULLETS: Final = ("•", "–")

CellAlignment: TypeAlias = Literal["left", "center", "right"]


def is_linked_href(*, href: str) -> bool:
    """Whether a link target becomes a link in a document: only `http`, `https` and `mailto` do."""
    try:
        scheme = urlsplit(href.strip()).scheme
    except ValueError:
        return False
    return scheme.lower() in LINKED_SCHEMES


def list_bullet(*, depth: int) -> str:
    """The bullet of a bullet list `depth` lists deep, 1 for a top-level list: a bullet and an en dash, alternating."""
    return _BULLETS[(depth - 1) % len(_BULLETS)]


def list_start(*, start: str | float | None) -> int:
    """The number an ordered list starts at, from the `start` markdown-it reads off its first item: 1 when it has none."""
    if start is None:
        return 1
    try:
        return int(start)
    except (ValueError, OverflowError):
        return 1


def heading_level(*, tag: str) -> int:
    """A heading's level from its tag, `h1` to `h6`: 6 for any other tag."""
    if len(tag) == 2 and tag[0] == "h" and tag[1].isdigit():
        return int(tag[1])
    return 6


def code_text(*, content: str) -> str:
    """A code block's text as it prints: as written, without its last line feed, tabs expanded to four spaces."""
    return content.rstrip("\n").expandtabs(4)


def cell_alignment(*, node: SyntaxTreeNode) -> CellAlignment | None:
    """The alignment a table cell's column sets with the colons of its delimiter row, or None when it sets none.

    markdown-it writes it as the cell's `style`: `| :-- |` is left, `| :-: |` is center and `| --: |` is right.
    """
    style = node.attrs.get("style")
    if not isinstance(style, str):
        return None
    if "text-align:right" in style:
        return "right"
    if "text-align:center" in style:
        return "center"
    if "text-align:left" in style:
        return "left"
    return None


def plain_text(*, nodes: list[SyntaxTreeNode]) -> str:
    """The text of Markdown nodes without their markup, as it reads once printed, an image as `[image: alt]`."""
    parts: list[str] = []
    for node in nodes:
        match node.type:
            case "softbreak":
                parts.append(" ")
            case "hardbreak":
                parts.append("\n")
            case "image":
                parts.append(f"[image: {plain_text(nodes=node.children).strip() or node.content}]")
            case _:
                if node.children:
                    parts.append(plain_text(nodes=node.children))
                else:
                    parts.append(node.content)
    return "".join(parts)
