from pytest_mock import MockerFixture

from pipelex import log


class TestLogDispatchIncludeException:
    def test_include_exception_appends_traceback_to_console_message(self, mocker: MockerFixture) -> None:
        # Regression guard: `include_exception=True` must append the traceback to the string actually sent
        # to the console. The bug appended it to a dead local while the console was fed the pre-append
        # string, so server-side errors (e.g. the API's `log.error(..., include_exception=True)`) logged
        # only their summary line and never the underlying cause.
        to_console = mocker.patch.object(log.log_dispatch, "_log_to_console")

        cause = "boom-cause"
        try:
            raise ValueError(cause)
        except ValueError:
            log.error("something failed", include_exception=True)

        to_console.assert_called_once()
        call = to_console.call_args
        assert call is not None
        logged_message = call.kwargs["message"]
        assert "something failed" in logged_message
        assert "Traceback (most recent call last)" in logged_message
        assert "ValueError: boom-cause" in logged_message

    def test_no_traceback_when_include_exception_false(self, mocker: MockerFixture) -> None:
        to_console = mocker.patch.object(log.log_dispatch, "_log_to_console")

        cause = "boom-cause"
        try:
            raise ValueError(cause)
        except ValueError:
            log.error("something failed", include_exception=False)

        to_console.assert_called_once()
        call = to_console.call_args
        assert call is not None
        logged_message = call.kwargs["message"]
        assert "something failed" in logged_message
        assert "Traceback" not in logged_message
