import pytest

from pipelex.tools.misc.produced_file_name import MAX_FILE_NAME_BYTES, build_produced_file_name


class TestProducedFileName:
    @pytest.mark.parametrize(
        ("rendered", "default_name", "item_number", "expected"),
        [
            ("Acme Corp - NDA review", "generated.pdf", 1, "Acme Corp - NDA review.pdf"),
            ("Report.PDF", "generated.pdf", 1, "Report.PDF"),
            ("report.pdf", "generated.png", 1, "report.pdf.png"),
            ("  Acme\n\tCorp  ", "generated.pdf", 1, "Acme Corp.pdf"),
            ("../etc/passwd", "generated.pdf", 1, "-etc-passwd.pdf"),
            ('a/b\\c:d*e?f"g<h>i|j', "generated.pdf", 1, "a-b-c-d-e-f-g-h-i-j.pdf"),
            ("bell\x07char", "generated.pdf", 1, "bell-char.pdf"),
            ("...hidden...", "generated.pdf", 1, "hidden.pdf"),
            ("con", "generated.pdf", 1, "con_.pdf"),
            ("LPT1.notes", "generated.pdf", 1, "LPT1_.notes.pdf"),
            ("Café", "generated.pdf", 1, "Café.pdf"),
            ("cover", "generated.png", 2, "cover (2).png"),
            ("cover", "generated.png", 1, "cover.png"),
            ("no extension", "generated", 1, "no extension"),
        ],
    )
    def test_builds_the_name_from_the_rendered_template(self, rendered: str, default_name: str, item_number: int, expected: str) -> None:
        """Each step of the standard's naming: normalization, replaced characters, trimming, the extension and the suffix."""
        assert build_produced_file_name(rendered=rendered, default_name=default_name, item_number=item_number) == expected

    @pytest.mark.parametrize(
        "rendered",
        [None, "", "   ", "...", " . . ", "\t\n"],
    )
    def test_falls_back_to_the_runtime_name_when_nothing_is_left(self, rendered: str | None) -> None:
        """A failed render, or nothing left before the extension, keeps the name the runtime would have given."""
        assert build_produced_file_name(rendered=rendered, default_name="generated.pdf") == "generated.pdf"

    @pytest.mark.parametrize(
        ("rendered", "item_number"),
        [("é" * 300, 1), ("é" * 300, 12), ("a" * 400, 1), ("日本語" * 100, 3)],
    )
    def test_caps_the_name_at_255_bytes_without_splitting_a_character(self, rendered: str, item_number: int) -> None:
        """The whole name, suffix and extension included, fits in 255 bytes of UTF-8 and keeps its suffix and extension."""
        name = build_produced_file_name(rendered=rendered, default_name="generated.pdf", item_number=item_number)
        encoded = name.encode("utf-8")
        assert len(encoded) <= MAX_FILE_NAME_BYTES
        assert encoded.decode("utf-8") == name
        assert name.endswith(f" ({item_number}).pdf" if item_number > 1 else ".pdf")
        assert len(encoded) > MAX_FILE_NAME_BYTES - 4

    @pytest.mark.parametrize(
        ("rendered", "default_name", "item_number", "expected"),
        [
            ("Report", "generated." + "x" * 300, 1, "Report"),
            ("Report", "generated." + "é" * 200, 2, "Report (2)"),
            (None, "generated." + "x" * 300, 1, "generated"),
            ("", "z" * 400 + ".png", 1, "z" * 251 + ".png"),
            (None, "é" * 300 + ".png", 1, "é" * 125 + ".png"),
        ],
    )
    def test_never_passes_255_bytes_whatever_the_runtime_name_carries(
        self, rendered: str | None, default_name: str, item_number: int, expected: str
    ) -> None:
        """An extension leaving no room for the name is dropped, and the runtime's own name is capped when it is the fallback."""
        name = build_produced_file_name(rendered=rendered, default_name=default_name, item_number=item_number)
        assert name == expected
        assert len(name.encode("utf-8")) <= MAX_FILE_NAME_BYTES
