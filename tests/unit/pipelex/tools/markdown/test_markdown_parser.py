import random

import pytest
from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode

from pipelex.tools.markdown.markdown_parser import (
    MAX_INLINE_NESTING,
    get_markdown_parser,
    html_length_bound,
    markdown_syntax_tree,
    render_markdown_as_html,
    table_cells_bound,
)
from pipelex.tools.markdown.markdown_rules import plain_text
from tests.unit.pipelex.tools.markdown.test_data import MarkdownFormattingTestData

# The pieces the generated documents are made of: emphasis and its unmatched delimiters, links, references and
# images, tables in and out of containers, padded rows, code, escapes, and every line ending markdown-it knows,
# with characters `str.splitlines` would break at and markdown-it does not.
_PIECES = [
    "*",
    "_",
    "~~",
    "**",
    "a",
    " ",
    "\n",
    "\r",
    "\r\n",
    "\n\n",
    "[",
    "]",
    "(",
    ")",
    "`",
    "\\*",
    "&",
    "<",
    '"',
    'https://a.co/&"x',
    "|",
    "| ",
    "-",
    "-|",
    "|-|",
    ":-",
    "# ",
    "> ",
    ">",
    "  ",
    "\t",
    "1. ",
    "- ",
    "![",
    "](/i.png)",
    "]: /u",
    "[r]",
    "[r][]",
    '\n[r]: /é&"<x> "t&"\n',
    "```py&\n",
    " ",
    "\x85",
    "|a|b|c|\n|-|:-:|-:|\n|1\n",
    "> |a|b|\n> |-|-|\n> |c\n",
    "- |a|b|\n  |-|-|\n  |c\n",
    "![![x](/in)](/out)",
]


def _generated_documents() -> list[str]:
    generator = random.Random(20261002)
    return ["".join(generator.choice(_PIECES) for _ in range(generator.randint(1, 120))) for _ in range(1000)]


def _stock_parser() -> MarkdownIt:
    parser = MarkdownIt("commonmark", {"html": False, "linkify": True}).enable(["table", "strikethrough", "linkify"])
    linkify = parser.linkify
    assert linkify is not None
    linkify.set({"fuzzy_link": False, "fuzzy_email": False})  # pyright: ignore[reportUnknownMemberType]
    return parser


def _deepest_inline_nesting(*, tree: SyntaxTreeNode) -> int:
    """How many emphasis, strong emphasis, strikethrough and link nodes the deepest path of a syntax tree crosses."""
    deepest = 0
    pending: list[tuple[SyntaxTreeNode, int]] = [(tree, 0)]
    while pending:
        node, depth = pending.pop()
        depth += node.type in {"em", "strong", "s", "link"}
        deepest = max(deepest, depth)
        pending.extend((child, depth) for child in node.children)
    return deepest


class TestMarkdownParser:
    def test_only_a_url_with_a_scheme_becomes_a_link(self) -> None:
        html = render_markdown_as_html("See https://example.com/docs, README.md, www.example.com and ada@example.com.")
        assert '<a href="https://example.com/docs">' in html
        assert "README.md" in html
        assert html.count("<a ") == 1

    def test_an_explicit_link_keeps_its_target_in_html_whatever_its_scheme(self) -> None:
        html = render_markdown_as_html("[the readme](README.md), [files](ftp://example.com/file) and ![a chart](chart.png)")
        assert '<a href="README.md">the readme</a>' in html
        assert '<a href="ftp://example.com/file">files</a>' in html
        assert '<img src="chart.png" alt="a chart" />' in html

    def test_tables_and_strikethrough_are_formatted(self) -> None:
        html = render_markdown_as_html("| a | b |\n| - | - |\n| 1 | 2 |\n\n~~gone~~")
        assert "<table>" in html
        assert "<s>gone</s>" in html

    @pytest.mark.parametrize(
        ("markdown_text", "expected_text"),
        [
            (MarkdownFormattingTestData.DEEP_EMPHASIS, MarkdownFormattingTestData.DEEP_EMPHASIS_TEXT),
            (MarkdownFormattingTestData.DEEP_MIXED_EMPHASIS, MarkdownFormattingTestData.DEEP_MIXED_EMPHASIS_TEXT),
        ],
    )
    def test_a_syntax_tree_caps_inline_nesting_and_keeps_the_text(self, markdown_text: str, expected_text: str) -> None:
        tree = markdown_syntax_tree(tokens=get_markdown_parser().parse(markdown_text))
        assert _deepest_inline_nesting(tree=tree) == MAX_INLINE_NESTING
        assert plain_text(nodes=tree.children) == expected_text

    def test_an_image_past_the_cap_prints_its_alt_text_as_written(self) -> None:
        markdown_text = "*a " * MAX_INLINE_NESTING + "![a *chart*](chart.png)" + " c*" * MAX_INLINE_NESTING
        tree = markdown_syntax_tree(tokens=get_markdown_parser().parse(markdown_text))
        assert "[image: a *chart*]" in plain_text(nodes=tree.children)

    def test_nesting_within_the_cap_is_left_as_parsed(self) -> None:
        parser = get_markdown_parser()
        nested_to_the_cap = "*a " * MAX_INLINE_NESTING + "b" + " c*" * MAX_INLINE_NESTING
        for document in [*_generated_documents(), nested_to_the_cap]:
            tokens = parser.parse(document)
            expected_html = parser.renderer.render(tokens, parser.options, {})
            markdown_syntax_tree(tokens=tokens)
            assert parser.renderer.render(tokens, parser.options, {}) == expected_html, repr(document)

    def test_joining_fragments_renders_as_markdown_it_does(self) -> None:
        stock = _stock_parser()
        parser = get_markdown_parser()
        assert [document for document in _generated_documents() if parser.render(document) != stock.render(document)] == []

    def test_html_length_bound_is_never_below_the_html(self) -> None:
        parser = get_markdown_parser()
        for document in _generated_documents():
            tokens = parser.parse(document)
            assert html_length_bound(tokens=tokens) >= len(parser.renderer.render(tokens, parser.options, {})), repr(document)

    def test_table_cells_bound_is_never_below_the_cells(self) -> None:
        parser = get_markdown_parser()
        for document in _generated_documents():
            cells = sum(1 for token in parser.parse(document) if token.type in {"th_open", "td_open"})
            assert table_cells_bound(markdown_text=document) >= cells, repr(document)

    def test_a_reused_reference_is_counted_at_every_use(self) -> None:
        document = "[a][r] " * 1000 + "\n\n[r]: /" + "y" * 10_000
        assert html_length_bound(tokens=get_markdown_parser().parse(document)) >= 1000 * 10_000

    def test_padded_cells_are_counted(self) -> None:
        document = "|" + "a|" * 200 + "\r|" + "-|" * 200 + "\r" + "|a\r" * 300
        assert table_cells_bound(markdown_text=document) >= 200 * 301
