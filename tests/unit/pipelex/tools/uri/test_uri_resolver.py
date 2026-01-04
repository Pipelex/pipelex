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


class TestResolveUriHttpUrls:
    """Tests for resolving HTTP/HTTPS URLs."""

    def test_resolve_https_url(self) -> None:
        """Test that HTTPS URLs are resolved to ResolvedHttpUrl."""
        uri = "https://example.com/image.png"

        resolved = resolve_uri(uri)

        assert resolved.kind == UriKind.HTTP_URL
        assert isinstance(resolved, ResolvedHttpUrl)
        assert resolved.url == uri
        assert resolved.original == uri

    def test_resolve_http_url(self) -> None:
        """Test that HTTP URLs are resolved to ResolvedHttpUrl."""
        uri = "http://example.com/path/to/file.txt"

        resolved = resolve_uri(uri)

        assert resolved.kind == UriKind.HTTP_URL
        assert isinstance(resolved, ResolvedHttpUrl)
        assert resolved.url == uri
        assert resolved.original == uri

    def test_resolve_http_url_with_query_params(self) -> None:
        """Test that HTTP URLs with query parameters are preserved."""
        uri = "https://example.com/api?key=value&other=123"

        resolved = resolve_uri(uri)

        assert resolved.kind == UriKind.HTTP_URL
        assert isinstance(resolved, ResolvedHttpUrl)
        assert resolved.url == uri

    def test_resolve_http_url_with_fragment(self) -> None:
        """Test that HTTP URLs with fragments are preserved."""
        uri = "https://example.com/page#section"

        resolved = resolve_uri(uri)

        assert resolved.kind == UriKind.HTTP_URL
        assert isinstance(resolved, ResolvedHttpUrl)
        assert resolved.url == uri


class TestResolveUriLocalPaths:
    """Tests for resolving local file paths."""

    def test_resolve_absolute_unix_path(self) -> None:
        """Test that absolute Unix paths are resolved to ResolvedLocalPath."""
        uri = "/home/user/documents/file.txt"

        resolved = resolve_uri(uri)

        assert resolved.kind == UriKind.LOCAL_PATH
        assert isinstance(resolved, ResolvedLocalPath)
        assert resolved.path == uri
        assert resolved.original == uri

    def test_resolve_relative_path_with_separator(self) -> None:
        """Test that relative paths with OS separator are resolved to ResolvedLocalPath."""
        uri = f"user{os.sep}documents{os.sep}file.txt"

        resolved = resolve_uri(uri)

        assert resolved.kind == UriKind.LOCAL_PATH
        assert isinstance(resolved, ResolvedLocalPath)
        assert resolved.path == uri

    def test_resolve_file_name_only(self) -> None:
        """Test that simple file names are resolved to ResolvedLocalPath."""
        uri = "document.pdf"

        resolved = resolve_uri(uri)

        assert resolved.kind == UriKind.LOCAL_PATH
        assert isinstance(resolved, ResolvedLocalPath)
        assert resolved.path == uri

    def test_resolve_file_name_without_extension(self) -> None:
        """Test that file names without extensions are resolved to ResolvedLocalPath."""
        uri = "readme"

        resolved = resolve_uri(uri)

        assert resolved.kind == UriKind.LOCAL_PATH
        assert isinstance(resolved, ResolvedLocalPath)
        assert resolved.path == uri


class TestResolveUriFileUri:
    """Tests for resolving file:// URIs."""

    def test_resolve_file_uri_unix(self) -> None:
        """Test that file:// URIs are converted to local paths."""
        uri = "file:///home/user/file.txt"

        resolved = resolve_uri(uri)

        assert resolved.kind == UriKind.LOCAL_PATH
        assert isinstance(resolved, ResolvedLocalPath)
        assert resolved.path == "/home/user/file.txt"
        assert resolved.original == uri

    def test_resolve_file_uri_with_spaces(self) -> None:
        """Test that file:// URIs with URL-encoded spaces are decoded."""
        uri = "file:///home/user/my%20document.txt"

        resolved = resolve_uri(uri)

        assert resolved.kind == UriKind.LOCAL_PATH
        assert isinstance(resolved, ResolvedLocalPath)
        assert resolved.path == "/home/user/my document.txt"

    def test_resolve_file_uri_with_special_chars(self) -> None:
        """Test that file:// URIs with special characters are decoded."""
        uri = "file:///home/user/file%20%26%20more.txt"

        resolved = resolve_uri(uri)

        assert resolved.kind == UriKind.LOCAL_PATH
        assert isinstance(resolved, ResolvedLocalPath)
        assert resolved.path == "/home/user/file & more.txt"

    def test_resolve_file_uri_windows_style(self) -> None:
        """Test that Windows file:// URIs are converted."""
        uri = "file:///C:/Users/user/file.txt"

        resolved = resolve_uri(uri)

        assert resolved.kind == UriKind.LOCAL_PATH
        assert isinstance(resolved, ResolvedLocalPath)
        # The path includes the leading slash from the URI
        assert resolved.path == "/C:/Users/user/file.txt"


class TestResolveUriPipelexStorage:
    """Tests for resolving pipelex-storage:// URIs."""

    def test_resolve_pipelex_storage_uri(self) -> None:
        """Test that pipelex-storage:// URIs are resolved to ResolvedPipelexStorage."""
        uri = f"{PIPELEX_STORAGE_SCHEME}images/photo.png"

        resolved = resolve_uri(uri)

        assert resolved.kind == UriKind.PIPELEX_STORAGE
        assert isinstance(resolved, ResolvedPipelexStorage)
        assert resolved.storage_uri == uri
        assert resolved.original == uri

    def test_resolve_pipelex_storage_uri_nested_path(self) -> None:
        """Test pipelex-storage:// URIs with nested paths."""
        uri = f"{PIPELEX_STORAGE_SCHEME}user123/run456/outputs/image.jpg"

        resolved = resolve_uri(uri)

        assert resolved.kind == UriKind.PIPELEX_STORAGE
        assert isinstance(resolved, ResolvedPipelexStorage)
        assert resolved.storage_uri == uri

    def test_resolve_pipelex_storage_takes_precedence(self) -> None:
        """Test that pipelex-storage:// is detected before path separator check."""
        uri = f"{PIPELEX_STORAGE_SCHEME}path/with/separators/file.bin"

        resolved = resolve_uri(uri)

        assert resolved.kind == UriKind.PIPELEX_STORAGE
        assert isinstance(resolved, ResolvedPipelexStorage)


class TestResolveUriBase64DataUrl:
    """Tests for resolving base64 data URLs."""

    def test_resolve_base64_data_url_png(self) -> None:
        """Test that data: URLs with base64 encoding are resolved to ResolvedBase64DataUrl."""
        base64_content = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        uri = f"data:image/png;base64,{base64_content}"

        resolved = resolve_uri(uri)

        assert resolved.kind == UriKind.BASE64_DATA_URL
        assert isinstance(resolved, ResolvedBase64DataUrl)
        assert resolved.mime_type == "image/png"
        assert resolved.base64_data == base64_content
        assert resolved.original == uri

    def test_resolve_base64_data_url_jpeg(self) -> None:
        """Test base64 data URL with JPEG mime type."""
        base64_content = "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRof"
        uri = f"data:image/jpeg;base64,{base64_content}"

        resolved = resolve_uri(uri)

        assert resolved.kind == UriKind.BASE64_DATA_URL
        assert isinstance(resolved, ResolvedBase64DataUrl)
        assert resolved.mime_type == "image/jpeg"
        assert resolved.base64_data == base64_content

    def test_resolve_base64_data_url_pdf(self) -> None:
        """Test base64 data URL with PDF mime type."""
        base64_content = "JVBERi0xLjQKJeLjz9MKMyAwIG9iago8PC9UeXBlL0NhdGFsb2cvUGFnZXMgMiAwIFI+PgplbmRvYmo="
        uri = f"data:application/pdf;base64,{base64_content}"

        resolved = resolve_uri(uri)

        assert resolved.kind == UriKind.BASE64_DATA_URL
        assert isinstance(resolved, ResolvedBase64DataUrl)
        assert resolved.mime_type == "application/pdf"
        assert resolved.base64_data == base64_content

    def test_resolve_base64_data_url_webp(self) -> None:
        """Test base64 data URL with WebP mime type."""
        base64_content = "UklGRhYAAABXRUJQVlA4TAoAAAAvAAAAABPpAA=="
        uri = f"data:image/webp;base64,{base64_content}"

        resolved = resolve_uri(uri)

        assert resolved.kind == UriKind.BASE64_DATA_URL
        assert isinstance(resolved, ResolvedBase64DataUrl)
        assert resolved.mime_type == "image/webp"


class TestResolveUriEdgeCases:
    """Tests for edge cases and validation."""

    def test_resolve_empty_string(self) -> None:
        """Test that empty strings are resolved to ResolvedLocalPath."""
        uri = ""

        resolved = resolve_uri(uri)

        assert resolved.kind == UriKind.LOCAL_PATH
        assert isinstance(resolved, ResolvedLocalPath)
        assert resolved.path == ""

    def test_resolve_http_in_filename(self) -> None:
        """Test that 'http' in a file path doesn't trigger HTTP URL detection."""
        uri = "/path/to/http_config.txt"

        resolved = resolve_uri(uri)

        assert resolved.kind == UriKind.LOCAL_PATH
        assert isinstance(resolved, ResolvedLocalPath)
        assert resolved.path == uri

    def test_resolve_file_in_http_url(self) -> None:
        """Test that 'file' in an HTTP URL doesn't trigger file path detection."""
        uri = "https://example.com/download/file.txt"

        resolved = resolve_uri(uri)

        assert resolved.kind == UriKind.HTTP_URL
        assert isinstance(resolved, ResolvedHttpUrl)

    def test_data_url_without_base64_is_not_base64_data_url(self) -> None:
        """Test that data: URLs without ;base64, are treated as local paths."""
        uri = "data:text/plain,Hello%20World"

        resolved = resolve_uri(uri)

        # Without ;base64, this is not a base64 data URL
        # It should fall through to local path (has no path separator)
        assert resolved.kind == UriKind.LOCAL_PATH


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
        resolved = ResolvedHttpUrl(
            original="https://example.com",
            url="https://example.com",
        )

        assert resolved.kind == UriKind.HTTP_URL
        assert resolved.original == "https://example.com"
        assert resolved.url == "https://example.com"

    def test_resolved_local_path_model(self) -> None:
        """Test ResolvedLocalPath model structure."""
        resolved = ResolvedLocalPath(
            original="/path/to/file",
            path="/path/to/file",
        )

        assert resolved.kind == UriKind.LOCAL_PATH
        assert resolved.original == "/path/to/file"
        assert resolved.path == "/path/to/file"

    def test_resolved_pipelex_storage_model(self) -> None:
        """Test ResolvedPipelexStorage model structure."""
        storage_uri = f"{PIPELEX_STORAGE_SCHEME}key/file.bin"
        resolved = ResolvedPipelexStorage(
            original=storage_uri,
            storage_uri=storage_uri,
        )

        assert resolved.kind == UriKind.PIPELEX_STORAGE
        assert resolved.original == storage_uri
        assert resolved.storage_uri == storage_uri

    def test_resolved_base64_data_url_model(self) -> None:
        """Test ResolvedBase64DataUrl model structure."""
        resolved = ResolvedBase64DataUrl(
            original="data:image/png;base64,abc123",
            mime_type="image/png",
            base64_data="abc123",
        )

        assert resolved.kind == UriKind.BASE64_DATA_URL
        assert resolved.original == "data:image/png;base64,abc123"
        assert resolved.mime_type == "image/png"
        assert resolved.base64_data == "abc123"


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
        resolved = resolve_uri(uri)
        assert resolved.kind == expected_kind

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
        resolved = resolve_uri("https://api.example.com/data")

        result: str
        match resolved:
            case ResolvedHttpUrl():
                # Type is narrowed: can access .url directly
                result = f"HTTP: {resolved.url}"
            case ResolvedLocalPath():
                result = f"Path: {resolved.path}"
            case ResolvedPipelexStorage():
                result = f"Storage: {resolved.storage_uri}"
            case ResolvedBase64DataUrl():
                result = f"Data: {resolved.mime_type}"

        assert result == "HTTP: https://api.example.com/data"

    def test_match_case_local_path(self) -> None:
        """Test match/case correctly narrows type to ResolvedLocalPath."""
        resolved = resolve_uri("/home/user/document.pdf")

        result: str
        match resolved:
            case ResolvedHttpUrl():
                result = f"HTTP: {resolved.url}"
            case ResolvedLocalPath():
                # Type is narrowed: can access .path directly
                result = f"Path: {resolved.path}"
            case ResolvedPipelexStorage():
                result = f"Storage: {resolved.storage_uri}"
            case ResolvedBase64DataUrl():
                result = f"Data: {resolved.mime_type}"

        assert result == "Path: /home/user/document.pdf"

    def test_match_case_pipelex_storage(self) -> None:
        """Test match/case correctly narrows type to ResolvedPipelexStorage."""
        uri = f"{PIPELEX_STORAGE_SCHEME}run123/output.png"
        resolved = resolve_uri(uri)

        result: str
        match resolved:
            case ResolvedHttpUrl():
                result = f"HTTP: {resolved.url}"
            case ResolvedLocalPath():
                result = f"Path: {resolved.path}"
            case ResolvedPipelexStorage():
                # Type is narrowed: can access .storage_uri directly
                result = f"Storage: {resolved.storage_uri}"
            case ResolvedBase64DataUrl():
                result = f"Data: {resolved.mime_type}"

        assert result == f"Storage: {uri}"

    def test_match_case_base64_data_url(self) -> None:
        """Test match/case correctly narrows type to ResolvedBase64DataUrl."""
        resolved = resolve_uri("data:image/webp;base64,UklGRhYA")

        result: str
        match resolved:
            case ResolvedHttpUrl():
                result = f"HTTP: {resolved.url}"
            case ResolvedLocalPath():
                result = f"Path: {resolved.path}"
            case ResolvedPipelexStorage():
                result = f"Storage: {resolved.storage_uri}"
            case ResolvedBase64DataUrl():
                # Type is narrowed: can access .mime_type and .base64_data directly
                result = f"Data: {resolved.mime_type}, {len(resolved.base64_data)} chars"

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
            resolved = resolve_uri(uri)
            match resolved:
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
            resolved = resolve_uri(uri)
            # .original is always available on base class
            assert resolved.original == uri
            # .kind is always available and matches the case
            match resolved:
                case ResolvedHttpUrl():
                    assert resolved.kind == UriKind.HTTP_URL
                case ResolvedLocalPath():
                    assert resolved.kind == UriKind.LOCAL_PATH
                case ResolvedPipelexStorage():
                    assert resolved.kind == UriKind.PIPELEX_STORAGE
                case ResolvedBase64DataUrl():
                    assert resolved.kind == UriKind.BASE64_DATA_URL
