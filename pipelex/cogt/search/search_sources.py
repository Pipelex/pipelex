"""A sourced answer lists each of its sources once.

A search provider can list one address more than once among the sources of a sourced answer: the same
page cited for two passages of the answer, or once with a fragment (`#section`) and once without. The
search worker keeps the first entry for each address and drops the others, in the provider's order,
comparing addresses with their fragment removed, since a fragment names a place in a page and not another
page. Every search worker's answer passes through here, so every provider gets the same rule.

When the search asked for inline citations, the answer numbers them `[1]`, `[2]`, … from 1, read here as
positions in the provider's list of sources, the only list its response carries; the provider's SDK
documents the flag that asks for them but not their format, so that reading is this module's. Dropping an entry moves
every later entry up, so each citation is renumbered to the position its source holds in the shortened
list, and a citation of a dropped duplicate points at the entry kept for its address. Text inside a
Markdown code span or a fenced code block is code rather than a citation and is never renumbered, and a
number that names no entry of the provider's list is left as written.
"""

import re
from typing import TYPE_CHECKING

from pipelex.core.stuffs.search_result_content import SearchResultContent

if TYPE_CHECKING:
    from pipelex.core.stuffs.document_content import DocumentContent

_CITATION_PATTERN = re.compile(r"\[([0-9]+)\]")
_BACKTICK_RUN_PATTERN = re.compile(r"`+")
_FENCE_OPENING_PATTERN = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_MAX_FENCE_INDENT = 3


def deduplicate_search_sources(*, search_result: SearchResultContent, renumber_citations: bool) -> SearchResultContent:
    """List each source of a sourced answer once, renumbering the answer's inline citations to match.

    Args:
        search_result: The sourced answer as the provider's worker built it.
        renumber_citations: Whether the answer carries inline citations numbering the sources, which is
            what the search asked for with `include_inline_citations`. Without them, a bracketed number
            in the answer is the answer's own text and stays as written.

    Returns:
        The same result when no address repeats, or a copy listing each address once, at its first
        position, with its citations renumbered when `renumber_citations` is set.
    """
    kept_sources: list[DocumentContent] = []
    kept_position_by_address: dict[str, int] = {}
    new_position_by_old_position: dict[int, int] = {}
    for old_index, source in enumerate(search_result.sources):
        address = _address_without_fragment(url=source.url)
        kept_position = kept_position_by_address.get(address)
        if kept_position is None:
            kept_sources.append(source)
            kept_position = len(kept_sources)
            kept_position_by_address[address] = kept_position
        new_position_by_old_position[old_index + 1] = kept_position

    if len(kept_sources) == len(search_result.sources):
        return search_result

    answer = search_result.answer
    if renumber_citations:
        answer = _renumber_citations(answer=answer, new_position_by_old_position=new_position_by_old_position)
    return search_result.model_copy(update={"answer": answer, "sources": kept_sources})


def _address_without_fragment(*, url: str) -> str:
    # A URL's fragment starts at its first `#`, which cannot appear unescaped anywhere before it
    return url.partition("#")[0]


def _renumber_citations(*, answer: str, new_position_by_old_position: dict[int, int]) -> str:
    renumbered_parts: list[str] = []
    for segment, is_code_block in _split_fenced_code_blocks(text=answer):
        if is_code_block:
            renumbered_parts.append(segment)
        else:
            renumbered_parts.append(_renumber_outside_code_spans(text=segment, new_position_by_old_position=new_position_by_old_position))
    return "".join(renumbered_parts)


def _split_fenced_code_blocks(*, text: str) -> list[tuple[str, bool]]:
    """Cut the text into runs of lines, each flagged as a fenced code block or not, which join back into the text.

    A fence opens on a line indented by at most three spaces with three or more backticks or tildes, and
    closes on a line of the same character at least as long, as in CommonMark; a fence never closed runs
    to the end of the text.
    """
    segments: list[tuple[str, bool]] = []
    current_lines: list[str] = []
    opening_fence: str | None = None
    for line in text.splitlines(keepends=True):
        if opening_fence is None:
            fence = _opening_fence(line=line)
            if fence is None:
                current_lines.append(line)
                continue
            if current_lines:
                segments.append(("".join(current_lines), False))
            current_lines = [line]
            opening_fence = fence
        else:
            current_lines.append(line)
            if _closes_fence(line=line, opening_fence=opening_fence):
                segments.append(("".join(current_lines), True))
                current_lines = []
                opening_fence = None
    if current_lines:
        segments.append(("".join(current_lines), opening_fence is not None))
    return segments


def _opening_fence(*, line: str) -> str | None:
    fence_match = _FENCE_OPENING_PATTERN.match(line)
    if fence_match is None:
        return None
    fence = fence_match.group(1)
    # A backtick fence's info string holds no backtick: such a line opens a code span, not a block
    if fence.startswith("`") and "`" in line[fence_match.end() :]:
        return None
    return fence


def _closes_fence(*, line: str, opening_fence: str) -> bool:
    content = line.rstrip("\r\n").rstrip(" \t")
    fence = content.lstrip(" ")
    if len(content) - len(fence) > _MAX_FENCE_INDENT:
        return False
    return len(fence) >= len(opening_fence) and fence == opening_fence[0] * len(fence)


def _renumber_outside_code_spans(*, text: str, new_position_by_old_position: dict[int, int]) -> str:
    """Renumber the citations of a text outside its code spans.

    A code span opens on a run of backticks and closes on the next run of exactly the same length, as in
    CommonMark; a run with no such closer is literal text.
    """
    renumbered_parts: list[str] = []
    prose_start = 0
    search_start = 0
    while (opening_run := _BACKTICK_RUN_PATTERN.search(text, search_start)) is not None:
        closing_run = _closing_backtick_run(text=text, opening_run=opening_run)
        if closing_run is None:
            search_start = opening_run.end()
            continue
        renumbered_parts.append(
            _renumber_prose(text=text[prose_start : opening_run.start()], new_position_by_old_position=new_position_by_old_position)
        )
        renumbered_parts.append(text[opening_run.start() : closing_run.end()])
        prose_start = closing_run.end()
        search_start = closing_run.end()
    renumbered_parts.append(_renumber_prose(text=text[prose_start:], new_position_by_old_position=new_position_by_old_position))
    return "".join(renumbered_parts)


def _closing_backtick_run(*, text: str, opening_run: re.Match[str]) -> re.Match[str] | None:
    run_length = len(opening_run.group(0))
    for candidate_run in _BACKTICK_RUN_PATTERN.finditer(text, opening_run.end()):
        if len(candidate_run.group(0)) == run_length:
            return candidate_run
    return None


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
