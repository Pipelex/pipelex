import os

import pytest

from pipelex.tools.storage.storage_provider_abstract import PIPELEX_STORAGE_SCHEME
from pipelex.tools.uri.resolved_uri import (
    ResolvedBase64DataUrl,
    ResolvedHttpUrl,
    ResolvedLocalPath,
    ResolvedPipelexStorage,
    ResolvedUri,
    UriKind,
)
from pipelex.tools.uri.uri_resolver import resolve_uri
from pipelex.urls import URLs


class TestResolveUriHttpUrls:
    """Tests for resolving HTTP/HTTPS URLs."""

    def test_resolve_https_url(self) -> None:
        """Test that HTTPS URLs are resolved_uri to ResolvedHttpUrl."""
        uri = URLs.png_example_1

        resolved_uri = resolve_uri(uri)

        assert resolved_uri.kind == UriKind.HTTP_URL
        assert isinstance(resolved_uri, ResolvedHttpUrl)
        assert resolved_uri.url == uri
        assert resolved_uri.original == uri

    def test_resolve_http_url(self) -> None:
        """Test that HTTP URLs are resolved_uri to ResolvedHttpUrl."""
        uri = URLs.txt_example

        resolved_uri = resolve_uri(uri)

        assert resolved_uri.kind == UriKind.HTTP_URL
        assert isinstance(resolved_uri, ResolvedHttpUrl)
        assert resolved_uri.url == uri
        assert resolved_uri.original == uri

    def test_resolve_http_url_with_query_params(self) -> None:
        """Test that HTTP URLs with query parameters are preserved."""
        uri = "https://example.com/api?key=value&other=123"

        resolved_uri = resolve_uri(uri)

        assert resolved_uri.kind == UriKind.HTTP_URL
        assert isinstance(resolved_uri, ResolvedHttpUrl)
        assert resolved_uri.url == uri

    def test_resolve_http_url_with_fragment(self) -> None:
        """Test that HTTP URLs with fragments are preserved."""
        uri = "https://example.com/page#section"

        resolved_uri = resolve_uri(uri)

        assert resolved_uri.kind == UriKind.HTTP_URL
        assert isinstance(resolved_uri, ResolvedHttpUrl)
        assert resolved_uri.url == uri


class TestResolveUriLocalPaths:
    """Tests for resolving local file paths."""

    def test_resolve_absolute_unix_path(self) -> None:
        """Test that absolute Unix paths are resolved_uri to ResolvedLocalPath."""
        uri = "/home/user/documents/file.txt"

        resolved_uri = resolve_uri(uri)

        assert resolved_uri.kind == UriKind.LOCAL_PATH
        assert isinstance(resolved_uri, ResolvedLocalPath)
        assert resolved_uri.path == uri
        assert resolved_uri.original == uri

    def test_resolve_relative_path_with_separator(self) -> None:
        """Test that relative paths with OS separator are resolved_uri to ResolvedLocalPath."""
        uri = f"user{os.sep}documents{os.sep}file.txt"

        resolved_uri = resolve_uri(uri)

        assert resolved_uri.kind == UriKind.LOCAL_PATH
        assert isinstance(resolved_uri, ResolvedLocalPath)
        assert resolved_uri.path == uri

    def test_resolve_file_name_only(self) -> None:
        """Test that simple file names are resolved_uri to ResolvedLocalPath."""
        uri = "document.pdf"

        resolved_uri = resolve_uri(uri)

        assert resolved_uri.kind == UriKind.LOCAL_PATH
        assert isinstance(resolved_uri, ResolvedLocalPath)
        assert resolved_uri.path == uri

    def test_resolve_file_name_without_extension(self) -> None:
        """Test that file names without extensions are resolved_uri to ResolvedLocalPath."""
        uri = "readme"

        resolved_uri = resolve_uri(uri)

        assert resolved_uri.kind == UriKind.LOCAL_PATH
        assert isinstance(resolved_uri, ResolvedLocalPath)
        assert resolved_uri.path == uri


class TestResolveUriFileUri:
    """Tests for resolving file:// URIs."""

    def test_resolve_file_uri_unix(self) -> None:
        """Test that file:// URIs are converted to local paths."""
        uri = "file:///home/user/file.txt"

        resolved_uri = resolve_uri(uri)

        assert resolved_uri.kind == UriKind.LOCAL_PATH
        assert isinstance(resolved_uri, ResolvedLocalPath)
        assert resolved_uri.path == "/home/user/file.txt"
        assert resolved_uri.original == uri

    def test_resolve_file_uri_with_spaces(self) -> None:
        """Test that file:// URIs with URL-encoded spaces are decoded."""
        uri = "file:///home/user/my%20document.txt"

        resolved_uri = resolve_uri(uri)

        assert resolved_uri.kind == UriKind.LOCAL_PATH
        assert isinstance(resolved_uri, ResolvedLocalPath)
        assert resolved_uri.path == "/home/user/my document.txt"

    def test_resolve_file_uri_with_special_chars(self) -> None:
        """Test that file:// URIs with special characters are decoded."""
        uri = "file:///home/user/file%20%26%20more.txt"

        resolved_uri = resolve_uri(uri)

        assert resolved_uri.kind == UriKind.LOCAL_PATH
        assert isinstance(resolved_uri, ResolvedLocalPath)
        assert resolved_uri.path == "/home/user/file & more.txt"

    def test_resolve_file_uri_windows_style(self) -> None:
        """Test that Windows file:// URIs are converted."""
        uri = "file:///C:/Users/user/file.txt"

        resolved_uri = resolve_uri(uri)

        assert resolved_uri.kind == UriKind.LOCAL_PATH
        assert isinstance(resolved_uri, ResolvedLocalPath)
        # The path includes the leading slash from the URI
        assert resolved_uri.path == "/C:/Users/user/file.txt"


class TestResolveUriPipelexStorage:
    """Tests for resolving pipelex-storage:// URIs."""

    def test_resolve_pipelex_storage_uri(self) -> None:
        """Test that pipelex-storage:// URIs are resolved_uri to ResolvedPipelexStorage."""
        uri = f"{PIPELEX_STORAGE_SCHEME}images/photo.png"

        resolved_uri = resolve_uri(uri)

        assert resolved_uri.kind == UriKind.PIPELEX_STORAGE
        assert isinstance(resolved_uri, ResolvedPipelexStorage)
        assert resolved_uri.storage_uri == uri
        assert resolved_uri.original == uri

    def test_resolve_pipelex_storage_uri_nested_path(self) -> None:
        """Test pipelex-storage:// URIs with nested paths."""
        uri = f"{PIPELEX_STORAGE_SCHEME}user123/run456/outputs/image.jpg"

        resolved_uri = resolve_uri(uri)

        assert resolved_uri.kind == UriKind.PIPELEX_STORAGE
        assert isinstance(resolved_uri, ResolvedPipelexStorage)
        assert resolved_uri.storage_uri == uri

    def test_resolve_pipelex_storage_takes_precedence(self) -> None:
        """Test that pipelex-storage:// is detected before path separator check."""
        uri = f"{PIPELEX_STORAGE_SCHEME}path/with/separators/file.bin"

        resolved_uri = resolve_uri(uri)

        assert resolved_uri.kind == UriKind.PIPELEX_STORAGE
        assert isinstance(resolved_uri, ResolvedPipelexStorage)


class TestResolveUriBase64DataUrl:
    """Tests for resolving base64 data URLs."""

    def test_resolve_base64_data_url_png(self) -> None:
        """Test that data: URLs with base64 encoding are resolved_uri to ResolvedBase64DataUrl."""
        base64_content = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        uri = f"data:image/png;base64,{base64_content}"

        resolved_uri = resolve_uri(uri)

        assert resolved_uri.kind == UriKind.BASE64_DATA_URL
        assert isinstance(resolved_uri, ResolvedBase64DataUrl)
        assert resolved_uri.mime_type == "image/png"
        assert resolved_uri.base64_data == base64_content
        assert resolved_uri.original == uri

    def test_resolve_base64_data_url_jpeg(self) -> None:
        """Test base64 data URL with JPEG mime type."""
        base64_content = "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRof"
        uri = f"data:image/jpeg;base64,{base64_content}"

        resolved_uri = resolve_uri(uri)

        assert resolved_uri.kind == UriKind.BASE64_DATA_URL
        assert isinstance(resolved_uri, ResolvedBase64DataUrl)
        assert resolved_uri.mime_type == "image/jpeg"
        assert resolved_uri.base64_data == base64_content

    def test_resolve_base64_data_url_pdf(self) -> None:
        """Test base64 data URL with PDF mime type."""
        base64_content = "JVBERi0xLjQKJeLjz9MKMyAwIG9iago8PC9UeXBlL0NhdGFsb2cvUGFnZXMgMiAwIFI+PgplbmRvYmo="
        uri = f"data:application/pdf;base64,{base64_content}"

        resolved_uri = resolve_uri(uri)

        assert resolved_uri.kind == UriKind.BASE64_DATA_URL
        assert isinstance(resolved_uri, ResolvedBase64DataUrl)
        assert resolved_uri.mime_type == "application/pdf"
        assert resolved_uri.base64_data == base64_content

    def test_resolve_base64_data_url_webp(self) -> None:
        """Test base64 data URL with WebP mime type."""
        base64_content = "UklGRhYAAABXRUJQVlA4TAoAAAAvAAAAABPpAA=="
        uri = f"data:image/webp;base64,{base64_content}"

        resolved_uri = resolve_uri(uri)

        assert resolved_uri.kind == UriKind.BASE64_DATA_URL
        assert isinstance(resolved_uri, ResolvedBase64DataUrl)
        assert resolved_uri.mime_type == "image/webp"


class TestResolveUriEdgeCases:
    """Tests for edge cases and validation."""

    def test_resolve_empty_string(self) -> None:
        """Test that empty strings are resolved_uri to ResolvedLocalPath."""
        uri = ""

        resolved_uri = resolve_uri(uri)

        assert resolved_uri.kind == UriKind.LOCAL_PATH
        assert isinstance(resolved_uri, ResolvedLocalPath)
        assert resolved_uri.path == ""

    def test_resolve_http_in_filename(self) -> None:
        """Test that 'http' in a file path doesn't trigger HTTP URL detection."""
        uri = "/path/to/http_config.txt"

        resolved_uri = resolve_uri(uri)

        assert resolved_uri.kind == UriKind.LOCAL_PATH
        assert isinstance(resolved_uri, ResolvedLocalPath)
        assert resolved_uri.path == uri

    def test_resolve_file_in_http_url(self) -> None:
        """Test that 'file' in an HTTP URL doesn't trigger file path detection."""
        uri = "https://example.com/download/file.txt"

        resolved_uri = resolve_uri(uri)

        assert resolved_uri.kind == UriKind.HTTP_URL
        assert isinstance(resolved_uri, ResolvedHttpUrl)

    def test_data_url_without_base64_is_not_base64_data_url(self) -> None:
        """Test that data: URLs without ;base64, are treated as local paths."""
        uri = "data:text/plain,Hello%20World"

        resolved_uri = resolve_uri(uri)

        # Without ;base64, this is not a base64 data URL
        # It should fall through to local path (has no path separator)
        assert resolved_uri.kind == UriKind.LOCAL_PATH


class TestUriKindEnum:
    """Tests for the UriKind StrEnum."""

    def test_uri_kind_values(self) -> None:
        """Test that UriKind has the expected values."""
        assert UriKind.HTTP_URL == "http_url"
        assert UriKind.LOCAL_PATH == "local_path"
        assert UriKind.PIPELEX_STORAGE == "pipelex_storage"
        assert UriKind.BASE64_DATA_URL == "base64_data_url"

    def test_uri_kind_is_string(self) -> None:
        """Test that UriKind values work as strings."""
        assert str(UriKind.HTTP_URL) == "http_url"
        assert f"{UriKind.LOCAL_PATH}" == "local_path"

    def test_uri_kind_desc_property(self) -> None:
        """Test that UriKind.desc returns human-readable descriptions."""
        assert UriKind.HTTP_URL.desc == "HTTP URL"
        assert UriKind.LOCAL_PATH.desc == "Local path"
        assert UriKind.PIPELEX_STORAGE.desc == "Pipelex Storage"
        assert UriKind.BASE64_DATA_URL.desc == "Base64 data URL"


class TestResolvedUriModels:
    """Tests for ResolvedUri model properties."""

    def test_resolved_http_url_model(self) -> None:
        """Test ResolvedHttpUrl model structure."""
        resolved_uri = ResolvedHttpUrl(
            original="https://example.com",
            url="https://example.com",
        )

        assert resolved_uri.kind == UriKind.HTTP_URL
        assert resolved_uri.original == "https://example.com"
        assert resolved_uri.url == "https://example.com"

    def test_resolved_local_path_model(self) -> None:
        """Test ResolvedLocalPath model structure."""
        resolved_uri = ResolvedLocalPath(
            original="/path/to/file",
            path="/path/to/file",
        )

        assert resolved_uri.kind == UriKind.LOCAL_PATH
        assert resolved_uri.original == "/path/to/file"
        assert resolved_uri.path == "/path/to/file"

    def test_resolved_pipelex_storage_model(self) -> None:
        """Test ResolvedPipelexStorage model structure."""
        storage_uri = f"{PIPELEX_STORAGE_SCHEME}key/file.bin"
        resolved_uri = ResolvedPipelexStorage(
            original=storage_uri,
            storage_uri=storage_uri,
        )

        assert resolved_uri.kind == UriKind.PIPELEX_STORAGE
        assert resolved_uri.original == storage_uri
        assert resolved_uri.storage_uri == storage_uri

    def test_resolved_base64_data_url_model(self) -> None:
        """Test ResolvedBase64DataUrl model structure."""
        resolved_uri = ResolvedBase64DataUrl(
            original="data:image/png;base64,abc123",
            mime_type="image/png",
            base64_data="abc123",
        )

        assert resolved_uri.kind == UriKind.BASE64_DATA_URL
        assert resolved_uri.original == "data:image/png;base64,abc123"
        assert resolved_uri.mime_type == "image/png"
        assert resolved_uri.base64_data == "abc123"


class TestResolvedUriTypeUnion:
    """Tests for the ResolvedUri union type."""

    @pytest.mark.parametrize(
        ("uri", "expected_kind"),
        [
            ("https://example.com", UriKind.HTTP_URL),
            ("http://example.com", UriKind.HTTP_URL),
            ("/absolute/path.txt", UriKind.LOCAL_PATH),
            ("relative/path.txt", UriKind.LOCAL_PATH),
            ("filename.txt", UriKind.LOCAL_PATH),
            ("file:///home/user/file.txt", UriKind.LOCAL_PATH),
            (f"{PIPELEX_STORAGE_SCHEME}key/file.bin", UriKind.PIPELEX_STORAGE),
            ("data:image/png;base64,abc", UriKind.BASE64_DATA_URL),
        ],
    )
    def test_resolve_uri_returns_correct_kind(self, uri: str, expected_kind: UriKind) -> None:
        """Test that resolve_uri returns the correct kind for various URIs."""
        resolved_uri = resolve_uri(uri)
        assert resolved_uri.kind == expected_kind

    def test_resolved_uri_type_annotation(self) -> None:
        """Test that ResolvedUri type annotation works for all variants."""
        results: list[ResolvedUri] = [
            resolve_uri("https://example.com"),
            resolve_uri("/path/to/file"),
            resolve_uri(f"{PIPELEX_STORAGE_SCHEME}key"),
            resolve_uri("data:image/png;base64,abc"),
        ]

        kinds = [result.kind for result in results]
        assert UriKind.HTTP_URL in kinds
        assert UriKind.LOCAL_PATH in kinds
        assert UriKind.PIPELEX_STORAGE in kinds
        assert UriKind.BASE64_DATA_URL in kinds


class TestResolvedUriMatchCase:
    """Tests demonstrating match/case pattern matching with ResolvedUri types.

    These tests verify that:
    1. Class pattern matching works correctly with ResolvedUri discriminated union
    2. Type narrowing allows direct attribute access without isinstance assertions
    3. All union variants are properly handled (exhaustiveness)
    """

    def test_match_case_http_url(self) -> None:
        """Test match/case correctly narrows type to ResolvedHttpUrl."""
        resolved_uri = resolve_uri("https://api.example.com/data")

        result: str
        match resolved_uri:
            case ResolvedHttpUrl():
                # Type is narrowed: can access .url directly
                result = f"HTTP: {resolved_uri.url}"
            case ResolvedLocalPath():
                result = f"Path: {resolved_uri.path}"
            case ResolvedPipelexStorage():
                result = f"Storage: {resolved_uri.storage_uri}"
            case ResolvedBase64DataUrl():
                result = f"Data: {resolved_uri.mime_type}"

        assert result == "HTTP: https://api.example.com/data"

    def test_match_case_local_path(self) -> None:
        """Test match/case correctly narrows type to ResolvedLocalPath."""
        resolved_uri = resolve_uri("/home/user/document.pdf")

        result: str
        match resolved_uri:
            case ResolvedHttpUrl():
                result = f"HTTP: {resolved_uri.url}"
            case ResolvedLocalPath():
                # Type is narrowed: can access .path directly
                result = f"Path: {resolved_uri.path}"
            case ResolvedPipelexStorage():
                result = f"Storage: {resolved_uri.storage_uri}"
            case ResolvedBase64DataUrl():
                result = f"Data: {resolved_uri.mime_type}"

        assert result == "Path: /home/user/document.pdf"

    def test_match_case_pipelex_storage(self) -> None:
        """Test match/case correctly narrows type to ResolvedPipelexStorage."""
        uri = f"{PIPELEX_STORAGE_SCHEME}run123/output.png"
        resolved_uri = resolve_uri(uri)

        result: str
        match resolved_uri:
            case ResolvedHttpUrl():
                result = f"HTTP: {resolved_uri.url}"
            case ResolvedLocalPath():
                result = f"Path: {resolved_uri.path}"
            case ResolvedPipelexStorage():
                # Type is narrowed: can access .storage_uri directly
                result = f"Storage: {resolved_uri.storage_uri}"
            case ResolvedBase64DataUrl():
                result = f"Data: {resolved_uri.mime_type}"

        assert result == f"Storage: {uri}"

    def test_match_case_base64_data_url(self) -> None:
        """Test match/case correctly narrows type to ResolvedBase64DataUrl."""
        resolved_uri = resolve_uri("data:image/webp;base64,UklGRhYA")

        result: str
        match resolved_uri:
            case ResolvedHttpUrl():
                result = f"HTTP: {resolved_uri.url}"
            case ResolvedLocalPath():
                result = f"Path: {resolved_uri.path}"
            case ResolvedPipelexStorage():
                result = f"Storage: {resolved_uri.storage_uri}"
            case ResolvedBase64DataUrl():
                # Type is narrowed: can access .mime_type and .base64_data directly
                result = f"Data: {resolved_uri.mime_type}, {len(resolved_uri.base64_data)} chars"

        assert result == "Data: image/webp, 8 chars"

    def test_match_case_combined_cases(self) -> None:
        """Test match/case with combined case patterns using | operator."""
        test_uris = [
            "https://example.com/file.txt",
            "/local/file.txt",
            f"{PIPELEX_STORAGE_SCHEME}key",
            "data:text/plain;base64,SGVsbG8=",
        ]

        results: list[str] = []
        for uri in test_uris:
            resolved_uri = resolve_uri(uri)
            match resolved_uri:
                case ResolvedHttpUrl() | ResolvedLocalPath():
                    # Both provide path-like access
                    results.append("fetchable")
                case ResolvedPipelexStorage() | ResolvedBase64DataUrl():
                    # Both require special handling
                    results.append("special")

        assert results == ["fetchable", "fetchable", "special", "special"]

    def test_match_case_access_common_attributes(self) -> None:
        """Test that common attributes (kind, original) are accessible in all cases."""
        uris = [
            "https://example.com",
            "/path/to/file",
            f"{PIPELEX_STORAGE_SCHEME}key",
            "data:image/png;base64,abc",
        ]

        for uri in uris:
            resolved_uri = resolve_uri(uri)
            # .original is always available on base class
            assert resolved_uri.original == uri
            # .kind is always available and matches the case
            match resolved_uri:
                case ResolvedHttpUrl():
                    assert resolved_uri.kind == UriKind.HTTP_URL
                case ResolvedLocalPath():
                    assert resolved_uri.kind == UriKind.LOCAL_PATH
                case ResolvedPipelexStorage():
                    assert resolved_uri.kind == UriKind.PIPELEX_STORAGE
                case ResolvedBase64DataUrl():
                    assert resolved_uri.kind == UriKind.BASE64_DATA_URL
