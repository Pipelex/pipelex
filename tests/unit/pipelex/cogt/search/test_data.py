"""Test data for the deduplication of a sourced answer's sources."""

from typing import ClassVar

ALPHA_URL = "https://alpha.example.com/report"
BETA_URL = "https://beta.example.org/article"
GAMMA_URL = "https://gamma.example.net/notes"

# One page listed twice, then another: a citation `[3]` becomes `[2]` and `[2]` becomes `[1]`.
ALPHA_TWICE_THEN_BETA: list[tuple[str, str]] = [(ALPHA_URL, "Alpha"), (ALPHA_URL, "Alpha again"), (BETA_URL, "Beta")]

# Sources of a real Linkup sourced answer, in the order they arrived: positions 4 and 5 name one page, with
# and without `www.`, under the same title. Titles and public addresses only.
REAL_RUN_SOURCES: list[tuple[str, str]] = [
    (
        "https://www.pikon.com/en/blog/france-new-b2b-and-b2c-einvoicing-and-ereporting-requirements/",
        "France: New E-Invoicing and E-Reporting Requirements for 2026 - PIKON SAP Consulting International",
    ),
    ("https://www.taxually.com/blog/e-invoicing-france-everything-you-need-to-know", "E-Invoicing France: Everything You Need to Know | Taxually"),
    ("https://www.cleartax.com/fr/en/e-invoicing-france", "e-Invoicing France 2026: Timeline, Requirements, Guidelines and Format"),
    (
        "https://www.resolveit.nl/en/blog/frankrijk-e-facturatie-september-2026",
        "French e-invoicing from 1 September 2026: what it does and does not ask of you | Resolve IT",
    ),
    (
        "https://resolveit.nl/en/blog/frankrijk-e-facturatie-september-2026",
        "French e-invoicing from 1 September 2026: what it does and does not ask of you | Resolve IT",
    ),
    ("https://dddinvoices.com/learn/e-invoicing-france", "France E-Invoicing Guide: B2B Mandate and 2026 Requirements"),
    ("https://www.sarepta-expertise.fr/en/guides/e-invoicing-in-france/", "E-invoicing in France: 2026-2027 Rules, Dates | SAREPTA"),
    ("https://www.sanso.ai/en/blog/e-invoicing-mandate-small-business", "France's E-Invoicing Mandate for Small Business | Sanso"),
    ("https://maventa.com/blog/e-invoicing-requirements-in-france", "Guide to e-invoicing requirements in France | Maventa"),
    (
        "https://www.pincvision.com/news/france-einvoicing-and-e-reporting-what-you-need-to-know",
        "France eInvoicing and e-reporting: requirements and timelines - Pincvision",
    ),
]

# Positions 14 and 15 of the same answer: one site, two different pages, under the same title.
REAL_RUN_SAME_SITE_PAGES: list[tuple[str, str]] = [
    ("https://code10it.com/france-b2b-einvoicing/", "France B2B E-Invoicing: Requirements &amp; SAP Integration"),
    (
        "https://code10it.com/regulatory-map/compliance-regulation-france/france-b2b-einvoicing/",
        "France B2B E-Invoicing: Requirements &amp; SAP Integration",
    ),
]


class SearchSourcesTestData:
    """Sourced answers, as the sources a provider listed and the answer citing them.

    `NO_DUPLICATE_CASES` tuples: (topic, sources as (url, title) pairs, answer, renumber_citations).

    `DEDUP_CASES` tuples: (topic, sources as (url, title) pairs, answer, renumber_citations, positions of
    the sources expected back in the provider's list counted from 1, answer expected back).
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
            "path_case_kept",
            [(ALPHA_URL, "Alpha"), ("https://alpha.example.com/Report", "Alpha, capitalised")],
            "Alpha [1], and the capitalised page [2].",
            True,
        ),
        (
            "real_run_same_site_different_pages",
            REAL_RUN_SAME_SITE_PAGES,
            "Both pages of the site [1][2].",
            True,
        ),
        (
            "no_sources",
            [],
            "Nothing to cite [1].",
            True,
        ),
    ]

    DEDUP_CASES: ClassVar[list[tuple[str, list[tuple[str, str]], str, bool, list[int], str]]] = [
        (
            "duplicate_dropped",
            [(ALPHA_URL, "Alpha"), (BETA_URL, "Beta"), (ALPHA_URL, "Alpha again"), (GAMMA_URL, "Gamma")],
            "Alpha says so [1]. Beta agrees [2]. Alpha repeats it [3]. Gamma adds more [4].",
            True,
            [1, 2, 4],
            "Alpha says so [1]. Beta agrees [2]. Alpha repeats it [1]. Gamma adds more [3].",
        ),
        (
            "duplicate_differing_by_fragment",
            [(ALPHA_URL, "Alpha"), (BETA_URL, "Beta"), (f"{ALPHA_URL}#methods", "Alpha, methods"), (GAMMA_URL, "Gamma")],
            "Alpha [1] and Beta [2] agree, by its methods [3][4].",
            True,
            [1, 2, 4],
            "Alpha [1] and Beta [2] agree, by its methods [1][3].",
        ),
        (
            "first_entry_kept_with_its_fragment",
            [(f"{ALPHA_URL}#intro", "Alpha, intro"), (ALPHA_URL, "Alpha"), (BETA_URL, "Beta")],
            "The intro [1], the page [2], then Beta [3].",
            True,
            [1, 3],
            "The intro [1], the page [1], then Beta [2].",
        ),
        (
            "www_prefix_dropped",
            [("https://www.alpha.example.com/report", "Alpha, www"), (BETA_URL, "Beta"), (ALPHA_URL, "Alpha")],
            "Alpha [1], Beta [2], Alpha again [3].",
            True,
            [1, 2],
            "Alpha [1], Beta [2], Alpha again [1].",
        ),
        (
            "http_against_https",
            [(ALPHA_URL, "Alpha"), ("http://alpha.example.com/report", "Alpha over http"), (BETA_URL, "Beta")],
            "Alpha [1], Alpha over http [2], Beta [3].",
            True,
            [1, 3],
            "Alpha [1], Alpha over http [1], Beta [2].",
        ),
        (
            "trailing_slash_dropped",
            [(f"{GAMMA_URL}/", "Gamma, slash"), (BETA_URL, "Beta"), (GAMMA_URL, "Gamma")],
            "Gamma [1], Beta [2], Gamma again [3].",
            True,
            [1, 2],
            "Gamma [1], Beta [2], Gamma again [1].",
        ),
        (
            "host_case_ignored",
            [(ALPHA_URL, "Alpha"), ("https://Alpha.EXAMPLE.com/report", "Alpha, capitalised host"), (BETA_URL, "Beta")],
            "Alpha [1], Alpha again [2], Beta [3].",
            True,
            [1, 3],
            "Alpha [1], Alpha again [1], Beta [2].",
        ),
        (
            "site_root_with_and_without_slash",
            [("https://alpha.example.com/", "Alpha home"), (BETA_URL, "Beta"), ("http://www.alpha.example.com", "Alpha home, bare")],
            "Alpha's home [1], Beta [2], Alpha's home again [3].",
            True,
            [1, 2],
            "Alpha's home [1], Beta [2], Alpha's home again [1].",
        ),
        (
            "real_run_www_pair",
            REAL_RUN_SOURCES,
            (
                "Every company must be able to receive e-invoices from 1 September 2026.[2][3] "
                "An emailed PDF alone is not a compliant e-invoice.[2][4] "
                "The mandate asks little more of a small company that year.[5] "
                "Issuing follows in 2027.[6][9] "
                "Some VAT-exempt activities are excluded.[1][10]"
            ),
            True,
            [1, 2, 3, 4, 6, 7, 8, 9, 10],
            (
                "Every company must be able to receive e-invoices from 1 September 2026.[2][3] "
                "An emailed PDF alone is not a compliant e-invoice.[2][4] "
                "The mandate asks little more of a small company that year.[4] "
                "Issuing follows in 2027.[5][8] "
                "Some VAT-exempt activities are excluded.[1][9]"
            ),
        ),
        (
            "number_without_source_unchanged",
            [(ALPHA_URL, "Alpha"), (ALPHA_URL, "Alpha again"), (BETA_URL, "Beta")],
            "None [0], Beta [3], beyond the list [4], far beyond [12].",
            True,
            [1, 3],
            "None [0], Beta [2], beyond the list [4], far beyond [12].",
        ),
        (
            "code_left_alone",
            [(ALPHA_URL, "Alpha"), (ALPHA_URL, "Alpha again"), (BETA_URL, "Beta")],
            "Beta [3] says `items[3]` and ``a ` b[3]`` are last:\n\n```python\nprint(items[3])\n```\n\n~~~\nrows[3]\n~~~\n\nAgain [3].",
            True,
            [1, 3],
            "Beta [2] says `items[3]` and ``a ` b[3]`` are last:\n\n```python\nprint(items[3])\n```\n\n~~~\nrows[3]\n~~~\n\nAgain [2].",
        ),
        (
            "unclosed_backtick_is_text",
            [(ALPHA_URL, "Alpha"), (ALPHA_URL, "Alpha again"), (BETA_URL, "Beta")],
            "A lone ` backtick, then Beta [3].",
            True,
            [1, 3],
            "A lone ` backtick, then Beta [2].",
        ),
        (
            "unclosed_fence_runs_to_the_end",
            [(ALPHA_URL, "Alpha"), (ALPHA_URL, "Alpha again"), (BETA_URL, "Beta")],
            "Beta [3]:\n\n```\nitems[3]\n",
            True,
            [1, 3],
            "Beta [2]:\n\n```\nitems[3]\n",
        ),
        (
            "quote_nested_tilde_fence",
            ALPHA_TWICE_THEN_BETA,
            "Beta indexes it [3]:\n\n> ~~~python\n> items[3]\n> ~~~\n\nAlpha agrees [2].",
            True,
            [1, 3],
            "Beta indexes it [2]:\n\n> ~~~python\n> items[3]\n> ~~~\n\nAlpha agrees [1].",
        ),
        (
            "quote_nested_backtick_fence_closed_by_a_longer_fence",
            ALPHA_TWICE_THEN_BETA,
            "> ```\n> items[3]\n> ````\n\nBeta [3].",
            True,
            [1, 3],
            "> ```\n> items[3]\n> ````\n\nBeta [2].",
        ),
        (
            "list_nested_tilde_fence_at_indent_4",
            ALPHA_TWICE_THEN_BETA,
            "Beta's steps [3]:\n\n- Outer\n  - Inner:\n\n    ~~~python\n    items[3]\n    ~~~\n\nAlpha agrees [2].\n",
            True,
            [1, 3],
            "Beta's steps [2]:\n\n- Outer\n  - Inner:\n\n    ~~~python\n    items[3]\n    ~~~\n\nAlpha agrees [1].\n",
        ),
        (
            "indented_code_block",
            ALPHA_TWICE_THEN_BETA,
            "Beta indexes it [3]:\n\n    items[3]\n\nAlpha agrees [2].\n",
            True,
            [1, 3],
            "Beta indexes it [2]:\n\n    items[3]\n\nAlpha agrees [1].\n",
        ),
        (
            "unclosed_fence_ends_with_its_list_item",
            ALPHA_TWICE_THEN_BETA,
            "1. Run:\n   ```bash\n   ls items[3]\n\nBeta [3] and Alpha [2].\n",
            True,
            [1, 3],
            "1. Run:\n   ```bash\n   ls items[3]\n\nBeta [2] and Alpha [1].\n",
        ),
        (
            "stray_backtick_across_paragraphs",
            ALPHA_TWICE_THEN_BETA,
            "Press the ` key, says Beta [3].\n\nAlpha agrees [2].\n\nAnother ` here [3].\n",
            True,
            [1, 3],
            "Press the ` key, says Beta [2].\n\nAlpha agrees [1].\n\nAnother ` here [2].\n",
        ),
        (
            "stray_backtick_across_list_items",
            ALPHA_TWICE_THEN_BETA,
            "- The ` key [3]\n- Cited [2]\n- Another ` key [3]\n",
            True,
            [1, 3],
            "- The ` key [2]\n- Cited [1]\n- Another ` key [2]\n",
        ),
        (
            "stray_backtick_across_table_rows",
            ALPHA_TWICE_THEN_BETA,
            "| Key | Note |\n| --- | --- |\n| ` | Beta [3] |\n| x | Alpha [2] |\n| ` | Beta again [3] |\n",
            True,
            [1, 3],
            "| Key | Note |\n| --- | --- |\n| ` | Beta [2] |\n| x | Alpha [1] |\n| ` | Beta again [2] |\n",
        ),
        (
            "stray_backtick_across_table_cells",
            ALPHA_TWICE_THEN_BETA,
            "| Key | Source | Note |\n| --- | --- | --- |\n| Open ` | Beta [3] | close ` |\n",
            True,
            [1, 3],
            "| Key | Source | Note |\n| --- | --- | --- |\n| Open ` | Beta [2] | close ` |\n",
        ),
        (
            "stray_backtick_before_a_later_code_span",
            ALPHA_TWICE_THEN_BETA,
            "Press the backtick (`) key [3].\n\nAlpha agrees [2].\n\nThen run `ls` [3].",
            True,
            [1, 3],
            "Press the backtick (`) key [2].\n\nAlpha agrees [1].\n\nThen run `ls` [2].",
        ),
        (
            "escaped_backtick_opens_no_code_span",
            ALPHA_TWICE_THEN_BETA,
            "Escape it as \\` and cite Beta [3]; a literal backslash before code reads \\\\`items[3]`.",
            True,
            [1, 3],
            "Escape it as \\` and cite Beta [2]; a literal backslash before code reads \\\\`items[3]`.",
        ),
        (
            "escaped_backtick_leaves_the_rest_of_its_run",
            ALPHA_TWICE_THEN_BETA,
            "Write \\``items[3]` as Beta does [3].",
            True,
            [1, 3],
            "Write \\``items[3]` as Beta does [2].",
        ),
        (
            "crlf_line_endings_kept",
            ALPHA_TWICE_THEN_BETA,
            "Beta indexes it [3]:\r\n\r\n    items[3]\r\n\r\n> ~~~\r\n> rows[3]\r\n> ~~~\r\n\r\nAlpha agrees [2].\r\n",
            True,
            [1, 3],
            "Beta indexes it [2]:\r\n\r\n    items[3]\r\n\r\n> ~~~\r\n> rows[3]\r\n> ~~~\r\n\r\nAlpha agrees [1].\r\n",
        ),
        (
            "mixed_line_endings_kept",
            ALPHA_TWICE_THEN_BETA,
            "Beta indexes it [3]:\r\r    items[3]\n\r\n> ~~~\r> rows[3]\n> ~~~\r\n\rAlpha agrees [2].",
            True,
            [1, 3],
            "Beta indexes it [2]:\r\r    items[3]\n\r\n> ~~~\r> rows[3]\n> ~~~\r\n\rAlpha agrees [1].",
        ),
        (
            "line_separator_is_no_line_ending",
            ALPHA_TWICE_THEN_BETA,
            "Alpha agrees [2].\n\n    items[3]\n\nBeta [3].\n",
            True,
            [1, 3],
            "Alpha agrees [1].\n\n    items[3]\n\nBeta [2].\n",
        ),
        (
            "citations_not_requested",
            [(ALPHA_URL, "Alpha"), (ALPHA_URL, "Alpha again"), (BETA_URL, "Beta")],
            "The answer's own text names item [3].",
            False,
            [1, 3],
            "The answer's own text names item [3].",
        ),
    ]
