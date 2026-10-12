import re

import pytest

from pipelex.tools.storage.storage_file_name import (
    MAX_STORAGE_FILE_STEM_LENGTH,
    STORAGE_FILE_EXTENSION_PATTERN,
    STORAGE_FILE_STEM_PATTERN,
    fold_to_ascii,
    path_safe_file_name,
)

# The hosted platform's grammar for the last segment of a `pipelex-storage://` URI, copied from `_SEGMENT_PATTERN` and
# `_EXTENSION_PATTERN` in pipelex-server's `shared/src/pipelex_shared/domain/storage/storage_uri.py`
# (`parse_storage_uri`): a stem of these characters, one dot, an alphanumeric extension. A name it refuses is never
# served, so the file can never be downloaded. The runtime restates it rather than importing it, so this pins the two
# to one rule.
_HOSTED_STEM_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_HOSTED_EXTENSION_PATTERN = re.compile(r"^[A-Za-z0-9]+$")


def _assert_hosted_grammar_accepts(file_name: str) -> None:
    assert "." in file_name
    assert not file_name.startswith(".")
    assert not file_name.endswith(".")
    stem, extension = file_name.rsplit(".", 1)
    assert _HOSTED_STEM_PATTERN.fullmatch(stem), f"stem of {file_name!r} is not path-safe"
    assert _HOSTED_EXTENSION_PATTERN.fullmatch(extension), f"extension of {file_name!r} is not alphanumeric"


class TestStorageFileName:
    def test_the_runtime_restates_the_hosted_grammar_exactly(self) -> None:
        assert STORAGE_FILE_STEM_PATTERN.pattern == _HOSTED_STEM_PATTERN.pattern
        assert STORAGE_FILE_EXTENSION_PATTERN.pattern == _HOSTED_EXTENSION_PATTERN.pattern

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Zoë Ångström", "Zoe Angstrom"),
            ("Ærøskøbing", "AEroskobing"),
            ("ﬁle", "file"),
            ("Москва", "Москва"),
        ],
    )
    def test_letters_are_spelled_in_ascii_where_they_can_be_and_kept_otherwise(self, text: str, expected: str) -> None:
        assert fold_to_ascii(text=text) == expected

    @pytest.mark.parametrize(
        ("name", "expected"),
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
            ("a_-_b", "a-b.pdf"),
            ("snake__case", "snake_case.pdf"),
        ],
    )
    def test_a_rendered_document_name_becomes_one_the_hosted_plane_serves(self, name: str, expected: str) -> None:
        """A `PipeDocGen` step's rendered `filename`, with its code as the fallback and its format as the extension."""
        file_name = path_safe_file_name(name=name, fallback="render_invoice", extension="pdf")

        assert file_name == expected
        _assert_hosted_grammar_accepts(file_name)

    def test_the_proof_lab_name_the_hosted_plane_refused_is_now_served(self) -> None:
        """The file name of the run the hosted plane would not serve, as its method's template rendered it."""
        name = "Halden Brook Review Q3 2026 — Zoë Ångström Łukasiewicz · Ærøskøbing · İstanbul · Ελληνικά · Москва · 東京都 · 서울 · مرحبا · שלום"

        file_name = path_safe_file_name(name=name, fallback="render_review", extension="docx")

        assert file_name == "Halden-Brook-Review-Q3-2026-Zoe-Angstrom-Lukasiewicz-AEroskobing-Istanbul.docx"
        _assert_hosted_grammar_accepts(file_name)

    @pytest.mark.parametrize("extension", ["pdf", "xlsx", "docx", "pptx"])
    def test_a_stem_already_ending_in_the_extension_is_not_given_it_twice(self, extension: str) -> None:
        file_name = path_safe_file_name(name=f"quarterly-review.{extension.upper()}", fallback="render_review", extension=extension)

        assert file_name == f"quarterly-review.{extension}"
        _assert_hosted_grammar_accepts(file_name)

    def test_the_stem_is_cut_at_its_length_cap_and_never_ends_on_a_separator(self) -> None:
        name = "a" * (MAX_STORAGE_FILE_STEM_LENGTH - 1) + "-tail-past-the-cap"

        file_name = path_safe_file_name(name=name, fallback="render_invoice", extension="pdf")

        assert file_name == "a" * (MAX_STORAGE_FILE_STEM_LENGTH - 1) + ".pdf"
        _assert_hosted_grammar_accepts(file_name)

    def test_a_long_name_of_accented_letters_is_cut_after_its_letters_are_spelled(self) -> None:
        file_name = path_safe_file_name(name="é" * (MAX_STORAGE_FILE_STEM_LENGTH * 2), fallback="render_invoice", extension="pdf")

        assert file_name == "e" * MAX_STORAGE_FILE_STEM_LENGTH + ".pdf"
        _assert_hosted_grammar_accepts(file_name)

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            pytest.param("_" * 200_000, "render_invoice.pdf", id="underscores_alone"),
            pytest.param("report" + "_" * 200_000 + "end", "report.pdf", id="underscores_after_a_word"),
            pytest.param("-_" * 100_000 + "report", "render_invoice.pdf", id="mixed_separators"),
            pytest.param("é" * 200_000, "e" * MAX_STORAGE_FILE_STEM_LENGTH + ".pdf", id="accented_letters"),
        ],
    )
    def test_a_very_long_name_is_handled_in_bounded_work(self, name: str, expected: str) -> None:
        """A name rendered from a caller's text can be any length; only its first characters are read, in one pass each."""
        file_name = path_safe_file_name(name=name, fallback="render_invoice", extension="pdf")

        assert file_name == expected
        _assert_hosted_grammar_accepts(file_name)

    @pytest.mark.parametrize(
        ("name", "fallback", "extension", "expected"),
        [
            # A template file's own name, with its own extension.
            ("modèle.v2.docx", "file", "docx", "modele-v2.docx"),
            ("Invoice Template.DOCX", "file", "DOCX", "Invoice-Template.docx"),
            # An extension is spelled in ASCII and lowercased, `bin` when it is not then plainly letters and digits.
            ("template", "file", "", "template.bin"),
            ("template", "file", ".PDF", "template.pdf"),
            ("photo", "file", "jpég", "photo.jpeg"),
            ("notes", "file", "v1_draft", "notes.bin"),
            ("template", "file", "東京", "template.bin"),
            # A fallback is held to the same rule, and `file` stands in when it leaves nothing either.
            ("東京都", "Pipe Code.v2", "pdf", "Pipe-Code-v2.pdf"),
            ("東京都", "Москва", "pdf", "file.pdf"),
        ],
    )
    def test_extensions_and_fallbacks_are_held_to_the_hosted_grammar(self, name: str, fallback: str, extension: str, expected: str) -> None:
        file_name = path_safe_file_name(name=name, fallback=fallback, extension=extension)

        assert file_name == expected
        _assert_hosted_grammar_accepts(file_name)
