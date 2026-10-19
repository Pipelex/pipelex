"""Unit tests for the problem document of an API-authored error.

A `PipelexError` answers its own problem (`PipelexError.to_problem`), rendered by
`pipelex_api.exception_handlers.problem_response` and pinned in `test_exception_handlers.py` and
`test_problem_views.py`; this module covers only the document the API builds for its own 4xx and
5xx, which no `PipelexError` stands behind.
"""

from pipelex.base_exceptions import ErrorDomain

from pipelex_api.error_types import ErrorType
from pipelex_api.problem_document import build_problem_document_from_api_error, with_request_context


class TestProblemDocument:
    def test_api_error_variant_is_input_domain(self):
        doc = build_problem_document_from_api_error(
            ErrorType.VALIDATION_ERROR,
            "field 'pipe_code' is required",
            422,
            instance="/v1/execute",
            request_id="REQ9",
        )
        assert doc == {
            "type": "https://docs.pipelex.com/latest/errors/validation-error/",
            "title": "Validation error",
            "status": 422,
            "detail": "field 'pipe_code' is required",
            "instance": "/v1/execute",
            "request_id": "REQ9",
            "error_type": "ValidationError",
            "error_domain": "input",
            # Every API-authored error is non-retryable: a caller mistake is not fixed by a blind
            # retry. Carried as a uniform contract member so clients drive retry logic without
            # branching on field presence.
            "retryable": False,
        }

    def test_api_error_variant_config_domain_for_server_fault(self):
        # An API-owned 5xx (a missing secret, an unconfigured backend) classifies
        # CONFIG, not INPUT — an operator, not the caller, fixes it.
        doc = build_problem_document_from_api_error(
            ErrorType.SERVER_MISCONFIGURED,
            "Server configuration error: API_KEY not configured",
            500,
            instance="/v1/upload",
            request_id="REQ-CFG",
            error_domain=ErrorDomain.CONFIG,
        )
        assert doc["status"] == 500
        assert doc["title"] == "Server misconfigured"
        assert doc["error_type"] == "ServerMisconfigured"
        assert doc["error_domain"] == "config"
        # An API-owned 5xx is no more retryable than a 4xx — the operator, not
        # the caller, fixes a missing secret; a blind retry does nothing.
        assert doc["retryable"] is False

    def test_none_valued_fields_dropped(self):
        api_doc = build_problem_document_from_api_error(ErrorType.BAD_REQUEST, "bad request", 400, instance=None, request_id=None)
        assert None not in api_doc.values()
        assert "instance" not in api_doc
        assert "request_id" not in api_doc
        # `retryable` is a contract member, not a drop-on-None one — present
        # even when `instance`/`request_id` are absent.
        assert api_doc["retryable"] is False

    def test_request_context_is_stamped_on_a_copy(self):
        """The handler stamps the request's members on a copy, so the raised `ApiError` reads exactly as it was raised."""
        raised = build_problem_document_from_api_error(ErrorType.BAD_REQUEST, "bad request", 400, instance=None, request_id=None)
        before = dict(raised)

        stamped = with_request_context(raised, instance="/v1/start", request_id="REQ-STAMP")

        assert stamped == {**before, "instance": "/v1/start", "request_id": "REQ-STAMP"}
        assert raised == before

    def test_request_context_drops_none(self):
        raised = build_problem_document_from_api_error(ErrorType.BAD_REQUEST, "bad request", 400, instance=None, request_id=None)

        stamped = with_request_context(raised, instance=None, request_id=None)

        assert stamped == raised
        assert None not in stamped.values()
