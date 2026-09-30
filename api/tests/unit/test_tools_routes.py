from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.exception_handlers import register_exception_handlers
from api.limits import MAX_MTHDS_FILE_BYTES
from api.openapi_schema import PipelexFastAPI
from api.problem_document import PROBLEM_JSON_MEDIA_TYPE
from api.routes import router as api_router
from tests.unit._constants import VALID_MTHDS

SCHEMA_INVALID_MTHDS = """\
domain = "broken"
main_pipe = "echo"

[pipe.echo]
type = "Nope"
description = "Bad"
"""


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(app)


def _build_app() -> FastAPI:
    # `PipelexFastAPI`, not a bare `FastAPI`: the problem+json media type on error responses is
    # asserted by the app class's `openapi()` override (see `api.openapi_schema`), so a schema
    # built off a stock app would not be the one this server publishes.
    app = PipelexFastAPI()
    app.include_router(api_router, prefix="/v1")
    return app


class TestLintRoute:
    def test_valid_content_returns_no_diagnostics(self):
        response = _build_client().post("/v1/lint", json={"content": VALID_MTHDS})

        assert response.status_code == 200, response.text
        assert response.json() == {"diagnostics": []}

    def test_syntax_error_returns_200_with_diagnostic(self):
        response = _build_client().post("/v1/lint", json={"content": "key = "})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["diagnostics"]
        assert body["diagnostics"][0]["kind"] == "syntax"
        assert body["diagnostics"][0]["range"]["start_line"] == 1

    def test_schema_error_returns_200_with_diagnostic(self):
        response = _build_client().post("/v1/lint", json={"content": SCHEMA_INVALID_MTHDS, "source": "broken.mthds"})

        assert response.status_code == 200, response.text
        diagnostics = response.json()["diagnostics"]
        assert diagnostics
        assert any(diagnostic["kind"] == "schema" for diagnostic in diagnostics)

    def test_oversized_content_returns_rfc7807_422(self):
        response = _build_client().post("/v1/lint", json={"content": "a" * (MAX_MTHDS_FILE_BYTES + 1)})

        assert response.status_code == 422, response.text
        assert response.headers["content-type"] == PROBLEM_JSON_MEDIA_TYPE
        body = response.json()
        assert body["error_type"] == "ValidationError"
        assert "MTHDS file exceeds" in body["detail"]


class TestFormatRoute:
    def test_unformatted_valid_content_returns_changed_output(self):
        response = _build_client().post("/v1/format", json={"content": "a=1"})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body == {"formatted": "a = 1\n", "changed": True, "diagnostics": []}

    def test_already_formatted_content_returns_unchanged_output(self):
        response = _build_client().post("/v1/format", json={"content": "a = 1\n"})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["formatted"] == "a = 1\n"
        assert body["changed"] is False
        assert body["diagnostics"] == []

    def test_syntax_error_returns_200_with_unchanged_content_and_diagnostic(self):
        response = _build_client().post("/v1/format", json={"content": "key = "})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["formatted"] == "key = "
        assert body["changed"] is False
        assert body["diagnostics"]
        assert body["diagnostics"][0]["kind"] == "syntax"

    def test_malformed_options_return_rfc7807_422(self):
        response = _build_client().post("/v1/format", json={"content": "a = 1\n", "options": {"column_width": "wide"}})

        assert response.status_code == 422, response.text
        assert response.headers["content-type"] == PROBLEM_JSON_MEDIA_TYPE
        body = response.json()
        assert body["error_type"] == "ValidationError"
        assert "column_width" in body["detail"]


class TestToolsRouteSchema:
    def test_tools_routes_are_served_under_v1(self):
        schema = _build_app().openapi()

        assert "/v1/lint" in schema["paths"]
        assert "/v1/format" in schema["paths"]

    def test_tools_routes_are_not_mthds_protocol_tagged(self):
        schema = _build_app().openapi()

        assert "x-mthds-protocol" not in schema["paths"]["/v1/lint"]["post"]
        assert "x-mthds-protocol" not in schema["paths"]["/v1/format"]["post"]

    def test_tools_routes_advertise_problem_json_422(self):
        schema = _build_app().openapi()

        for path in ("/v1/lint", "/v1/format"):
            error_content = schema["paths"][path]["post"]["responses"]["422"]["content"]
            assert set(error_content) == {PROBLEM_JSON_MEDIA_TYPE}
