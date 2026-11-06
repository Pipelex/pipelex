from fastapi import FastAPI
from fastapi.testclient import TestClient

from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.routes import router as api_router
from tests.unit._constants import DATE_FIELD_NAMED_DATE_MTHDS, FIELD_NAMED_LIKE_ITS_CLASS_MTHDS


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(app, raise_server_exceptions=False)


class TestValidateShadowingFieldNames:
    def test_a_field_named_date_typed_date_is_a_valid_verdict(self):
        """The bundle that once got an internal error from `/validate` is a 200 valid verdict."""
        response = _build_client().post("/v1/validate", json={"mthds_contents": [DATE_FIELD_NAMED_DATE_MTHDS]})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is True, body
        assert body["default_pipe_ref"] == "repro_date_field.read_day"

    def test_a_field_named_like_the_class_it_holds_is_an_invalid_verdict_naming_the_concept_and_the_field(self):
        """The one field name a structure class cannot take is a 200 invalid verdict, never a 500."""
        response = _build_client().post("/v1/validate", json={"mthds_contents": [FIELD_NAMED_LIKE_ITS_CLASS_MTHDS]})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is False
        finding = (
            "its field 'shadowing_refs__Person' has the name of the Python class of the concept 'shadowing_refs.Person', "
            "which the structure refers to"
        )
        assert body["errors"] == [
            {
                "code": "method.concept_invalid",
                "detail": f"The structure of the concept 'shadowing_refs.Visit' cannot be built ({finding}).",
                "params": {"concept": "shadowing_refs.Visit", "finding": finding},
            }
        ]
