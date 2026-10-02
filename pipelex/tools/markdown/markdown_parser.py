"""The one Markdown parser Pipelex formats Markdown with, whatever it turns it into.

The `markdown` filter of HTML templates, the `Markdown` concept's HTML view and the built-in PDF engine all
read Markdown an LLM or a person wrote, so they parse it the same way, here:

- CommonMark, with tables and strikethrough, which LLM reports use;
- raw HTML disabled, so HTML inside the Markdown shows as text rather than entering the document;
- bare URLs linked, but only those with a scheme: markdown-it's default fuzzy matching links `README.md` to
  `http://README.md` and `config.py` to `http://config.py`, `.md` and `.py` being country domains, so fuzzy
  links and fuzzy emails are off, and `www.` addresses and bare emails stay text.
"""

from functools import cache

from markdown_it import MarkdownIt


@cache
def get_markdown_parser() -> MarkdownIt:
    """The shared parser, built once. Parsing and rendering keep no state between calls, so it is shared freely."""
    parser = MarkdownIt("commonmark", {"html": False, "linkify": True}).enable(["table", "strikethrough", "linkify"])
    linkify = parser.linkify
    if linkify is None:
        msg = "markdown-it-py found no linkify-it-py: Pipelex requires markdown-it-py[linkify]."
        raise RuntimeError(msg)
    linkify.set({"fuzzy_link": False, "fuzzy_email": False})  # pyright: ignore[reportUnknownMemberType]
    return parser


def render_markdown_as_html(markdown_text: str) -> str:
    """Markdown as an HTML fragment, with any raw HTML in the source escaped."""
    html: str = get_markdown_parser().render(markdown_text)
    return html
