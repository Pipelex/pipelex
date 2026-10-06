from typing import Any, ClassVar


class TestData:
    # A short report, as an LLM writes one
    SAMPLE_REPORT = "# Inspection report\n\nThe **roof** needs work.\n\n- cracked tiles\n- sagging gutter"
    EXPECTED_REPORT_HTML = (
        "<h1>Inspection report</h1>\n<p>The <strong>roof</strong> needs work.</p>\n<ul>\n<li>cracked tiles</li>\n<li>sagging gutter</li>\n</ul>\n"
    )
    EXPECTED_SMART_DUMP: ClassVar[dict[str, Any]] = {"text": SAMPLE_REPORT}
    EXPECTED_SHORT_DESC = f"some markdown ({len(SAMPLE_REPORT)} chars)"
    EXPECTED_FIELD_DESCRIPTION = "The text, written in Markdown"

    # (source, expected HTML): what the conversion links, leaves as text and escapes
    HTML_CONVERSION_CASES: ClassVar[list[tuple[str, str]]] = [
        # A URL with a scheme is linked
        (
            "See https://example.com/report for details.",
            '<p>See <a href="https://example.com/report">https://example.com/report</a> for details.</p>\n',
        ),
        # A file name whose suffix is a country domain stays text: fuzzy linking is off
        ("Read README.md first.", "<p>Read README.md first.</p>\n"),
        # Raw HTML in the source is escaped, never inserted
        ("<script>alert(1)</script>", "<p>&lt;script&gt;alert(1)&lt;/script&gt;</p>\n"),
        # A javascript: link target is refused, so the link stays text
        ("[click](javascript:alert(1))", "<p>[click](javascript:alert(1))</p>\n"),
    ]

    # Source that looks like HTML: a Text would pretty-print it as HTML, a Markdown never does
    SAMPLE_HTML_LOOKING_MARKDOWN = "<b>not html</b>\n\n# A heading"
