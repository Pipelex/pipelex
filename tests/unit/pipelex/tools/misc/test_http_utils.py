import pytest
from pytest_mock import MockerFixture

from pipelex.tools.misc.http_utils import get_user_agent, validate_http_url_syntax, validate_url_resource_exists


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

    @pytest.mark.parametrize(
        "url",
        [
            pytest.param("https://example.com/file.pdf", id="https"),
            pytest.param("http://localhost:8000/file.pdf", id="localhost-with-port"),
            pytest.param("https://example.com/a%20b.pdf?x=1#frag", id="encoded-query-fragment"),
        ],
    )
    def test_well_formed_http_url_syntax_passes(self, url: str) -> None:
        validate_http_url_syntax(url=url)

    @pytest.mark.parametrize(
        "url",
        [
            pytest.param("https://", id="no-host"),
            pytest.param("https://exa mple.com/file.pdf", id="space-in-host"),
            pytest.param("ftp://example.com/file.pdf", id="wrong-scheme"),
            pytest.param("not a url", id="plain-text"),
        ],
    )
    def test_malformed_http_url_syntax_raises(self, url: str) -> None:
        with pytest.raises(ValueError, match="not a valid http\\(s\\) URL"):
            validate_http_url_syntax(url=url)

    def test_user_agent_is_product_and_version_only(self) -> None:
        """No URL in parentheses: that crawler signature is what bot walls stall on."""
        user_agent = get_user_agent()
        assert user_agent.startswith("Pipelex/")
        assert "(" not in user_agent
        assert "http" not in user_agent
