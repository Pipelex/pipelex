import logging
from collections.abc import Callable
from typing import NoReturn

import httpx
import pytest
from pytest_mock import MockerFixture

from pipelex.tools.misc.http_utils import validate_url_resource_exists


def _make_status_error(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("HEAD", "https://example.test/resource")
    response = httpx.Response(status_code=status_code, request=request)
    return httpx.HTTPStatusError(message=f"HTTP {status_code}", request=request, response=response)


def _raise_status_error(status_code: int) -> Callable[..., NoReturn]:
    def _stub(*_args: object, **_kwargs: object) -> NoReturn:
        raise _make_status_error(status_code)

    return _stub


class TestValidateHttpUrl:
    """Tests for HTTP URL validation HEAD/GET fallback logic and warn-only contract."""

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

    @pytest.mark.parametrize("status_code", [401, 403, 429])
    def test_bot_block_status_codes_are_debug_only(
        self,
        status_code: int,
        mocker: MockerFixture,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """401/403/429 are typical bot-block codes and must NOT log at WARNING."""
        mocker.patch("pipelex.tools.misc.http_utils.httpx.head", side_effect=_raise_status_error(status_code))
        url = "https://example.test/resource"
        with caplog.at_level(logging.DEBUG, logger="pipelex"):
            validate_url_resource_exists(url)
        warning_records = [record for record in caplog.records if record.levelno >= logging.WARNING and url in record.message]
        assert not warning_records, f"Expected no WARNING-level log for status {status_code}, got: {[record.message for record in warning_records]}"

    @pytest.mark.parametrize("status_code", [404, 500, 503])
    def test_other_status_codes_emit_warning(
        self,
        status_code: int,
        mocker: MockerFixture,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """4xx (other than 401/403/429) and 5xx codes must surface as WARNING per the warn-only contract."""
        mocker.patch("pipelex.tools.misc.http_utils.httpx.head", side_effect=_raise_status_error(status_code))
        url = "https://example.test/resource"
        with caplog.at_level(logging.DEBUG, logger="pipelex"):
            validate_url_resource_exists(url)
        warning_records = [record for record in caplog.records if record.levelno == logging.WARNING and url in record.message]
        assert warning_records, f"Expected a WARNING-level log mentioning the URL for status {status_code}"
        assert str(status_code) in warning_records[0].message
