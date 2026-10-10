"""The shared analysis of the files a prompt template reads, which every prompt-shaped factory calls."""

from pathlib import Path
from typing import Callable

import pytest

from pipelex.kernel.prompt_references import DocumentReferenceKind, ImageReferenceKind
from pipelex.pipe_operators.shared.template_file_references import analyze_template_file_references


class TestTemplateFileReferences:
    def test_images_and_documents_are_found_in_one_pass(self, load_test_library: Callable[[list[Path]], None]) -> None:
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        file_references = analyze_template_file_references(
            template_source="Compare $note with $photo and $claim, then $album and $annexes",
            input_specs={"note": "Text", "photo": "Image", "claim": "Document", "album": "Image[]", "annexes": "Document[]"},
            domain_code="test_pipes",
        )

        assert [(reference.variable_path, reference.kind) for reference in file_references.image_references] == [
            ("photo", ImageReferenceKind.DIRECT),
            ("album", ImageReferenceKind.DIRECT_LIST),
        ]
        assert [(reference.variable_path, reference.kind) for reference in file_references.document_references] == [
            ("claim", DocumentReferenceKind.DIRECT),
            ("annexes", DocumentReferenceKind.DIRECT_LIST),
        ]

    @pytest.mark.parametrize(
        ("presence_suffix", "is_optional"),
        [
            pytest.param("?", True, id="optional"),
            pytest.param("", False, id="required"),
            pytest.param("!", False, id="forced"),
        ],
    )
    def test_each_reference_says_whether_its_root_input_is_optional(
        self, load_test_library: Callable[[list[Path]], None], presence_suffix: str, is_optional: bool
    ) -> None:
        """The assembly skips an absent optional input's file and refuses an absent required one, so the mark must be exact."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        file_references = analyze_template_file_references(
            template_source="@?photo\n@?claim\n",
            input_specs={"photo": f"Image{presence_suffix}", "claim": f"Document{presence_suffix}"},
            domain_code="test_pipes",
        )

        assert [reference.is_optional for reference in file_references.image_references] == [is_optional]
        assert [reference.is_optional for reference in file_references.document_references] == [is_optional]
