import pytest
from reportlab.lib.fonts import tt2ps  # type: ignore[import-untyped]
from reportlab.pdfbase import pdfmetrics  # type: ignore[import-untyped]
from reportlab.platypus import Paragraph  # type: ignore[import-untyped]

from pipelex.providers.reportlab.pdf_elements import (
    BUNDLED_FACES,
    FONTS_DIR,
    MONO_FONT,
    SANS_BOLD_FONT,
    SANS_BOLD_ITALIC_FONT,
    SANS_FONT,
    SANS_ITALIC_FONT,
    ColumnExtent,
    build_pdf_styles,
    escape_attribute,
    escape_text,
    fit_column_widths,
    register_bundled_fonts,
    text_cell,
)


class TestPdfElements:
    def test_every_bundled_face_ships_with_its_licence_and_the_fonts_stay_small(self) -> None:
        for face in BUNDLED_FACES:
            assert face.file_path.is_file(), face.file_path
            assert (face.file_path.parent / "OFL.txt").is_file(), face.file_path.parent
        total_size = sum(font_file.stat().st_size for font_file in FONTS_DIR.rglob("*") if font_file.is_file())
        assert total_size < 1_000_000

    def test_the_fonts_are_registered_once_and_their_families_map_bold_and_italic(self) -> None:
        register_bundled_fonts()
        sans_font = pdfmetrics.getFont(SANS_FONT)
        register_bundled_fonts()
        assert pdfmetrics.getFont(SANS_FONT) is sans_font
        assert tt2ps(SANS_FONT, 1, 0) == SANS_BOLD_FONT
        assert tt2ps(SANS_FONT, 0, 1) == SANS_ITALIC_FONT
        assert tt2ps(SANS_FONT, 1, 1) == SANS_BOLD_ITALIC_FONT
        assert tt2ps(MONO_FONT, 1, 1) == MONO_FONT

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("<b>Tom & Jerry</b>", "&lt;b&gt;Tom &amp; Jerry&lt;/b&gt;"),
            ("&amp; &nbsp;", "&amp;amp; &amp;nbsp;"),
            ("first\nsecond\r\nthird\rfourth", "first<br/>second<br/>third<br/>fourth"),
            ("bell\x07 null\x00 tab\t", "bell null tab\t"),
        ],
    )
    def test_escaped_text_prints_as_written(self, text: str, expected: str) -> None:
        assert escape_text(text=text) == expected

    def test_an_attribute_escapes_its_quotes(self) -> None:
        assert escape_attribute(value='https://x.com/?a="1"&b=<2>') == "https://x.com/?a=&quot;1&quot;&amp;b=&lt;2&gt;"

    def test_columns_that_fit_keep_their_preferred_widths(self) -> None:
        extents = [ColumnExtent(preferred=100, minimum=40), ColumnExtent(preferred=50, minimum=20)]
        assert fit_column_widths(extents=extents, available_width=400) == [100, 50]

    def test_a_long_text_column_wraps_and_the_short_columns_beside_it_do_not(self) -> None:
        extents = [ColumnExtent(preferred=90, minimum=50), ColumnExtent(preferred=4000, minimum=30), ColumnExtent(preferred=40, minimum=40)]
        widths = fit_column_widths(extents=extents, available_width=500)
        assert widths == [90, 370, 40]

    def test_columns_that_all_want_more_share_the_width_evenly_above_their_minimums(self) -> None:
        extents = [ColumnExtent(preferred=1000, minimum=100), ColumnExtent(preferred=3000, minimum=20)]
        widths = fit_column_widths(extents=extents, available_width=400)
        assert widths == [240, 160]

    def test_minimums_wider_than_the_page_shrink_in_proportion(self) -> None:
        extents = [ColumnExtent(preferred=600, minimum=300), ColumnExtent(preferred=400, minimum=200)]
        assert fit_column_widths(extents=extents, available_width=250) == [150, 100]

    def test_a_text_that_fits_its_column_is_drawn_as_it_is_and_one_that_does_not_wraps(self) -> None:
        cell_style = build_pdf_styles().cell
        assert text_cell(text="<b>short</b>", width=200, style=cell_style) == "<b>short</b>"
        assert isinstance(text_cell(text="word " * 60, width=200, style=cell_style), Paragraph)
        assert isinstance(text_cell(text="two\nlines", width=200, style=cell_style), Paragraph)

    @pytest.mark.parametrize(("level", "expected_index"), [(-3, 0), (0, 0), (1, 0), (3, 2), (6, 5), (12, 5)])
    def test_a_heading_level_is_clamped_to_the_styles_there_are(self, level: int, expected_index: int) -> None:
        styles = build_pdf_styles()
        assert styles.heading(level=level) is styles.headings[expected_index]
