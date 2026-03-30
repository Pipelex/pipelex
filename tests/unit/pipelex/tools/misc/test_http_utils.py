import httpx
import pytest
from pytest_mock import MockerFixture

from pipelex.tools.misc.http_utils import validate_url_resource_exists


class TestValidateHttpUrl:
    """Tests for HTTP URL validation HEAD/GET fallback logic."""

    def test_head_success_does_not_fall_back_to_get(self, mocker: MockerFixture) -> None:
        """When HEAD returns 200, no GET request is made."""
        mock_head_response = mocker.MagicMock()
        mock_head_response.status_code = 200
        mock_head_response.raise_for_status = mocker.MagicMock()
        mocker.patch("pipelex.tools.misc.http_utils.httpx.head", return_value=mock_head_response)
        mock_stream = mocker.patch("pipelex.tools.misc.http_utils.httpx.stream")

        validate_url_resource_exists("https://example.com/file.png")

        mock_head_response.raise_for_status.assert_called_once()
        mock_stream.assert_not_called()

    @pytest.mark.parametrize(
        "status_code",
        [
            pytest.param(403, id="forbidden"),
            pytest.param(405, id="method-not-allowed"),
        ],
    )
    def test_head_rejection_falls_back_to_get(self, mocker: MockerFixture, status_code: int) -> None:
        """When HEAD returns a rejection code (403, 405), a streaming GET is attempted."""
        mock_head_response = mocker.MagicMock()
        mock_head_response.status_code = status_code

        mocker.patch("pipelex.tools.misc.http_utils.httpx.head", return_value=mock_head_response)

        mock_get_response = mocker.MagicMock()
        mock_get_response.raise_for_status = mocker.MagicMock()
        mock_get_response.__enter__ = mocker.MagicMock(return_value=mock_get_response)
        mock_get_response.__exit__ = mocker.MagicMock(return_value=False)
        mocker.patch("pipelex.tools.misc.http_utils.httpx.stream", return_value=mock_get_response)

        validate_url_resource_exists("https://example.com/file.png")

        mock_get_response.raise_for_status.assert_called_once()

    @pytest.mark.parametrize(
        "status_code",
        [
            pytest.param(401, id="unauthorized"),
            pytest.param(404, id="not-found"),
        ],
    )
    def test_head_non_rejection_4xx_does_not_fall_back(self, mocker: MockerFixture, status_code: int) -> None:
        """When HEAD returns 401 or 404, it raises immediately without trying GET."""
        mock_head_response = mocker.MagicMock()
        mock_head_response.status_code = status_code
        mock_head_response.raise_for_status = mocker.MagicMock(
            side_effect=httpx.HTTPStatusError(
                "Client Error",
                request=mocker.MagicMock(),
                response=mocker.MagicMock(status_code=status_code),
            )
        )
        mocker.patch("pipelex.tools.misc.http_utils.httpx.head", return_value=mock_head_response)
        mock_stream = mocker.patch("pipelex.tools.misc.http_utils.httpx.stream")

        with pytest.raises(ValueError, match=f"returned HTTP {status_code}"):
            validate_url_resource_exists("https://example.com/file.png")

        mock_stream.assert_not_called()

    def test_head_5xx_does_not_fall_back_to_get(self, mocker: MockerFixture) -> None:
        """When HEAD returns 5xx, it raises immediately without trying GET."""
        mock_head_response = mocker.MagicMock()
        mock_head_response.status_code = 500
        mock_head_response.raise_for_status = mocker.MagicMock(
            side_effect=httpx.HTTPStatusError(
                "Server Error",
                request=mocker.MagicMock(),
                response=mocker.MagicMock(status_code=500),
            )
        )
        mocker.patch("pipelex.tools.misc.http_utils.httpx.head", return_value=mock_head_response)
        mock_stream = mocker.patch("pipelex.tools.misc.http_utils.httpx.stream")

        with pytest.raises(ValueError, match="returned HTTP 500"):
            validate_url_resource_exists("https://example.com/file.png")

        mock_stream.assert_not_called()

    def test_head_rejection_and_get_fails_raises_valueerror(self, mocker: MockerFixture) -> None:
        """When HEAD returns 403 and GET also fails, a ValueError is raised."""
        mock_head_response = mocker.MagicMock()
        mock_head_response.status_code = 403

        mocker.patch("pipelex.tools.misc.http_utils.httpx.head", return_value=mock_head_response)

        mock_get_response = mocker.MagicMock()
        mock_get_response.raise_for_status = mocker.MagicMock(
            side_effect=httpx.HTTPStatusError(
                "Forbidden",
                request=mocker.MagicMock(),
                response=mocker.MagicMock(status_code=403),
            )
        )
        mock_get_response.__enter__ = mocker.MagicMock(return_value=mock_get_response)
        mock_get_response.__exit__ = mocker.MagicMock(return_value=False)
        mocker.patch("pipelex.tools.misc.http_utils.httpx.stream", return_value=mock_get_response)

        with pytest.raises(ValueError, match="returned HTTP 403"):
            validate_url_resource_exists("https://example.com/file.png")
