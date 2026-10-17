"""Assertions on the problem documents the runner answers, shared by the route tests.

Every failure the runner answers is an `application/problem+json` document carrying a registry `code`, the status its
code declares, repeated in the body, and no member written as `null`. These helpers assert that shape once, so a test
states only what is particular to its refusal: the code, and the parameters or the field it names.
"""

import json
from collections.abc import Mapping
from typing import Any, Protocol

from pipelex.base_exceptions import PipelexError
from pipelex.errors.problem import ProblemView

from pipelex_api.problem_document import problem_json_response

PROBLEM_JSON = "application/problem+json"


class ClientResponse(Protocol):
    """What these helpers read of a test client's response, whichever HTTP client package the test client is built on."""

    @property
    def status_code(self) -> int: ...

    @property
    def headers(self) -> Mapping[str, str]: ...

    @property
    def text(self) -> str: ...

    def json(self) -> Any: ...


def assert_problem(response: ClientResponse, *, status: int, code: str, field: str | None = None) -> dict[str, Any]:
    """Assert that a response is the problem document of `code` at `status`, and return its body.

    Args:
        response: The response a test client received.
        status: The HTTP status the code declares.
        code: The registry code the problem must carry.
        field: The request field the problem's `field` parameter must name, when the code has one.

    Returns:
        The problem document.
    """
    assert response.status_code == status, response.text
    assert response.headers["content-type"] == PROBLEM_JSON, response.headers
    body: dict[str, Any] = response.json()
    assert body["code"] == code, body
    assert body["status"] == status, body
    assert "instance" not in body, body
    assert "error_type" not in body, body
    assert None not in body.values(), body
    if field is not None:
        assert body["params"]["field"] == field, body
    return body


def problem_of(error: PipelexError, *, view: ProblemView = ProblemView.OPERATOR) -> dict[str, Any]:
    """The problem document a raised error is answered with, in `view`, as the global handler renders it, its status included."""
    response = problem_json_response(error.to_problem(view=ProblemView.OPERATOR), view=view)
    body: dict[str, Any] = json.loads(bytes(response.body))
    assert body["status"] == response.status_code, body
    return body


def problem_items_fields(body: dict[str, Any]) -> list[str]:
    """The `field` parameter of each of a problem's items, in order: the fields a request refusal names one by one."""
    return [item["params"]["field"] for item in body.get("errors", [])]
