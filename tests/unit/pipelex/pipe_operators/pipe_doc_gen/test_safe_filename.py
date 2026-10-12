import re

import pytest

from pipelex.pipe_operators.doc_gen.pipe_doc_gen import safe_filename
from pipelex.tools.storage.storage_file_name import MAX_STORAGE_FILE_STEM_LENGTH

# The hosted platform's grammar for the last segment of a `pipelex-storage://` URI, copied from `_SEGMENT_PATTERN` and
# `_EXTENSION_PATTERN` in pipelex-server's `shared/src/pipelex_shared/domain/storage/storage_uri.py`
# (`parse_storage_uri`): a stem of these characters, one dot, an alphanumeric extension. A name it refuses is never
# served, so the document can never be downloaded.
_HOSTED_STEM_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_HOSTED_EXTENSION_PATTERN = re.compile(r"^[A-Za-z0-9]+$")


def _assert_hosted_grammar_accepts(filename: str) -> None:
    assert "." in filename
    assert not filename.startswith(".")
    assert not filename.endswith(".")
    stem, extension = filename.rsplit(".", 1)
    assert _HOSTED_STEM_PATTERN.match(stem), f"stem of {filename!r} is not path-safe"
    assert _HOSTED_EXTENSION_PATTERN.match(extension), f"extension of {filename!r} is not alphanumeric"


class TestSafeFilename:
    @pytest.mark.parametrize(
        ("rendered", "expected"),
        [
            ("invoice-INV-2026-0142", "invoice-INV-2026-0142.pdf"),
            ("invoice INV/2026:0142", "invoice-INV-2026-0142.pdf"),
            ("report.pdf", "report.pdf"),
            ("Report.PDF", "Report.pdf"),
            ("  ../../etc/passwd  ", "etc-passwd.pdf"),
            ("", "render_invoice.pdf"),
            ("...", "render_invoice.pdf"),
            # Accents are dropped from their letters.
            ("Bäckerei Müller & Söhne", "Backerei-Muller-Sohne.pdf"),
            ("Zoë Ångström — Q3.2026", "Zoe-Angstrom-Q3-2026.pdf"),
            ("İstanbul Çiğköfte", "Istanbul-Cigkofte.pdf"),
            # Letters NFKD leaves whole are spelled from the table.
            ("Ærøskøbing", "AEroskobing.pdf"),
            ("Łukasiewicz straße", "Lukasiewicz-strasse.pdf"),
            ("Đorđe Þórr ðe œuvre ı", "Dorde-Thorr-de-oeuvre-i.pdf"),
            # A script with no Latin spelling becomes a separator, and is dropped at either end.
            ("Ελληνικά report", "report.pdf"),
            ("Москва 2026", "2026.pdf"),
            ("東京都 Q3", "Q3.pdf"),
            ("مرحبا Q3", "Q3.pdf"),
            # A name that leaves nothing falls back to the step's code.
            ("ελληνικά", "render_invoice.pdf"),
            ("Москва", "render_invoice.pdf"),
            ("東京都", "render_invoice.pdf"),
            ("مرحبا", "render_invoice.pdf"),
            ("서울", "render_invoice.pdf"),
            # Inner dots leave the stem, and repeated separators collapse.
            ("report.v2.final", "report-v2-final.pdf"),
            ("report.v2.pdf", "report-v2.pdf"),
            ("a -- b __ c", "a-b-c.pdf"),
            ("snake__case", "snake_case.pdf"),
        ],
    )
    def test_the_rendered_name_becomes_one_name_the_hosted_plane_serves(self, rendered: str, expected: str) -> None:
        filename = safe_filename(rendered=rendered, fallback="render_invoice", suffix="pdf")

        assert filename == expected
        _assert_hosted_grammar_accepts(filename)

    def test_the_proof_lab_name_the_hosted_plane_refused_is_now_served(self) -> None:
        """The file name of the run the hosted plane would not serve, as its method's template rendered it."""
        rendered = "Halden Brook Review Q3 2026 — Zoë Ångström Łukasiewicz · Ærøskøbing · İstanbul · Ελληνικά · Москва · 東京都 · 서울 · مرحبا · שלום"

        filename = safe_filename(rendered=rendered, fallback="render_review", suffix="docx")

        assert filename == "Halden-Brook-Review-Q3-2026-Zoe-Angstrom-Lukasiewicz-AEroskobing-Istanbul.docx"
        _assert_hosted_grammar_accepts(filename)

    @pytest.mark.parametrize("suffix", ["pdf", "xlsx", "docx", "pptx"])
    def test_a_stem_already_ending_in_the_suffix_is_not_given_it_twice(self, suffix: str) -> None:
        filename = safe_filename(rendered=f"quarterly-review.{suffix.upper()}", fallback="render_review", suffix=suffix)

        assert filename == f"quarterly-review.{suffix}"
        _assert_hosted_grammar_accepts(filename)

    def test_the_stem_is_cut_at_its_length_cap_and_never_ends_on_a_separator(self) -> None:
        rendered = "a" * (MAX_STORAGE_FILE_STEM_LENGTH - 1) + "-tail-past-the-cap"

        filename = safe_filename(rendered=rendered, fallback="render_invoice", suffix="pdf")

        assert filename == "a" * (MAX_STORAGE_FILE_STEM_LENGTH - 1) + ".pdf"
        _assert_hosted_grammar_accepts(filename)

    def test_a_long_name_of_accented_letters_is_cut_after_its_letters_are_spelled(self) -> None:
        filename = safe_filename(rendered="é" * (MAX_STORAGE_FILE_STEM_LENGTH * 2), fallback="render_invoice", suffix="pdf")

        assert filename == "e" * MAX_STORAGE_FILE_STEM_LENGTH + ".pdf"
        _assert_hosted_grammar_accepts(filename)
