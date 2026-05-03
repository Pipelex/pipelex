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
