"""A sourced answer lists each of its sources once.

A search provider can list one page more than once among the sources of a sourced answer, under addresses
that differ only in how they are written: `https://www.example.com/a` and `https://example.com/a`, the
same page over `http` and `https`, with and without a trailing `/`, or with and without a fragment
(`#section`). The search worker keeps the first entry for each page and drops the others, in the
provider's order, and the entry it keeps keeps its original address. Two addresses name the same page when
they are equal once each is reduced to its comparison key: `http` and `https` count as one scheme, the host
is lowercased and loses one leading `www.`, the fragment is dropped, one trailing `/` is dropped from the
path unless the path is `/` alone (a web address written with no path having the path `/`), and the query is
kept as it is. The rule is stated in the `PipeSearch`
documentation, so a consumer that deduplicates on display can apply the same one. Every search worker's
answer passes through here, so every provider gets it.

When the search asked for inline citations, the answer numbers them `[1]`, `[2]`, … as positions in the
provider's list of sources, counted from 1 in the order they arrive: Linkup documents its inline references
as corresponding to the sources in its response, and a real answer's citations support their sentences only
under that reading. Dropping an entry moves every later entry up, so each citation is renumbered to the
position its source holds in the shortened list, and a citation of a dropped duplicate points at the entry
kept for its page. A number that names no entry of the provider's list is left as written, and so is a number
inside code, as CommonMark reads the answer: the answer is parsed with the parser that renders it
(`markdown_parser.py`), so a code block, fenced or indented, is code at any depth of block quotes and lists,
and so is a code span, which opens on a run of backticks not escaped by a backslash, closes on the next run of
the same length, and never runs past the paragraph, heading, list item or table cell it opens in.
"""

import re
from bisect import bisect_right
from enum import StrEnum
from itertools import groupby
from typing import TYPE_CHECKING, Final, NamedTuple
from urllib.parse import urlsplit

from pipelex.core.stuffs.search_result_content import SearchResultContent
from pipelex.tools.markdown.markdown_parser import LINE_ENDING, get_markdown_parser

if TYPE_CHECKING:
    from pipelex.core.stuffs.document_content import DocumentContent

_CITATION_PATTERN = re.compile(r"\[([0-9]+)\]")
_BACKTICK_RUN_PATTERN = re.compile(r"`+")
_BACKSLASH = "\\"
# markdown-it cuts a table row into its cells at each `|` that does not directly follow a backslash, before it
# reads the code spans of each cell
_TABLE_CELL_SEPARATOR = "|"
_TABLE_CELL_SEPARATOR_PATTERN = re.compile(r"(?<!\\)\|")
_WEB_SCHEMES = frozenset({"http", "https"})
_WEB_SCHEME_KEY = "http"
_WWW_PREFIX = "www."


class _PageKey(NamedTuple):
    """What two addresses of the same page share, once the ways of writing that address are set aside."""

    scheme: str
    netloc: str
    path: str
    query: str


class _BlockKind(StrEnum):
    """What CommonMark reads a block of the answer's lines as, which decides where a citation can stand in it."""

    # A fenced or indented code block, whose lines are all code
    CODE = "code"
    # One block of text, such as a paragraph or a heading, whose code spans stay inside it
    TEXT = "text"
    # One row of a table, each of whose cells is a block of text of its own
    TABLE_ROW = "table_row"


class _LineBlock(NamedTuple):
    """The block a line of the answer belongs to, told apart from the blocks around it by its first line."""

    kind: _BlockKind
    first_line: int


# The parsed tokens that claim lines of the answer for a block, by token type; a table row's `tr_open` comes
# before the tokens of its cells, which share its line
_BLOCK_KIND_BY_TOKEN_TYPE: Final[dict[str, _BlockKind]] = {
    "fence": _BlockKind.CODE,
    "code_block": _BlockKind.CODE,
    "tr_open": _BlockKind.TABLE_ROW,
    "inline": _BlockKind.TEXT,
}


def deduplicate_search_sources(*, search_result: SearchResultContent, renumber_citations: bool) -> SearchResultContent:
    """List each source of a sourced answer once, renumbering the answer's inline citations to match.

    Args:
        search_result: The sourced answer as the provider's worker built it.
        renumber_citations: Whether the answer carries inline citations numbering the sources, which is
            what the search asked for with `include_inline_citations`. Without them, a bracketed number
            in the answer is the answer's own text and stays as written.

    Returns:
        The same result when no page repeats, or a copy listing each page once, at its first position and
        under its first address, with its citations renumbered when `renumber_citations` is set.
    """
    kept_sources: list[DocumentContent] = []
    kept_position_by_page: dict[_PageKey, int] = {}
    new_position_by_old_position: dict[int, int] = {}
    for old_index, source in enumerate(search_result.sources):
        page_key = _page_key(url=source.url)
        kept_position = kept_position_by_page.get(page_key)
        if kept_position is None:
            kept_sources.append(source)
            kept_position = len(kept_sources)
            kept_position_by_page[page_key] = kept_position
        new_position_by_old_position[old_index + 1] = kept_position

    if len(kept_sources) == len(search_result.sources):
        return search_result

    answer = search_result.answer
    if renumber_citations:
        answer = _renumber_citations(answer=answer, new_position_by_old_position=new_position_by_old_position)
    return search_result.model_copy(update={"answer": answer, "sources": kept_sources})


def _page_key(*, url: str) -> _PageKey:
    """Reduce an address to the key two addresses of the same page share.

    `http` and `https` count as one scheme, the host is lowercased and loses one leading `www.`, the
    fragment is dropped, one trailing `/` is dropped from the path unless the path is `/` alone, and the
    query is kept as it is. A web address written with no path has the path `/`, as a URL parser reads
    it. Any other scheme, the user information and the port are kept as written.
    """
    # A URL's fragment starts at its first `#`, which cannot appear unescaped anywhere before it
    address = url.partition("#")[0]
    try:
        parts = urlsplit(address)
    except ValueError:
        # An address the parser refuses, such as a malformed IPv6 host, only matches itself
        return _PageKey(scheme="", netloc="", path=address, query="")

    scheme = _WEB_SCHEME_KEY if parts.scheme in _WEB_SCHEMES else parts.scheme
    user_info, at_sign, host_and_port = parts.netloc.rpartition("@")
    host_and_port = host_and_port.lower().removeprefix(_WWW_PREFIX)
    path = parts.path
    if not path and scheme == _WEB_SCHEME_KEY:
        # A web address written with no path names its site's root, which is the path `/`
        path = "/"
    elif len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    return _PageKey(scheme=scheme, netloc=f"{user_info}{at_sign}{host_and_port}", path=path, query=parts.query)


def _renumber_citations(*, answer: str, new_position_by_old_position: dict[int, int]) -> str:
    """Renumber the answer's citations outside its code, as CommonMark reads the answer.

    Each run of lines that one block holds is renumbered on its own: a code block's lines are left as
    written, a block of text is renumbered outside its code spans, a table row cell by cell, and lines no
    block holds, such as blank lines, are renumbered as they are. The lines keep their line endings.
    """
    # A line ends where markdown-it ends one, so the lines are counted as its tokens' `map` counts them
    line_bounds = [0, *(line_ending.end() for line_ending in LINE_ENDING.finditer(answer)), len(answer)]
    renumbered_parts: list[str] = []
    run_start = 0
    for block, block_lines in groupby(_block_of_each_line(answer=answer, line_count=len(line_bounds) - 1)):
        run_end = run_start + len(list(block_lines))
        renumbered_parts.append(
            _renumber_block(
                text=answer[line_bounds[run_start] : line_bounds[run_end]],
                block=block,
                new_position_by_old_position=new_position_by_old_position,
            )
        )
        run_start = run_end
    return "".join(renumbered_parts)


def _block_of_each_line(*, answer: str, line_count: int) -> list[_LineBlock | None]:
    """The block each line of the answer belongs to, as the parser that renders the answer reads it, or `None`.

    A line belongs to the first token that claims it, in the parser's order, so a table row's line belongs to
    the row rather than to its cells; a line no token claims, such as a blank line, a table's delimiter row or
    a link reference definition, belongs to no block.
    """
    block_of_each_line: list[_LineBlock | None] = [None] * line_count
    for token in get_markdown_parser().parse(answer):
        block_kind = _BLOCK_KIND_BY_TOKEN_TYPE.get(token.type)
        if block_kind is None or token.map is None:
            continue
        first_line, end_line = token.map
        block = _LineBlock(kind=block_kind, first_line=first_line)
        for line_index in range(first_line, end_line):
            if block_of_each_line[line_index] is None:
                block_of_each_line[line_index] = block
    return block_of_each_line


def _renumber_block(*, text: str, block: _LineBlock | None, new_position_by_old_position: dict[int, int]) -> str:
    """Renumber the citations of the lines one block holds, or of lines that no block holds when `block` is `None`."""
    if block is None:
        return _renumber_prose(text=text, new_position_by_old_position=new_position_by_old_position)
    match block.kind:
        case _BlockKind.CODE:
            return text
        case _BlockKind.TEXT:
            return _renumber_outside_code_spans(text=text, new_position_by_old_position=new_position_by_old_position)
        case _BlockKind.TABLE_ROW:
            renumbered_cells: list[str] = []
            for cell in _TABLE_CELL_SEPARATOR_PATTERN.split(text):
                renumbered_cells.append(_renumber_outside_code_spans(text=cell, new_position_by_old_position=new_position_by_old_position))
            return _TABLE_CELL_SEPARATOR.join(renumbered_cells)


def _renumber_outside_code_spans(*, text: str, new_position_by_old_position: dict[int, int]) -> str:
    """Renumber the citations of one block of text outside its code spans.

    A code span opens on a run of backticks and closes on the next run of exactly the same length, as in
    CommonMark; a run with no such closer is literal text. A backtick that follows an odd number of
    backslashes is escaped, so it is literal text and the rest of its run is a run of its own, while a closer
    is never escaped, since a backslash escapes nothing inside a code span.
    """
    backtick_runs = list(_BACKTICK_RUN_PATTERN.finditer(text))
    # The indices of the runs of each length, in the text's order, so an opener's closer is found without reading on
    run_indices_by_length: dict[int, list[int]] = {}
    for run_index, backtick_run in enumerate(backtick_runs):
        run_indices_by_length.setdefault(len(backtick_run.group(0)), []).append(run_index)

    renumbered_parts: list[str] = []
    prose_start = 0
    run_index = 0
    while run_index < len(backtick_runs):
        opening_run = backtick_runs[run_index]
        opening_start = opening_run.start()
        if _follows_odd_backslashes(text=text, position=opening_start):
            opening_start += 1
        closing_index = _closing_run_index(
            run_indices=run_indices_by_length.get(opening_run.end() - opening_start, []),
            opening_index=run_index,
        )
        if closing_index is None:
            run_index += 1
            continue
        renumbered_parts.append(_renumber_prose(text=text[prose_start:opening_start], new_position_by_old_position=new_position_by_old_position))
        prose_start = backtick_runs[closing_index].end()
        renumbered_parts.append(text[opening_start:prose_start])
        run_index = closing_index + 1
    renumbered_parts.append(_renumber_prose(text=text[prose_start:], new_position_by_old_position=new_position_by_old_position))
    return "".join(renumbered_parts)


def _follows_odd_backslashes(*, text: str, position: int) -> bool:
    """Whether the character at `position` follows an odd number of backslashes, the last of which escapes it."""
    backslashes_start = position
    while backslashes_start > 0 and text[backslashes_start - 1] == _BACKSLASH:
        backslashes_start -= 1
    return (position - backslashes_start) % 2 == 1


def _closing_run_index(*, run_indices: list[int], opening_index: int) -> int | None:
    """The first of `run_indices`, the indices of the runs as long as an opener, that comes after the opener."""
    later_position = bisect_right(run_indices, opening_index)
    if later_position == len(run_indices):
        return None
    return run_indices[later_position]


def _renumber_prose(*, text: str, new_position_by_old_position: dict[int, int]) -> str:
    renumbered_parts: list[str] = []
    cursor = 0
    for citation in _CITATION_PATTERN.finditer(text):
        old_position = int(citation.group(1))
        new_position = new_position_by_old_position.get(old_position)
        if new_position is None or new_position == old_position:
            continue
        renumbered_parts.append(text[cursor : citation.start()])
        renumbered_parts.append(f"[{new_position}]")
        cursor = citation.end()
    renumbered_parts.append(text[cursor:])
    return "".join(renumbered_parts)
