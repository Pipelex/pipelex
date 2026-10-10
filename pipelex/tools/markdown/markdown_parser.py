"""The one Markdown parser Pipelex formats Markdown with, whatever it turns it into.

The `markdown` filter of HTML templates, the `Markdown` concept's HTML view and the built-in PDF engine all
read Markdown an LLM or a person wrote, so they parse it the same way, here:

- CommonMark, with tables and strikethrough, which LLM reports use;
- raw HTML disabled, so HTML inside the Markdown shows as text rather than entering the document;
- bare URLs linked, but only those with a scheme: markdown-it's default fuzzy matching links `README.md` to
  `http://README.md` and `config.py` to `http://config.py`, `.md` and `.py` being country domains, so fuzzy
  links and fuzzy emails are off, and `www.` addresses and bare emails stay text.

The parser joins the text fragments emphasis leaves behind in one pass (`_join_text_fragments`), where
markdown-it's own rule holds a copy of every prefix of a run of fragments at once: 64,000 characters of
unclosed `**a ` peaked at 1.5 GB with it and at 19 MB with this one, for the same tokens.

A conversion to HTML that a template sets off is charged to that template's render budget
(`jinja2_render_budget.py`), wherever it happens: the `markdown` filter, and markupsafe's `__html__`, which
converts a Markdown value whenever an HTML template prints, joins or formats one. It costs far more than the
bytes it produces, and can produce far more than it reads, so it is charged before it parses, for every
character of its source and every cell of its tables (`table_cells_bound`), since the table rule pads a short
row with empty cells; and its output, bounded from the parsed tokens (`html_length_bound`), must fit what is
left before it renders, since a reference link's destination and title are written once and printed at
every link that uses the reference. The formatting a document engine prints from (`markdown_formatting.py`) is
charged the same way, so both parse through `charged_parse`, which holds that order.

A converter that walks the syntax tree rather than the flat tokens, the built-in PDF engine and that formatting,
builds it with `markdown_syntax_tree`, which caps how deep inline markup nests first (`cap_inline_nesting`):
markdown-it caps the nesting of blocks, but not that of emphasis, and the tree and every walk of it recurse once
per level, so four hundred nested `*a ` would overflow Python's stack.
"""

import re
from collections.abc import Sequence
from functools import cache
from typing import TYPE_CHECKING, Any, Final, NamedTuple, Protocol

from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode

from pipelex.tools.jinja2.jinja2_render_budget import MARKDOWN_UNITS_PER_CHARACTER, RenderBudget, active_render_budget

if TYPE_CHECKING:
    from markdown_it.rules_inline import StateInline
    from markdown_it.token import Token

_CONVERTING: Final = "converting Markdown to HTML"

# What the renderer writes around one token at most, besides its tag name: `<`, `</`, `>`, ` /`, a line
# feed, and for a code block `<pre><code class="language-">` and `</code></pre>`.
_TOKEN_MARKUP_UNITS: Final = 48

# The factor by which escaping can grow a text: `"` becomes `&quot;`.
_ESCAPE_FACTOR: Final = 6

# markdown-it's line endings (its `normalize` rule), and nothing else: `str.splitlines` would also break at
# characters markdown-it keeps inside a line.
_LINE_ENDING: Final = re.compile(r"\r\n?|\n")

# What a table's delimiter row is made of, once its container's indentation and `>` markers are left out.
_DELIMITER_ROW_CHARACTERS: Final = frozenset("|-: \t")

# How deep inline markup may nest in a syntax tree, emphasis inside emphasis inside a link, an image's alt text one
# level below the image: far beyond what a written text nests, and far within Python's stack for a walk of the tree.
MAX_INLINE_NESTING: Final = 50


@cache
def get_markdown_parser() -> MarkdownIt:
    """The shared parser, built once. Parsing and rendering keep no state between calls, so it is shared freely."""
    parser = MarkdownIt("commonmark", {"html": False, "linkify": True}).enable(["table", "strikethrough", "linkify"])
    linkify = parser.linkify
    if linkify is None:
        msg = "markdown-it-py found no linkify-it-py: Pipelex requires markdown-it-py[linkify]."
        raise RuntimeError(msg)
    linkify.set({"fuzzy_link": False, "fuzzy_email": False})  # pyright: ignore[reportUnknownMemberType]
    parser.inline.ruler2.at("fragments_join", _join_text_fragments)
    return parser


def _join_text_fragments(state: "StateInline") -> None:
    """markdown-it's `fragments_join`, joining each run of adjacent text tokens once instead of pair by pair.

    Emphasis and strikethrough leave each unmatched delimiter as a text token of its own, which this joins
    with the text around it, and it recalculates every token's level, since emphasis turned some text tokens
    into tags. The last token of each run keeps the run's text, as with markdown-it's rule, which joins a run
    pair by pair and leaves every token of it holding the text joined so far until the run is dropped.
    """
    tokens = state.tokens
    count = len(tokens)
    kept: list[Token] = []
    run: list[str] = []
    level = 0
    for index, token in enumerate(tokens):
        if token.nesting < 0:
            level -= 1
        token.level = level
        if token.nesting > 0:
            level += 1
        if token.type == "text" and index + 1 < count and tokens[index + 1].type == "text":
            run.append(token.content)
            continue
        if run:
            run.append(token.content)
            token.content = "".join(run)
            run.clear()
        kept.append(token)
    tokens[:] = kept


def render_markdown_as_html(markdown_text: str) -> str:
    """Markdown as an HTML fragment, with any raw HTML in the source escaped.

    Inside a template render, the conversion is charged to the render's budget, which refuses it with
    `RenderBudgetExceededError` before it parses a source, or renders an output, larger than what is left.
    """
    parser = get_markdown_parser()
    budget = active_render_budget()
    if budget is None:
        html: str = parser.render(markdown_text)
        return html
    parsed = charged_parse(markdown_text=markdown_text, budget=budget, operation=_CONVERTING, output_bound=html_length_bound)
    rendered: str = parser.renderer.render(parsed.tokens, parser.options, parsed.env)
    budget.charge(units=len(rendered), operation=_CONVERTING)
    return rendered


class TokensBound(Protocol):
    """At most the work units of what a conversion builds out of parsed tokens, taken without building it."""

    def __call__(self, *, tokens: Sequence["Token"]) -> int: ...


class ParsedMarkdown(NamedTuple):
    """A Markdown text's tokens, and the environment the parser filled, holding its reference definitions."""

    tokens: list["Token"]
    env: dict[str, Any]


def charged_parse(*, markdown_text: str, budget: RenderBudget, operation: str, output_bound: TokensBound) -> ParsedMarkdown:
    """Parse a Markdown text for a conversion charged to `budget`, refusing it at the first step the budget cannot afford.

    In this order: its length, before anything reads it, since the table scan reads every line; then the cells of its
    tables, before the parser pads them (`table_cells_bound`); then the parse; and then what the conversion builds out
    of the tokens, bounded from them by `output_bound`, must fit what is left. The caller builds its output and
    charges what it built.

    Raises:
        RenderBudgetExceededError: a step would overdraw the budget, `operation` naming the conversion.
    """
    budget.charge(units=MARKDOWN_UNITS_PER_CHARACTER * len(markdown_text), operation=operation)
    budget.charge(units=MARKDOWN_UNITS_PER_CHARACTER * table_cells_bound(markdown_text=markdown_text), operation=operation)
    env: dict[str, Any] = {}
    tokens = get_markdown_parser().parse(markdown_text, env)
    budget.afford(units=output_bound(tokens=tokens), operation=operation)
    return ParsedMarkdown(tokens=tokens, env=env)


def markdown_syntax_tree(*, tokens: Sequence["Token"]) -> SyntaxTreeNode:
    """The syntax tree of parsed tokens, their inline nesting capped first (`cap_inline_nesting`)."""
    cap_inline_nesting(tokens=tokens)
    return SyntaxTreeNode(tokens)


def cap_inline_nesting(*, tokens: Sequence["Token"]) -> None:
    """Drop the inline markup of `tokens` that nests deeper than `MAX_INLINE_NESTING`, keeping its text.

    markdown-it caps the nesting of blocks at twenty, but emphasis is paired up after its delimiters are read, so it
    nests as deep as the text asks: four hundred `*a ` before a word and four hundred ` c*` after it nest four hundred
    deep. The cap walks the flat tokens, each inline token's children and each image's, the alt text, one level below
    the image; past it, an opening token is dropped with its closing one, and an image keeps no children, printing its
    alt text as written. The tokens are changed in place.
    """
    pending: list[tuple[Token, int]] = [(token, 0) for token in tokens if token.children]
    while pending:
        parent, depth = pending.pop()
        kept: list[Token] = []
        # For each opening token not yet closed, whether it was dropped, so its closing token is dropped with it.
        open_dropped: list[bool] = []
        for child in parent.children or []:
            if child.nesting > 0:
                is_dropped = depth >= MAX_INLINE_NESTING
                open_dropped.append(is_dropped)
                if is_dropped:
                    continue
                depth += 1
            elif child.nesting < 0 and open_dropped:
                if open_dropped.pop():
                    continue
                depth -= 1
            if child.children:
                if depth + 1 > MAX_INLINE_NESTING:
                    child.children = None
                else:
                    pending.append((child, depth + 1))
            kept.append(child)
        parent.children = kept


def table_cells_bound(*, markdown_text: str) -> int:
    """At most the number of cells the tables of `markdown_text` parse into, taken from its lines.

    The table rule gives every row as many cells as its header, padding a short row with empty ones, so a
    table costs the parser its cells rather than its characters: a header of two hundred columns over three
    hundred one-character rows makes sixty thousand cells, about sixty megabytes of tokens, out of two
    kilobytes of text. A table needs a delimiter row, a line of `|`, `-`, `:`, spaces and tabs under its
    header once its container's indentation and `>` markers are left out, with at most one column more than
    it has `|`; and its rows end at the latest at the next blank line.
    """
    total = 0
    # Read from the bottom: the lines under the current one, down to the next blank line.
    lines_below = 0
    for line in reversed(_LINE_ENDING.split(markdown_text)):
        if not line.strip():
            lines_below = 0
            continue
        content = line.lstrip(" \t>")
        if content[:1] in {"|", "-", ":"} and "-" in content and _DELIMITER_ROW_CHARACTERS.issuperset(content):
            # The header row, and every row down to the next blank line.
            total += (content.count("|") + 1) * (lines_below + 1)
        lines_below += 1
    return total


def html_length_bound(*, tokens: Sequence["Token"]) -> int:
    """At most the length of the HTML the renderer makes of `tokens`, taken without rendering them.

    Every token counts its tag, its attributes and its content as if all were escaped, and an image counts
    once more the text of the tokens it holds, which becomes its `alt`. A token holds a reference link's
    destination and title as it prints them, so a reference used ten thousand times is counted ten thousand
    times, while the parsed tokens share one copy of it.
    """
    total = 0
    pending: list[Sequence[Token]] = [tokens]
    while pending:
        for token in pending.pop():
            total += _TOKEN_MARKUP_UNITS + 2 * len(token.tag) + _ESCAPE_FACTOR * (len(token.content) + len(token.info))
            for key, value in token.attrItems():
                total += len(key) + 4 + _ESCAPE_FACTOR * len(str(value))
            if token.children:
                pending.append(token.children)
                if token.type == "image":
                    total += _ESCAPE_FACTOR * _inline_text_length(tokens=token.children)
    return total


def _inline_text_length(*, tokens: Sequence["Token"]) -> int:
    """The length of the text an image's `alt` is made of: its text, and that of the images inside it."""
    total = 0
    pending: list[Sequence[Token]] = [tokens]
    while pending:
        for token in pending.pop():
            if token.type == "text":
                total += len(token.content)
            elif token.type == "softbreak":
                total += 1
            elif token.type == "image" and token.children:
                pending.append(token.children)
    return total
