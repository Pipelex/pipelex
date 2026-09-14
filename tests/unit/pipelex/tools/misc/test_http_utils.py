import pytest
from pytest_mock import MockerFixture

from pipelex.tools.misc.http_utils import validate_url_resource_exists


class TestValidateUrlResourceExists:
    """The pre-check never touches the network: remote URLs pass through, local paths must exist."""

    @pytest.mark.parametrize(
        "url",
        [
            pytest.param("https://example.com/file.png", id="https"),
            pytest.param("http://example.com/file.png", id="http"),
            pytest.param("https://this-domain-cannot-exist.invalid/file.pdf", id="unresolvable-host"),
        ],
    )
    def test_remote_url_is_not_probed(self, mocker: MockerFixture, url: str) -> None:
        """No HTTP request is made for a remote URL, whatever the host."""
        mock_head = mocker.patch("httpx.head")
        mock_get = mocker.patch("httpx.get")
        mock_stream = mocker.patch("httpx.stream")

        validate_url_resource_exists(url)

        mock_head.assert_not_called()
        mock_get.assert_not_called()
        mock_stream.assert_not_called()

    @pytest.mark.parametrize(
        "url",
        [
            pytest.param("data:image/png;base64,abc123", id="data-url"),
            pytest.param("pipelex-storage://bucket/file.pdf", id="pipelex-storage"),
        ],
    )
    def test_internal_uri_is_skipped(self, url: str) -> None:
        validate_url_resource_exists(url)

    def test_existing_local_path_passes(self) -> None:
        validate_url_resource_exists("pyproject.toml")

    def test_missing_local_path_raises(self) -> None:
        with pytest.raises(ValueError, match="does not exist"):
            validate_url_resource_exists("/nonexistent/path/to/file.png")
