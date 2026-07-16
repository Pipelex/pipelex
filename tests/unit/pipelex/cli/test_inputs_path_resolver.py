"""Unit tests for _inputs_path_resolver: resolve relative url paths in pipeline inputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import pytest

from pipelex.cli.commands.run._inputs_path_resolver import resolve_inputs_paths, resolve_url_in_value  # noqa: PLC2701
from pipelex.tools.uri.uri_resolver import is_relative_local_path


class _IsRelativeLocalPathCases:
    RELATIVE_FILE = ("data/invoice.pdf", True)
    RELATIVE_NESTED = ("subdir/another/file.txt", True)
    BARE_FILENAME = ("invoice.pdf", True)
    ABSOLUTE_PATH = ("/home/user/data/invoice.pdf", False)
    HTTP_URL = ("https://example.com/file.pdf", False)
    HTTPS_URL = ("https://cdn.example.com/doc.pdf", False)
    DATA_URL = ("data:application/pdf;base64,AAAA", False)
    PIPELEX_STORAGE = ("pipelex-storage://bucket/file.pdf", False)
    FILE_URI = ("file:///home/user/file.pdf", False)
    # Unrecognized schemes must NOT be rewritten as relative local paths: resolve_uri returns them as
    # a ResolvedLocalPath but their `://` shows they are non-local, so the downstream remote guards work.
    S3_URL = ("s3://bucket/people.csv", False)
    GS_URL = ("gs://bucket/people.csv", False)


class _ResolveInputsPathsCases:
    """Parametrized test data for resolve_inputs_paths."""

    BASE_DIR: ClassVar[Path] = Path("/bundles/my_pipeline")

    RELATIVE_URL_IN_CONTENT: ClassVar[tuple[str, dict[str, Any], dict[str, Any]]] = (
        "relative url in content dict is resolved",
        {
            "source_doc": {
                "concept": "native.Document",
                "content": {"url": "data/invoice.pdf"},
            },
        },
        {
            "source_doc": {
                "concept": "native.Document",
                "content": {"url": "/bundles/my_pipeline/data/invoice.pdf"},
            },
        },
    )

    RELATIVE_URLS_IN_LIST: ClassVar[tuple[str, dict[str, Any], dict[str, Any]]] = (
        "relative urls in content list are resolved",
        {
            "docs": {
                "concept": "native.Document",
                "content": [
                    {"url": "data/f1.pdf"},
                    {"url": "data/f2.pdf"},
                ],
            },
        },
        {
            "docs": {
                "concept": "native.Document",
                "content": [
                    {"url": "/bundles/my_pipeline/data/f1.pdf"},
                    {"url": "/bundles/my_pipeline/data/f2.pdf"},
                ],
            },
        },
    )

    ABSOLUTE_PATH_UNCHANGED: ClassVar[tuple[str, dict[str, Any], dict[str, Any]]] = (
        "absolute paths are left unchanged",
        {
            "source_doc": {
                "concept": "native.Document",
                "content": {"url": "/absolute/path/file.pdf"},
            },
        },
        {
            "source_doc": {
                "concept": "native.Document",
                "content": {"url": "/absolute/path/file.pdf"},
            },
        },
    )

    HTTP_URL_UNCHANGED: ClassVar[tuple[str, dict[str, Any], dict[str, Any]]] = (
        "http urls are left unchanged",
        {
            "source_doc": {
                "concept": "native.Document",
                "content": {"url": "https://example.com/file.pdf"},
            },
        },
        {
            "source_doc": {
                "concept": "native.Document",
                "content": {"url": "https://example.com/file.pdf"},
            },
        },
    )

    DATA_URL_UNCHANGED: ClassVar[tuple[str, dict[str, Any], dict[str, Any]]] = (
        "data: urls are left unchanged",
        {
            "source_doc": {
                "concept": "native.Document",
                "content": {"url": "data:application/pdf;base64,AAAA"},
            },
        },
        {
            "source_doc": {
                "concept": "native.Document",
                "content": {"url": "data:application/pdf;base64,AAAA"},
            },
        },
    )

    PIPELEX_STORAGE_UNCHANGED: ClassVar[tuple[str, dict[str, Any], dict[str, Any]]] = (
        "pipelex-storage urls are left unchanged",
        {
            "source_doc": {
                "concept": "native.Document",
                "content": {"url": "pipelex-storage://bucket/file.pdf"},
            },
        },
        {
            "source_doc": {
                "concept": "native.Document",
                "content": {"url": "pipelex-storage://bucket/file.pdf"},
            },
        },
    )

    PLAIN_TEXT_UNCHANGED: ClassVar[tuple[str, dict[str, Any], dict[str, Any]]] = (
        "plain text inputs are left unchanged",
        {
            "topic": {
                "concept": "native.Text",
                "content": {"body": "summarize this document"},
            },
        },
        {
            "topic": {
                "concept": "native.Text",
                "content": {"body": "summarize this document"},
            },
        },
    )

    NESTED_URL_RESOLVED: ClassVar[tuple[str, dict[str, Any], dict[str, Any]]] = (
        "nested structured content urls are resolved",
        {
            "complex": {
                "concept": "native.Document",
                "content": {
                    "metadata": {"title": "Report"},
                    "attachments": [
                        {"url": "data/attachment.pdf", "label": "att1"},
                    ],
                },
            },
        },
        {
            "complex": {
                "concept": "native.Document",
                "content": {
                    "metadata": {"title": "Report"},
                    "attachments": [
                        {"url": "/bundles/my_pipeline/data/attachment.pdf", "label": "att1"},
                    ],
                },
            },
        },
    )

    EMPTY_DICT: ClassVar[tuple[str, dict[str, Any], dict[str, Any]]] = (
        "empty dict returns empty dict",
        {},
        {},
    )

    NO_URL_KEYS: ClassVar[tuple[str, dict[str, Any], dict[str, Any]]] = (
        "dict without url keys is unchanged",
        {
            "config": {
                "key": "value",
                "nested": {"a": 1, "b": 2},
            },
        },
        {
            "config": {
                "key": "value",
                "nested": {"a": 1, "b": 2},
            },
        },
    )


class TestInputsPathResolver:
    """Tests for is_relative_local_path, resolve_url_in_value, and resolve_inputs_paths."""

    # ---- is_relative_local_path ----

    @pytest.mark.parametrize(
        ("uri", "expected"),
        [
            _IsRelativeLocalPathCases.RELATIVE_FILE,
            _IsRelativeLocalPathCases.RELATIVE_NESTED,
            _IsRelativeLocalPathCases.BARE_FILENAME,
            _IsRelativeLocalPathCases.ABSOLUTE_PATH,
            _IsRelativeLocalPathCases.HTTP_URL,
            _IsRelativeLocalPathCases.HTTPS_URL,
            _IsRelativeLocalPathCases.DATA_URL,
            _IsRelativeLocalPathCases.PIPELEX_STORAGE,
            _IsRelativeLocalPathCases.FILE_URI,
            _IsRelativeLocalPathCases.S3_URL,
            _IsRelativeLocalPathCases.GS_URL,
        ],
    )
    def test_is_relative_local_path(self, uri: str, expected: bool) -> None:
        """Correctly classifies URIs as relative local paths or not."""
        assert is_relative_local_path(uri) == expected

    # ---- resolve_url_in_value ----

    def test_resolve_url_in_value_string_passthrough(self) -> None:
        """Non-dict, non-list values pass through unchanged."""
        assert resolve_url_in_value("hello", base_dir=Path("/base")) == "hello"
        assert resolve_url_in_value(42, base_dir=Path("/base")) == 42
        assert resolve_url_in_value(None, base_dir=Path("/base")) is None

    def test_resolve_url_in_value_tilde_expands_to_home(self) -> None:
        """A ~-prefixed url is home-anchored: it expands to home, never joined onto base_dir."""
        resolved = resolve_url_in_value({"url": "~/photo.jpg"}, base_dir=Path("/base"))
        assert resolved == {"url": str(Path("~/photo.jpg").expanduser())}

    # ---- resolve_inputs_paths ----

    @pytest.mark.parametrize(
        ("topic", "inputs_dict", "expected"),
        [
            _ResolveInputsPathsCases.RELATIVE_URL_IN_CONTENT,
            _ResolveInputsPathsCases.RELATIVE_URLS_IN_LIST,
            _ResolveInputsPathsCases.ABSOLUTE_PATH_UNCHANGED,
            _ResolveInputsPathsCases.HTTP_URL_UNCHANGED,
            _ResolveInputsPathsCases.DATA_URL_UNCHANGED,
            _ResolveInputsPathsCases.PIPELEX_STORAGE_UNCHANGED,
            _ResolveInputsPathsCases.PLAIN_TEXT_UNCHANGED,
            _ResolveInputsPathsCases.NESTED_URL_RESOLVED,
            _ResolveInputsPathsCases.EMPTY_DICT,
            _ResolveInputsPathsCases.NO_URL_KEYS,
        ],
    )
    def test_resolve_inputs_paths(self, topic: str, inputs_dict: dict[str, Any], expected: dict[str, Any]) -> None:  # noqa: ARG002
        """Resolves relative url paths in various input structures."""
        result = resolve_inputs_paths(inputs_dict, base_dir=_ResolveInputsPathsCases.BASE_DIR)
        assert result == expected
