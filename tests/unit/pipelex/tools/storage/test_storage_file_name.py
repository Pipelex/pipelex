import re

import pytest

from pipelex.tools.storage.storage_file_name import (
    STORAGE_FILE_EXTENSION_PATTERN,
    STORAGE_FILE_STEM_PATTERN,
    fold_to_ascii,
    path_safe_file_name,
)

# The hosted platform's grammar for the last segment of a `pipelex-storage://` URI, copied from `_SEGMENT_PATTERN` and
# `_EXTENSION_PATTERN` in pipelex-server's `shared/src/pipelex_shared/domain/storage/storage_uri.py`
# (`parse_storage_uri`). The runtime restates it rather than importing it, so this pins the two to one rule.
_HOSTED_STEM_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_HOSTED_EXTENSION_PATTERN = re.compile(r"^[A-Za-z0-9]+$")


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
        ("name", "fallback", "extension", "expected"),
        [
            # A template file's own name, with its own extension.
            ("modèle.v2.docx", "file", "docx", "modele-v2.docx"),
            ("Invoice Template.DOCX", "file", "DOCX", "Invoice-Template.docx"),
            # An extension is lowercased and kept to its ASCII letters and digits, `bin` when none is left.
            ("template", "file", "", "template.bin"),
            ("template", "file", ".x-l_s.x", "template.xlsx"),
            ("template", "file", "東京", "template.bin"),
            # A fallback is held to the same rule, and `file` stands in when it leaves nothing either.
            ("東京都", "Pipe Code.v2", "pdf", "Pipe-Code-v2.pdf"),
            ("東京都", "Москва", "pdf", "file.pdf"),
        ],
    )
    def test_every_name_it_gives_is_one_the_hosted_grammar_accepts(self, name: str, fallback: str, extension: str, expected: str) -> None:
        file_name = path_safe_file_name(name=name, fallback=fallback, extension=extension)

        assert file_name == expected
        stem, safe_extension = file_name.rsplit(".", 1)
        assert _HOSTED_STEM_PATTERN.match(stem)
        assert _HOSTED_EXTENSION_PATTERN.match(safe_extension)
