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

from api.error_types import ErrorType
from api.errors import raise_validation_error
from api.exception_handlers import API_ERROR_EVENT, register_exception_handlers
from api.middleware import REQUEST_ID_HEADER, RequestIdMiddleware

_SHIPPED_PIPELEX_CONFIG = Path(__file__).parents[2] / ".pipelex" / "pipelex.toml"

_router = APIRouter()


@_router.get("/pipelex-failure")
async def pipelex_failure_route() -> None:
    # An operator-actionable 500 — the `error`-level branch, with a traceback on the record.
    msg = "the gateway config is missing"
    raise PipelexConfigError(msg)


@_router.get("/caller-mistake")
async def caller_mistake_route(detail: str) -> None:
    # A caller-input 422 whose `detail` is exactly what the caller sent — the `warning`-level
    # branch, and the one field on the record that a caller controls.
    raise_validation_error(detail, ErrorType.VALIDATION_ERROR)


def _build_client() -> TestClient:
    """Wire a throwaway app with the production handlers and the request-id middleware."""
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(_router)
    return TestClient(RequestIdMiddleware(app))


def _api_error_record(caplog: pytest.LogCaptureFixture) -> logging.LogRecord:
    """The one `api_error` record the request emitted."""
    records = [record for record in caplog.records if getattr(record, "event", None) == API_ERROR_EVENT]
    assert len(records) == 1, f"expected exactly one api_error record, got {len(records)}"
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

    def test_request_id_and_route_ride_the_error_record(self, caplog: pytest.LogCaptureFixture):
        # The two identifiers an operator starts from. `request_id` arrives from the log context
        # the middleware bound for the request; `route` from the field set the handler ships.
        # Neither is interpolated into the message, which is the whole point of the change.
        with caplog.at_level(logging.WARNING):
            response = _build_client().get("/pipelex-failure")
        assert response.status_code == 500
        record = _api_error_record(caplog)
        assert record.levelno == logging.ERROR
        assert getattr(record, "request_id", None) == response.headers[REQUEST_ID_HEADER]
        assert getattr(record, "route", None) == "/pipelex-failure"
        assert getattr(record, "error_type", None) == "PipelexConfigError"
        assert record.getMessage() == "API error 500: PipelexConfigError"

    def test_a_caller_mistake_records_a_warning_carrying_the_same_identifiers(self, caplog: pytest.LogCaptureFixture):
        # A 4xx is a caller mistake, so it lands at `warning` — but it carries the same two
        # identifiers, so one query over `event` returns the whole error stream of a request.
        with caplog.at_level(logging.WARNING):
            response = _build_client().get("/caller-mistake", params={"detail": "the input is malformed"})
        assert response.status_code == 422
        record = _api_error_record(caplog)
        assert record.levelno == logging.WARNING
        assert getattr(record, "request_id", None) == response.headers[REQUEST_ID_HEADER]
        assert getattr(record, "route", None) == "/caller-mistake"
        assert getattr(record, "status", None) == 422

    def test_the_json_sink_writes_one_object_per_line_with_the_fields_flat(self, caplog: pytest.LogCaptureFixture):
        # The shape the runner's configured sink puts on stderr: the sink's own keys, then every
        # field and the bound context identifiers flat beside them, one JSON object on one line.
        with caplog.at_level(logging.WARNING):
            response = _build_client().get("/pipelex-failure")
        payload = _rendered_json(_api_error_record(caplog))
        assert payload["severity"] == "ERROR"
        assert payload["message"] == "API error 500: PipelexConfigError"
        assert payload["event"] == API_ERROR_EVENT
        assert payload["request_id"] == response.headers[REQUEST_ID_HEADER]
        assert payload["route"] == "/pipelex-failure"
        assert payload["status"] == 500
        assert payload["error_type"] == "PipelexConfigError"
        assert payload["error_domain"] == "config"
        # `retryable` is absent rather than false: pipelex populates it only on a classifiable
        # failure, and a field with no value is dropped rather than written as a null a query
        # filtering on presence would read as an answer.
        assert "retryable" not in payload
        # `time` and `logger` come from the sink itself; an operator-actionable failure carries
        # its traceback under `exception` rather than spilling it across the line.
        assert payload["time"].endswith("Z")
        assert "PipelexConfigError" in payload["exception"]

    @pytest.mark.parametrize(
        ("crafted_detail", "logged_detail"),
        [
            # Back when the API flattened its own fields into a `key=value` run, each of these
            # forged either a sibling field or a whole second line. The API renders nothing now:
            # the runtime escapes a control character in a field's value and the sink escapes what
            # it writes, so each must survive as one field's value.
            ("legit\nstatus=200 event=auth_success", "legit\\nstatus=200 event=auth_success"),
            ("hijack status=200 event=fake", "hijack status=200 event=fake"),
            ("legit\rstatus=200", "legit\\rstatus=200"),
            ('has " a quote = inside', 'has " a quote = inside'),
        ],
    )
    def test_a_crafted_detail_survives_as_one_value_and_forges_nothing(
        self, caplog: pytest.LogCaptureFixture, crafted_detail: str, logged_detail: str
    ):
        # The escaping the API used to do itself is the runtime's job now, in two layers. The
        # redaction processor every sink sits behind turns a control character in a field's value
        # into its printable escape, so a newline the caller sent reads `\n` in `detail`; then
        # `json.dumps` writes each value inside one string, so a quote or an `=` stays part of it.
        # Either way the line stays one object and the value comes back as one field.
        with caplog.at_level(logging.WARNING):
            response = _build_client().get("/caller-mistake", params={"detail": crafted_detail})
        assert response.status_code == 422
        payload = _rendered_json(_api_error_record(caplog))
        assert payload["detail"] == logged_detail
        assert payload["event"] == API_ERROR_EVENT, "a crafted detail forged or overwrote a field"
        assert payload["status"] == 422, "a crafted detail forged or overwrote a field"
        assert crafted_detail not in payload["message"], "caller input reached the message"

    def test_a_credential_echoed_into_a_detail_is_redacted_on_the_line(self, caplog: pytest.LogCaptureFixture):
        # A validation message can echo what the caller sent, header text included. The runtime's
        # redaction processor scrubs the credential out of the field before the sink writes it, and
        # keeps the scheme, so the line still says which kind of credential went.
        with caplog.at_level(logging.WARNING):
            response = _build_client().get("/caller-mistake", params={"detail": "rejected Authorization: Bearer placeholder-not-a-token"})
        assert response.status_code == 422
        payload = _rendered_json(_api_error_record(caplog))
        assert payload["detail"] == "rejected Authorization: Bearer [REDACTED]"
