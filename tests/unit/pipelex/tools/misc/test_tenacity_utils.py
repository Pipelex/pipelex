from collections.abc import Callable

import pytest
from pytest_mock import MockerFixture
from tenacity import Retrying, retry_base, retry_if_exception_type, retry_if_result, stop_after_attempt, wait_fixed

from pipelex.tools.misc import tenacity_utils
from pipelex.tools.misc.tenacity_utils import log_retry

WAIT_SECONDS = 1.5


def _fail_once_with_value_error() -> Callable[[], str | None]:
    calls: list[int] = []

    def attempt() -> str | None:
        calls.append(1)
        if len(calls) == 1:
            msg = "first attempt fails"
            raise ValueError(msg)
        return "done"

    return attempt


def _return_none_once() -> Callable[[], str | None]:
    calls: list[int] = []

    def attempt() -> str | None:
        calls.append(1)
        if len(calls) == 1:
            return None
        return "done"

    return attempt


class TestLogRetry:
    @pytest.mark.parametrize(
        ("topic", "make_attempt", "retry_condition", "expected_exception_type"),
        [
            ("retry on an exception", _fail_once_with_value_error, retry_if_exception_type(ValueError), "ValueError"),
            ("retry on a result", _return_none_once, retry_if_result(lambda result: result is None), None),
        ],
    )
    def test_a_retry_is_logged_at_debug_with_its_values_as_fields(
        self,
        mocker: MockerFixture,
        topic: str,
        make_attempt: Callable[[], Callable[[], str | None]],
        retry_condition: retry_base,
        expected_exception_type: str | None,
    ) -> None:
        """One fixed message per retry, the attempt, the exception's class and the wait carried as fields."""
        debug = mocker.patch.object(tenacity_utils.log, "debug")
        retrying = Retrying(
            retry=retry_condition,
            wait=wait_fixed(WAIT_SECONDS),
            stop=stop_after_attempt(2),
            before_sleep=log_retry,
            sleep=lambda _seconds: None,
            reraise=True,
        )

        assert retrying(make_attempt()) == "done", topic
        debug.assert_called_once_with(
            "Retrying after a failed attempt",
            fields={"attempt_number": 1, "exception_type": expected_exception_type, "wait_seconds": WAIT_SECONDS},
        )
