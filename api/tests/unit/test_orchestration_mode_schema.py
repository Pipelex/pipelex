"""The `orchestration_mode` per-request override is documented on every run surface that honors it.

`/execute` and `/start` both thread a per-request `orchestration_mode` override into the same
override policy (`PipelineApiExtras.orchestration_mode` -> `resolve_orchestration_mode`), so the
committed OpenAPI artifact must advertise the field on BOTH — otherwise a client generated from the
artifact can drive the override on `/execute` but not on `/start`, even though the runtime honors it.
Their bodies are published via inline `openapi_extra` schemas (raw-`Request` parsing, so FastAPI
cannot infer the body), so this asserts the generated `app.openapi()` request-body schema directly.
"""

import pytest
from fastapi import FastAPI

from api.routes import router as api_router


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    return app


class TestOrchestrationModeSchema:
    @pytest.mark.parametrize("path", ["/v1/execute", "/v1/start"])
    def test_request_body_documents_orchestration_mode(self, path: str) -> None:
        schema = _build_app().openapi()
        request_schema = schema["paths"][path]["post"]["requestBody"]["content"]["application/json"]["schema"]
        properties = request_schema["properties"]
        assert "orchestration_mode" in properties, f"{path} request schema must document orchestration_mode"
        assert properties["orchestration_mode"]["description"], f"{path} orchestration_mode must carry a description"
