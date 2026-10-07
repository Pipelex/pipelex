from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from mthds.protocol.input_form import PipeInputFormDescriptor

from pipelex.hosted.hosted_inputs import anchor_local_file_sources
from tests.unit.pipelex.hosted.test_data import HostedDescriptors

BASE_DIR = Path("/work/inputs")


def _descriptor() -> PipeInputFormDescriptor:
    return PipeInputFormDescriptor.model_validate_json(HostedDescriptors.MIXED_FILE_POSITIONS)


class TestHostedInputs:
    @pytest.mark.parametrize(
        ("topic", "inputs", "expected_inputs", "expected_local_sources"),
        [
            (
                "a compact relative document",
                {"document": "invoice.pdf"},
                {"document": "/work/inputs/invoice.pdf"},
                ["/work/inputs/invoice.pdf"],
            ),
            (
                "a document content keeps its other members",
                {"document": {"url": "scans/invoice.pdf", "mime_type": "application/pdf"}},
                {"document": {"url": "/work/inputs/scans/invoice.pdf", "mime_type": "application/pdf"}},
                ["/work/inputs/scans/invoice.pdf"],
            ),
            (
                "an absolute path is local but already anchored",
                {"document": "/elsewhere/invoice.pdf"},
                {"document": "/elsewhere/invoice.pdf"},
                ["/elsewhere/invoice.pdf"],
            ),
            (
                "a reachable URL, a storage URI and a data URL are not local files",
                {
                    "document": "https://example.com/invoice.pdf",
                    "pages": ["pipelex-storage://uploads/a.png", {"url": "data:image/png;base64,iVBORw0KGgo="}],
                },
                {
                    "document": "https://example.com/invoice.pdf",
                    "pages": ["pipelex-storage://uploads/a.png", {"url": "data:image/png;base64,iVBORw0KGgo="}],
                },
                [],
            ),
            (
                "a text that reads like a file name is not a file position",
                {"notes": "invoice.pdf"},
                {"notes": "invoice.pdf"},
                [],
            ),
            (
                "an optional file nested in a structure",
                {"report": {"title": "cover.png", "cover": "cover.png"}},
                {"report": {"title": "cover.png", "cover": "/work/inputs/cover.png"}},
                ["/work/inputs/cover.png"],
            ),
            (
                "each image of a list, compact or as content",
                {"pages": ["page1.png", {"url": "page2.png"}]},
                {"pages": ["/work/inputs/page1.png", {"url": "/work/inputs/page2.png"}]},
                ["/work/inputs/page1.png", "/work/inputs/page2.png"],
            ),
            (
                "an explicit envelope is walked through its content",
                {"document": {"concept": "native.Document", "content": {"url": "invoice.pdf"}}},
                {"document": {"concept": "native.Document", "content": {"url": "/work/inputs/invoice.pdf"}}},
                ["/work/inputs/invoice.pdf"],
            ),
            (
                "an input the signature does not declare passes through",
                {"extra": "invoice.pdf"},
                {"extra": "invoice.pdf"},
                [],
            ),
            (
                "a value whose shape disagrees with its position is left for the run to refuse",
                {"document": ["invoice.pdf"], "pages": "page.png"},
                {"document": ["invoice.pdf"], "pages": "page.png"},
                [],
            ),
        ],
    )
    def test_local_files_are_found_and_anchored_where_the_signature_declares_them(
        self,
        topic: str,
        inputs: dict[str, Any],
        expected_inputs: dict[str, Any],
        expected_local_sources: list[str],
    ) -> None:
        """Only a document or image position holds a file, whatever a value looks like elsewhere."""
        anchored = anchor_local_file_sources(inputs=inputs, descriptor=_descriptor(), base_dir=BASE_DIR)
        assert anchored.inputs == expected_inputs, topic
        assert anchored.local_sources == expected_local_sources, topic

    def test_the_caller_inputs_are_not_mutated(self) -> None:
        inputs: dict[str, Any] = {"document": {"url": "invoice.pdf"}, "pages": ["page.png"]}
        anchor_local_file_sources(inputs=inputs, descriptor=_descriptor(), base_dir=BASE_DIR)
        assert inputs == {"document": {"url": "invoice.pdf"}, "pages": ["page.png"]}

    def test_without_a_base_directory_a_relative_path_stays_relative(self) -> None:
        """Inline inputs have no file to anchor to: the path is read from the working directory, as a local run reads it."""
        anchored = anchor_local_file_sources(inputs={"document": "invoice.pdf"}, descriptor=_descriptor(), base_dir=None)
        assert anchored.inputs == {"document": "invoice.pdf"}
        assert anchored.local_sources == ["invoice.pdf"]

    def test_a_home_relative_path_is_expanded(self) -> None:
        anchored = anchor_local_file_sources(inputs={"document": "~/invoice.pdf"}, descriptor=_descriptor(), base_dir=BASE_DIR)
        expected = str(Path("~/invoice.pdf").expanduser())
        assert anchored.inputs == {"document": expected}
        assert anchored.local_sources == [expected]
