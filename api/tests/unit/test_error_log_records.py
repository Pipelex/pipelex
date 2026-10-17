"""What an error record actually carries, and what it looks like once the `json` sink has written it.

The tests in `test_exception_handlers.py` read the `fields=` mapping the handlers hand the runtime,
with the runtime's `log` replaced by a spy. These ones let the real thing run end to end: a request
goes through `RequestIdMiddleware`, the handler emits, `caplog` catches the record the runtime built,
and the runner's configured sink formatter renders it. That is the whole path this server's operator
output takes in production, minus the process stream it is written to.
"""

import json
import logging
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from pipelex.base_exceptions import PipelexConfigError
from pipelex.system.console_target import ConsoleTarget
from pipelex.tools.log.json_log_sink import JsonLogFormatter
from pipelex.tools.log.log_sink import LogSinkMethod
from pipelex.tools.misc.pretty import PrettyPrintMode
from pipelex.tools.misc.toml_utils import load_toml_from_path

from pipelex_api.exception_handlers import ERROR_CHAIN_FIELD, ERROR_FRAMES_FIELD, register_exception_handlers
from pipelex_api.exceptions import RunnerRequestError
from pipelex_api.middleware import REQUEST_ID_HEADER, RequestIdMiddleware

_SHIPPED_PIPELEX_CONFIG = Path(__file__).parents[2] / ".pipelex" / "pipelex.toml"

_router = APIRouter()


@_router.get("/pipelex-failure")
async def pipelex_failure_route() -> None:
    # An operator-actionable 500 — the `error`-level branch, with the frames of its chain on the record.
    msg = "the gateway config is missing"
    raise PipelexConfigError(msg)


# The text of a foreign exception a run's data can reach, such as a pydantic error quoting an input or a method
# function's own failure: it must reach no record.
_RUN_DATA_TEXT = "the patient's record reads: Jane Doe, born 1970-01-01"


def _fail_on_run_data() -> None:
    """A method function failing with a message quoting the run's data."""
    raise ValueError(_RUN_DATA_TEXT)


@_router.get("/chained-failure")
async def chained_failure_route() -> None:
    # A Pipelex 500 raised from a foreign exception whose text quotes a run's data, and raised while handling another.
    try:
        _fail_on_run_data()
    except ValueError as exc:
        msg = f"the step failed: {exc}"
        raise PipelexConfigError(msg) from exc


@_router.get("/implicitly-chained-failure")
async def implicitly_chained_failure_route() -> None:
    # A bug of ours raised while handling a foreign failure: the chain is implicit, and the catch-all answers it.
    try:
        _fail_on_run_data()
    except ValueError:
        raise KeyError(_RUN_DATA_TEXT)  # noqa: B904


# The text of an exception that is not a Pipelex error, which may name anything on the host: the operator's alone.
_FOREIGN_FAILURE_TEXT = "the cache index at /srv/pipelex/private/index.db is corrupt"


@_router.get("/foreign-failure")
async def foreign_failure_route() -> None:
    # A bug of ours, raised by no Pipelex error: the catch-all handler answers it as `runtime.unexpected`.
    raise RuntimeError(_FOREIGN_FAILURE_TEXT)


@_router.get("/caller-mistake/{token:path}")
async def caller_mistake_route(token: str) -> None:
    # A caller-input 422 — the `warning`-level branch. Its path is exactly what the caller sent, and it rides the record
    # as `url.path`, percent-decoded: the one field on the record that a caller controls.
    msg = f"the token {token!r} is refused"
    raise RunnerRequestError(msg, field="token")


def _build_client(*, raise_server_exceptions: bool = True) -> TestClient:
    """Wire a throwaway app with the production handlers and the request-id middleware.

    `raise_server_exceptions` must be `False` for a route whose exception reaches the catch-all handler, which
    Starlette's `ServerErrorMiddleware` runs and then re-raises.
    """
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(_router)
    return TestClient(RequestIdMiddleware(app), raise_server_exceptions=raise_server_exceptions)


# The message every error line carries, whichever handler produced it: the key the error stream is selected by.
_ERROR_MESSAGE = "A request ended in an error response"


def _api_error_record(caplog: pytest.LogCaptureFixture) -> logging.LogRecord:
    """The one error record the request emitted."""
    records = [record for record in caplog.records if record.getMessage() == _ERROR_MESSAGE]
    assert len(records) == 1, f"expected exactly one error record, got {len(records)}"
    return records[0]


def _rendered_json(record: logging.LogRecord) -> dict[str, Any]:
    """The record as the `json` sink writes it: one line, parsed back."""
    line = JsonLogFormatter().format(record)
    assert "\n" not in line, f"the sink wrote more than one line: {line!r}"
    assert "\r" not in line, f"the sink wrote a carriage return: {line!r}"
    payload = json.loads(line)
    assert isinstance(payload, dict)
    return cast("dict[str, Any]", payload)


class TestErrorLogRecords:
    def test_the_runner_ships_a_configuration_that_selects_the_json_sink(self):
        # Reads the shipped file rather than `get_config()`, deliberately. The runtime layers
        # `_local`, `_{environment}` and `_override` files over a base, so the merged config is
        # partly this machine's: a developer who sets `sink = "console"` locally for a readable
        # `make run` would red this test while CI, which has no such file, stayed green. What the
        # image boots on is this file, because nothing mounts an override into it.
        #
        # The json sink writes to stderr so stdout stays the data channel, and the pretty-print
        # mode is silent because a server has no terminal and must not render on the request
        # thread. Neither is a claim that Rich is absent: `typer` and `instructor` require it
        # unconditionally, so it is installed and reachable — these keys are what keeps it unused.
        log_section = load_toml_from_path(_SHIPPED_PIPELEX_CONFIG)["runtime"]["log"]
        assert log_section["sink"] == LogSinkMethod.JSON
        assert log_section["console_log_target"] == ConsoleTarget.STDERR
        assert log_section["pretty_print_mode"] == PrettyPrintMode.SILENT

    def test_request_id_and_url_path_ride_the_error_record(self, caplog: pytest.LogCaptureFixture):
        # The two identifiers an operator starts from. `request_id` arrives from the log context
        # the middleware bound for the request; `url.path` from the field set the handler ships.
        # Neither is interpolated into the message, which is the whole point of the change.
        with caplog.at_level(logging.WARNING):
            response = _build_client().get("/pipelex-failure")
        assert response.status_code == 500
        record = _api_error_record(caplog)
        assert record.levelno == logging.ERROR
        assert getattr(record, "request_id", None) == response.headers[REQUEST_ID_HEADER]
        assert getattr(record, "url.path", None) == "/pipelex-failure"
        assert getattr(record, "error.type", None) == "PipelexConfigError"
        assert getattr(record, ERROR_CHAIN_FIELD, None) == ["PipelexConfigError"]

    def test_an_unexpected_failure_keeps_its_class_and_where_it_was_raised_for_the_operator(self, caplog: pytest.LogCaptureFixture):
        # The catch-all answers the caller the code's sentences, and the operator's record keeps what escaped: its class
        # as `error.type`, and the frames it was raised through, never its text, which the operator view's diagnostics
        # carry for whoever reads it.
        with caplog.at_level(logging.WARNING):
            response = _build_client(raise_server_exceptions=False).get("/foreign-failure")
        assert response.status_code == 500
        assert response.json()["code"] == "runtime.unexpected"
        assert _FOREIGN_FAILURE_TEXT not in response.text
        assert "RuntimeError" not in response.text
        record = _api_error_record(caplog)
        assert record.levelno == logging.ERROR
        assert getattr(record, "error.code", None) == "runtime.unexpected"
        assert getattr(record, "error.type", None) == "RuntimeError"
        assert record.exc_info is None
        payload = _rendered_json(record)
        assert "exception" not in payload
        assert payload[ERROR_CHAIN_FIELD] == ["RuntimeError"]
        assert any(frame.endswith(" in foreign_failure_route") for frame in payload[ERROR_FRAMES_FIELD]), payload
        assert _FOREIGN_FAILURE_TEXT not in json.dumps(payload)

    @pytest.mark.parametrize(
        ("route", "chain", "deepest_frame"),
        [
            pytest.param("/chained-failure", ["PipelexConfigError", "ValueError"], "_fail_on_run_data", id="explicit-cause"),
            pytest.param("/implicitly-chained-failure", ["KeyError", "ValueError"], "_fail_on_run_data", id="implicit-context"),
        ],
    )
    def test_a_chained_foreign_exception_text_reaches_no_record(
        self, caplog: pytest.LogCaptureFixture, route: str, chain: list[str], deepest_frame: str
    ):
        # A traceback prints the text of every exception of its chain, and a foreign exception's text can quote a run's
        # inputs or a model's answer. The handler's record names the chain by class and the deepest exception's frames
        # instead, so the run's data reaches no record, not even one the handler emits at `error`.
        with caplog.at_level(logging.DEBUG):
            response = _build_client(raise_server_exceptions=False).get(route)
        assert response.status_code == 500
        assert _RUN_DATA_TEXT not in response.text
        record = _api_error_record(caplog)
        assert record.levelno == logging.ERROR
        assert record.exc_info is None
        payload = _rendered_json(record)
        assert payload[ERROR_CHAIN_FIELD] == chain
        assert payload[ERROR_FRAMES_FIELD][-1].endswith(f" in {deepest_frame}"), payload
        handler_records = [record for record in caplog.records if record.name.startswith("pipelex_api")]
        assert handler_records
        for handler_record in handler_records:
            assert _RUN_DATA_TEXT not in JsonLogFormatter().format(handler_record)

    def test_a_caller_mistake_records_a_warning_carrying_the_same_identifiers(self, caplog: pytest.LogCaptureFixture):
        # A 4xx is a caller mistake, so it lands at `warning` — but it carries the same message and
        # the same two identifiers, so one query over the message returns the whole error stream of a request.
        with caplog.at_level(logging.WARNING):
            response = _build_client().get("/caller-mistake/malformed")
        assert response.status_code == 422
        record = _api_error_record(caplog)
        assert record.levelno == logging.WARNING
        assert getattr(record, "request_id", None) == response.headers[REQUEST_ID_HEADER]
        assert getattr(record, "url.path", None) == "/caller-mistake/malformed"
        assert getattr(record, "http.response.status_code", None) == 422
        assert getattr(record, "error.code", None) == "request.invalid"
        assert getattr(record, ERROR_CHAIN_FIELD, None) == ["RunnerRequestError"]
        assert getattr(record, ERROR_FRAMES_FIELD, None) is None

    def test_the_json_sink_writes_one_object_per_line_with_the_fields_flat(self, caplog: pytest.LogCaptureFixture):
        # The shape the runner's configured sink puts on stderr: the sink's own keys, then every
        # field and the bound context identifiers flat beside them, one JSON object on one line.
        with caplog.at_level(logging.WARNING):
            response = _build_client().get("/pipelex-failure")
        payload = _rendered_json(_api_error_record(caplog))
        assert payload["severity"] == "ERROR"
        assert payload["message"] == _ERROR_MESSAGE
        assert "event" not in payload
        assert payload["request_id"] == response.headers[REQUEST_ID_HEADER]
        assert payload["url.path"] == "/pipelex-failure"
        assert payload["http.response.status_code"] == 500
        assert payload["error.type"] == "PipelexConfigError"
        assert payload["error_domain"] == "config"
        # `retryable` is the verdict of the error's code, which every error carries, so it is always
        # written: `pipelex.config.invalid` is no fault a repeat can cure.
        assert payload["retryable"] is False
        # `time` and `logger` come from the sink itself. An operator-actionable failure carries its chain by class and
        # the frames it was raised through as fields, and no traceback, which would print its text.
        assert payload["time"].endswith("Z")
        assert "exception" not in payload
        assert payload[ERROR_CHAIN_FIELD] == ["PipelexConfigError"]
        assert any(frame.endswith(" in pipelex_failure_route") for frame in payload[ERROR_FRAMES_FIELD]), payload

    @pytest.mark.parametrize(
        ("crafted_segment", "logged_path"),
        [
            # Back when the API flattened its own fields into a `key=value` run, each of these
            # forged either a sibling field or a whole second line. The API renders nothing now: the
            # URL parser drops a control character from the path the record carries, and the sink
            # writes each value inside one string, so each must survive as one field's value.
            ("legit%0Astatus=200 event=auth_success", "/unserved/legitstatus=200 event=auth_success"),
            ("hijack status=200 event=fake", "/unserved/hijack status=200 event=fake"),
            ("legit%0Dstatus=200", "/unserved/legitstatus=200"),
            ('has " a quote = inside', '/unserved/has " a quote = inside'),
        ],
    )
    def test_a_crafted_path_survives_as_one_value_and_forges_nothing(self, caplog: pytest.LogCaptureFixture, crafted_segment: str, logged_path: str):
        # The path a caller sends is the one value of the record it controls whatever the route, a path no route serves
        # included. `json.dumps` writes each value inside one string, so a quote or an `=` stays part of it, and the
        # line stays one object with the value as one field.
        with caplog.at_level(logging.WARNING):
            response = _build_client().get(f"/unserved/{crafted_segment}")
        assert response.status_code == 404
        payload = _rendered_json(_api_error_record(caplog))
        assert payload["url.path"] == logged_path
        assert payload["error.code"] == "request.not_found"
        assert "event" not in payload, "a crafted path forged a field"
        assert payload["http.response.status_code"] == 404, "a crafted path forged or overwrote a field"
        assert payload["message"] == _ERROR_MESSAGE, "caller input reached the message"

    def test_a_credential_echoed_into_a_path_is_redacted_on_the_line(self, caplog: pytest.LogCaptureFixture):
        # A request line can carry what the caller sent, header text included. The runtime's
        # redaction processor scrubs the credential out of the field before the sink writes it, and
        # keeps the scheme, so the line still says which kind of credential went.
        with caplog.at_level(logging.WARNING):
            response = _build_client().get("/caller-mistake/rejected Authorization: Bearer placeholder-not-a-token")
        assert response.status_code == 422
        payload = _rendered_json(_api_error_record(caplog))
        assert payload["url.path"] == "/caller-mistake/rejected Authorization: Bearer [REDACTED]"
