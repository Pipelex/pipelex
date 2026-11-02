"""Test data for the deduplication of a sourced answer's sources."""

from typing import ClassVar

ALPHA_URL = "https://alpha.example.com/report"
BETA_URL = "https://beta.example.org/article"
GAMMA_URL = "https://gamma.example.net/notes"


class SearchSourcesTestData:
    """Sourced answers, as the sources a provider listed and the answer citing them.

    `NO_DUPLICATE_CASES` tuples: (topic, sources as (url, title) pairs, answer, renumber_citations).

    `DEDUP_CASES` tuples: (topic, sources as (url, title) pairs, answer, renumber_citations, titles of the
    sources expected back in order, answer expected back).
    """

    NO_DUPLICATE_CASES: ClassVar[list[tuple[str, list[tuple[str, str]], str, bool]]] = [
        (
            "distinct_addresses",
            [(ALPHA_URL, "Alpha"), (BETA_URL, "Beta"), (GAMMA_URL, "Gamma")],
            "Alpha says so [1], Beta agrees [2] and Gamma adds more [3].",
            True,
        ),
        (
            "same_page_other_query",
            [(ALPHA_URL, "Alpha"), (f"{ALPHA_URL}?page=2", "Alpha, page 2")],
            "Alpha [1], then its second page [2].",
            True,
        ),
        (
            "no_sources",
            [],
            "Nothing to cite [1].",
            True,
        ),
    ]

    DEDUP_CASES: ClassVar[list[tuple[str, list[tuple[str, str]], str, bool, list[str], str]]] = [
        (
            "duplicate_dropped",
            [(ALPHA_URL, "Alpha"), (BETA_URL, "Beta"), (ALPHA_URL, "Alpha again"), (GAMMA_URL, "Gamma")],
            "Alpha says so [1]. Beta agrees [2]. Alpha repeats it [3]. Gamma adds more [4].",
            True,
            ["Alpha", "Beta", "Gamma"],
            "Alpha says so [1]. Beta agrees [2]. Alpha repeats it [1]. Gamma adds more [3].",
        ),
        (
            "duplicate_differing_by_fragment",
            [(ALPHA_URL, "Alpha"), (BETA_URL, "Beta"), (f"{ALPHA_URL}#methods", "Alpha, methods"), (GAMMA_URL, "Gamma")],
            "Alpha [1] and Beta [2] agree, by its methods [3][4].",
            True,
            ["Alpha", "Beta", "Gamma"],
            "Alpha [1] and Beta [2] agree, by its methods [1][3].",
        ),
        (
            "first_entry_kept_with_its_fragment",
            [(f"{ALPHA_URL}#intro", "Alpha, intro"), (ALPHA_URL, "Alpha"), (BETA_URL, "Beta")],
            "The intro [1], the page [2], then Beta [3].",
            True,
            ["Alpha, intro", "Beta"],
            "The intro [1], the page [1], then Beta [2].",
        ),
        (
            "number_without_source_unchanged",
            [(ALPHA_URL, "Alpha"), (ALPHA_URL, "Alpha again"), (BETA_URL, "Beta")],
            "None [0], Beta [3], beyond the list [4], far beyond [12].",
            True,
            ["Alpha", "Beta"],
            "None [0], Beta [2], beyond the list [4], far beyond [12].",
        ),
        (
            "code_left_alone",
            [(ALPHA_URL, "Alpha"), (ALPHA_URL, "Alpha again"), (BETA_URL, "Beta")],
            "Beta [3] says `items[3]` and ``a ` b[3]`` are last:\n\n```python\nprint(items[3])\n```\n\n~~~\nrows[3]\n~~~\n\nAgain [3].",
            True,
            ["Alpha", "Beta"],
            "Beta [2] says `items[3]` and ``a ` b[3]`` are last:\n\n```python\nprint(items[3])\n```\n\n~~~\nrows[3]\n~~~\n\nAgain [2].",
        ),
        (
            "unclosed_backtick_is_text",
            [(ALPHA_URL, "Alpha"), (ALPHA_URL, "Alpha again"), (BETA_URL, "Beta")],
            "A lone ` backtick, then Beta [3].",
            True,
            ["Alpha", "Beta"],
            "A lone ` backtick, then Beta [2].",
        ),
        (
            "unclosed_fence_runs_to_the_end",
            [(ALPHA_URL, "Alpha"), (ALPHA_URL, "Alpha again"), (BETA_URL, "Beta")],
            "Beta [3]:\n\n```\nitems[3]\n",
            True,
            ["Alpha", "Beta"],
            "Beta [2]:\n\n```\nitems[3]\n",
        ),
        (
            "citations_not_requested",
            [(ALPHA_URL, "Alpha"), (ALPHA_URL, "Alpha again"), (BETA_URL, "Beta")],
            "The answer's own text names item [3].",
            False,
            ["Alpha", "Beta"],
            "The answer's own text names item [3].",
        ),
    ]
