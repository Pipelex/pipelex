from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from mthds.protocol.input_form import PipeInputFormDescriptor

from pipelex.hosted.hosted_inputs import anchor_local_file_sources, inputs_name_a_local_file
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
                "a URL scheme is told apart whatever its case, as the SDK tells it",
                {"document": "HTTPS://example.com/invoice.pdf", "pages": ["Http://example.com/page.png"]},
                {"document": "HTTPS://example.com/invoice.pdf", "pages": ["Http://example.com/page.png"]},
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
                "a file URI is the local path it names, as a local run reads it",
                {"document": "file:///scans/invoice%20v2.pdf", "pages": [{"url": "file:///scans/page.png"}]},
                {"document": "/scans/invoice v2.pdf", "pages": [{"url": "/scans/page.png"}]},
                ["/scans/invoice v2.pdf", "/scans/page.png"],
            ),
            (
                "an explicit null at a file position is no file, and stays null",
                {"report": {"title": "Report", "cover": None}, "pages": [None]},
                {"report": {"title": "Report", "cover": None}, "pages": [None]},
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

    def test_inputs_name_a_local_file_when_a_string_at_any_depth_is_an_existing_file(self, tmp_path: Path) -> None:
        """Whether to read the signature at all is decided before reading it: any string naming a file on this machine."""
        (tmp_path / "scans").mkdir()
        (tmp_path / "scans" / "invoice.pdf").write_bytes(b"%PDF")
        assert inputs_name_a_local_file(inputs={"document": "scans/invoice.pdf"}, base_dir=tmp_path)
        assert inputs_name_a_local_file(inputs={"report": {"pages": [{"url": "scans/invoice.pdf"}]}}, base_dir=tmp_path)
        assert inputs_name_a_local_file(inputs={"document": str(tmp_path / "scans" / "invoice.pdf")}, base_dir=None)
        assert inputs_name_a_local_file(inputs={"document": (tmp_path / "scans" / "invoice.pdf").as_uri()}, base_dir=None)

    def test_a_relative_path_also_counts_from_the_working_directory(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        (tmp_path / "invoice.pdf").write_bytes(b"%PDF")
        monkeypatch.chdir(tmp_path)
        assert inputs_name_a_local_file(inputs={"document": "invoice.pdf"}, base_dir=None)
        assert inputs_name_a_local_file(inputs={"document": "invoice.pdf"}, base_dir=tmp_path / "elsewhere")

    @pytest.mark.parametrize(
        ("topic", "inputs"),
        [
            ("no file is named", {"text": "a widget", "count": 3, "flag": True, "cover": None}),
            ("a missing file is not a local file", {"document": "missing.pdf"}),
            ("a directory is not a file", {"document": "."}),
            (
                "the remote forms are never local files",
                {"a": "https://example.com/x.pdf", "b": "HTTP://example.com/y.pdf", "c": "pipelex-storage://u/z.pdf", "d": "data:text/plain,hi"},
            ),
            ("a long text is not a path", {"text": "word " * 5000}),
            ("a text naming an unknown home is not a path", {"text": "~nobody-by-this-name/x"}),
        ],
    )
    def test_inputs_naming_no_existing_local_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, topic: str, inputs: dict[str, Any]) -> None:
        monkeypatch.chdir(tmp_path)
        assert not inputs_name_a_local_file(inputs=inputs, base_dir=tmp_path), topic
