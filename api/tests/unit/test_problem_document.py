"""Unit tests for the rendering of a problem as the HTTP response that carries it.

Every failure the runner answers is a problem built in the operator's view; `pipelex_api.problem_document` renders it as
the response a reader receives. The handlers that build the problems are pinned in `test_exception_handlers.py` and
`test_problem_views.py`; this module covers the rendering alone: the status, the view, the headers, and a body with no
member written as `null`.
"""

import json

from mthds.protocol.problem.registry import CoreCode
from pipelex.errors.problem import ProblemView, make_problem

from pipelex_api.exceptions import RunnerAuthError, RunnerMisconfiguredError, RunnerRequestError
from pipelex_api.problem_document import PROBLEM_JSON_MEDIA_TYPE, problem_json_response, problem_status


def _body_of(response_body: bytes | memoryview) -> dict[str, object]:
    body: dict[str, object] = json.loads(bytes(response_body))
    return body


class TestProblemDocument:
    def test_a_runner_refusal_answers_its_code_with_no_instance_and_no_null(self):
        problem = RunnerRequestError("the field is refused", field="pipe_code").to_problem(view=ProblemView.OPERATOR, request_id="REQ9")

        response = problem_json_response(problem, view=ProblemView.CALLER)

        assert response.status_code == 422
        assert response.media_type == PROBLEM_JSON_MEDIA_TYPE
        body = _body_of(response.body)
        assert body["code"] == "request.invalid"
        assert body["status"] == 422
        assert body["domain"] == "input"
        assert body["retry"] == "no"
        assert body["params"] == {"field": "pipe_code"}
        assert body["location"] == {"field": "pipe_code"}
        assert body["request_id"] == "REQ9"
        assert body["type"] == "https://mthds.ai/errors/request.invalid"
        assert "instance" not in body
        assert "error_type" not in body
        assert None not in body.values()

    def test_the_caller_view_leaves_the_diagnostics_out_and_the_operator_view_keeps_them(self):
        # The operator's message rides the diagnostics alone: the caller reads the code's sentence.
        problem = RunnerMisconfiguredError("API_KEY is not set", component="API_KEY").to_problem(view=ProblemView.OPERATOR)

        caller_body = _body_of(problem_json_response(problem, view=ProblemView.CALLER).body)
        operator_body = _body_of(problem_json_response(problem, view=ProblemView.OPERATOR).body)

        assert caller_body["code"] == "runtime.misconfigured"
        assert caller_body["status"] == 500
        assert "diagnostics" not in caller_body
        assert "API_KEY is not set" not in json.dumps(caller_body)
        diagnostics = operator_body["diagnostics"]
        assert isinstance(diagnostics, dict)
        assert diagnostics["error_class"] == "RunnerMisconfiguredError"
        assert "API_KEY is not set" in json.dumps(operator_body)

    def test_a_401_carries_the_challenge_its_raise_site_names_and_no_other(self):
        """The challenge names the credential the deployment reads, which only the refusal knows: none behind a proxy."""
        problem = RunnerAuthError("no credential").with_error_code(CoreCode.AUTH_MISSING_CREDENTIAL).to_problem(view=ProblemView.OPERATOR)

        bare = problem_json_response(problem, view=ProblemView.CALLER)
        challenged = problem_json_response(problem, view=ProblemView.CALLER, headers={"WWW-Authenticate": "Bearer"})

        assert bare.status_code == 401
        assert "WWW-Authenticate" not in bare.headers
        assert challenged.headers["WWW-Authenticate"] == "Bearer"
        assert _body_of(challenged.body)["code"] == "auth.missing_credential"

    def test_further_headers_are_added_to_the_response(self):
        problem = RunnerRequestError("method not allowed").with_error_code(CoreCode.REQUEST_METHOD_NOT_ALLOWED).to_problem(view=ProblemView.OPERATOR)

        response = problem_json_response(problem, view=ProblemView.CALLER, headers={"Allow": "GET"})

        assert response.status_code == 405
        assert response.headers["Allow"] == "GET"
        assert "Retry-After" not in response.headers

    def test_the_status_is_the_one_the_code_declares(self):
        assert problem_status(make_problem(code=CoreCode.REQUEST_TOO_LARGE, view=ProblemView.CALLER, params={"limit": 10, "size": 11})) == 413
        assert (
            problem_status(make_problem(code=CoreCode.RUNTIME_UNSUPPORTED, view=ProblemView.CALLER, params={"capability": "fire_and_forget"})) == 501
        )
