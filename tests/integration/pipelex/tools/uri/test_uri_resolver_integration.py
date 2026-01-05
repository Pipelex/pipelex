import base64

import pytest

from pipelex.tools.misc.base64_utils import make_base64_url_from_http_url
from pipelex.tools.uri.resolved_uri import ResolvedHttpUrl, ResolvedLocalPath, UriKind
from pipelex.tools.uri.uri_resolver import make_base64_url_from_any_uri, resolve_uri
from tests.cases import ImageTestCases, TestURLs


@pytest.mark.codex_disabled
@pytest.mark.asyncio(loop_scope="class")
class TestUriResolverIntegration:
    """Integration tests for URI resolution with real network calls."""

    @pytest.mark.parametrize("url", TestURLs.PUBLIC_URLS)
    async def test_make_base64_url_from_http_url_async_real_network(self, url: str) -> None:
        """Test fetching and converting real HTTP URLs to base64 data URLs."""
        result = await make_base64_url_from_http_url(url=url)

        # Should start with data URL prefix
        assert result.startswith("data:")
        assert ";base64," in result

        # Verify the base64 part is valid
        base64_part = result.split(",", 1)[1]
        decoded = base64.b64decode(base64_part)
        # Should have some content
        assert len(decoded) > 0

    @pytest.mark.parametrize("url", TestURLs.PUBLIC_URLS)
    async def test_make_base64_url_from_uri_async_with_http_url(self, url: str) -> None:
        """Test full URI resolution workflow with HTTP URLs."""
        # First verify the URL resolves correctly
        resolved = resolve_uri(url)
        assert resolved.kind == UriKind.HTTP_URL
        assert isinstance(resolved, ResolvedHttpUrl)
        assert resolved.url == url

        # Then test the full conversion workflow
        result = await make_base64_url_from_any_uri(url)

        assert result.startswith("data:")
        assert ";base64," in result
        base64_part = result.split(",", 1)[1]
        decoded = base64.b64decode(base64_part)
        assert len(decoded) > 0

    async def test_resolve_and_convert_local_file(self) -> None:
        """Test URI resolution workflow with local files."""
        file_path = ImageTestCases.IMAGE_FILE_PATH_PNG_1

        # Verify resolution
        resolved = resolve_uri(file_path)
        assert resolved.kind == UriKind.LOCAL_PATH
        assert isinstance(resolved, ResolvedLocalPath)
        assert resolved.path == file_path

        # Verify conversion
        result = await make_base64_url_from_any_uri(file_path)

        assert result.startswith("data:image/png;base64,")
        base64_part = result.split(",", 1)[1]
        decoded = base64.b64decode(base64_part)
        assert decoded[:8] == b"\x89PNG\r\n\x1a\n"

    async def test_data_url_passthrough_workflow(self) -> None:
        """Test that data URLs pass through the entire workflow unchanged."""
        original_data_url = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

        # Verify resolution
        resolved = resolve_uri(original_data_url)
        assert resolved.kind == UriKind.BASE64_DATA_URL
        assert resolved.original == original_data_url

        # Verify passthrough
        result = await make_base64_url_from_any_uri(original_data_url)
        assert result == original_data_url

    async def test_gcp_public_url_returns_png(self) -> None:
        """Test that GCP public URL returns a valid PNG image."""
        url = TestURLs.GCP_PUBLIC

        result = await make_base64_url_from_any_uri(url)

        assert result.startswith("data:image/png;base64,")
        base64_part = result.split(",", 1)[1]
        decoded = base64.b64decode(base64_part)
        # PNG magic bytes
        assert decoded[:8] == b"\x89PNG\r\n\x1a\n"

    async def test_aws_cloudfront_url_returns_jpeg(self) -> None:
        """Test that AWS CloudFront URL returns a valid JPEG image."""
        url = TestURLs.AWS_CLOUDFRONT

        result = await make_base64_url_from_any_uri(url)

        assert result.startswith("data:image/jpeg;base64,")
        base64_part = result.split(",", 1)[1]
        decoded = base64.b64decode(base64_part)
        # JPEG magic bytes
        assert decoded[:2] == b"\xff\xd8"
