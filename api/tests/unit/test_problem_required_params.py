"""The runner's problems and items carry every parameter their code requires, and a single fault carries no list.

Each case sends a request the acceptance of the error contract found answered without a parameter its code's registry
entry requires, or with a one-item `errors` list restating the problem, and asserts that the document names what a
caller acts on: the parameters its sentence and its next step are rendered from, and its location. The autouse fixture
of `conftest.py` sweeps every other test of this suite for the same class of defect.
"""

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.routes import router as api_router
from tests.unit._constants import INVALID_MAIN_PIPE_MTHDS, UNKNOWN_MODEL_MTHDS
from tests.unit._problems import assert_problem
from tests.unit.test_data import RequiredParamsTestData as Data


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(app)


def _invalid_items(response_body: dict[str, Any], *, code: str) -> list[dict[str, Any]]:
    """The items of an invalid verdict under one code."""
    assert response_body["is_valid"] is False, response_body
    return [item for item in response_body["errors"] if item["code"] == code]


class TestProblemRequiredParams:
    def test_a_model_no_enabled_backend_serves_is_unavailable_on_execute(self):
        response = _build_client().post("/v1/execute", json={"files": {Data.BUNDLE_PATH: Data.UNSERVED_MODEL_MTHDS}, "inputs": {"text": "x"}})
        problem = assert_problem(response, status=501, code="model.unavailable")
        assert problem["params"] == {"model": Data.UNSERVED_MODEL, "model_type": "llm", "reason": "not_served"}
        assert problem["location"] == {"pipe": "echo", "field": "model", "file": Data.BUNDLE_PATH}
        assert "errors" not in problem, problem

    def test_a_model_no_enabled_backend_serves_is_unavailable_on_validate(self):
        # Not a verdict: the method is sound, and this deployment cannot run it.
        response = _build_client().post("/v1/validate", json={"files": {Data.BUNDLE_PATH: Data.UNSERVED_MODEL_MTHDS}})
        problem = assert_problem(response, status=501, code="model.unavailable")
        assert problem["params"] == {"model": Data.UNSERVED_MODEL, "model_type": "llm", "reason": "not_served"}
        assert problem["location"] == {"pipe": "echo", "field": "model", "file": Data.BUNDLE_PATH}

    def test_a_model_no_catalog_knows_offers_the_nearest_handles(self):
        response = _build_client().post("/v1/validate", json={"files": {Data.BUNDLE_PATH: Data.NEAR_MODEL_MTHDS}})
        assert response.status_code == 200, response.text
        (item,) = _invalid_items(response.json(), code="model.unknown")
        assert item["params"]["model"] == Data.NEAR_MODEL
        assert item["params"]["model_type"] == "llm"
        assert Data.NEAR_MODEL_SUGGESTION in item["params"]["suggestions"], item
        assert item["location"] == {"pipe": "echo", "field": "model", "file": Data.BUNDLE_PATH}

    def test_a_model_near_no_handle_offers_an_empty_list(self):
        response = _build_client().post("/v1/validate", json={"files": {Data.BUNDLE_PATH: UNKNOWN_MODEL_MTHDS}})
        (item,) = _invalid_items(response.json(), code="model.unknown")
        assert item["params"] == {"model": "no-such-model-in-any-deck", "model_type": "llm", "suggestions": []}

    def test_an_invalid_main_pipe_names_its_kind_and_the_name(self):
        response = _build_client().post("/v1/validate", json={"files": {Data.BUNDLE_PATH: INVALID_MAIN_PIPE_MTHDS}})
        assert response.status_code == 200, response.text
        (item,) = _invalid_items(response.json(), code="method.identifier_invalid")
        assert item["params"] == {"identifier_kind": "main_pipe", "name": "Not A Valid Pipe Code!"}
        assert item["location"]["file"] == Data.BUNDLE_PATH

    def test_a_selected_pipe_the_method_lacks_offers_the_nearest(self):
        body = {"files": {Data.BUNDLE_PATH: Data.ECHO_MTHDS}, "pipe_code": "ecoh", "inputs": {"text": "x"}}
        response = _build_client().post("/v1/execute", json=body)
        problem = assert_problem(response, status=422, code="request.pipe_not_found")
        assert problem["params"] == {"pipe": "ecoh", "suggestions": ["smoke.echo"]}
        assert "errors" not in problem, problem

    def test_an_unresolved_concept_offers_the_nearest_declared(self):
        response = _build_client().post("/v1/validate", json={"files": {Data.BUNDLE_PATH: Data.UNKNOWN_CONCEPT_MTHDS}})
        assert response.status_code == 200, response.text
        items = _invalid_items(response.json(), code="method.concept_unresolved")
        assert items, response.text
        assert items[0]["params"]["concept"].endswith("Thingg"), items
        assert items[0]["params"]["suggestions"] == ["Thing"], items

    def test_models_check_answers_one_refusal_without_a_list(self):
        response = _build_client().get("/v1/models/check")
        problem = assert_problem(response, status=422, code="request.invalid", field="reference")
        assert "errors" not in problem, problem

    def test_a_template_the_sandbox_refuses_names_what_it_reached_for(self):
        response = _build_client().post("/v1/validate", json={"files": {Data.BUNDLE_PATH: Data.TEMPLATE_REFUSED_MTHDS}})
        problem = assert_problem(response, status=422, code="security.template_refused")
        assert problem["params"] == {"pipe": "say", "name": "_owner"}
        assert problem["detail"] == "A template of pipe 'say' reached for '_owner', which the template sandbox forbids."
        assert problem["location"]["pipe"] == "say"
        assert "errors" not in problem, problem

    def test_a_native_concept_redeclared_names_the_concept_and_the_conflict(self):
        response = _build_client().post("/v1/validate", json={"files": {Data.BUNDLE_PATH: Data.NATIVE_REDECLARATION_MTHDS}})
        assert response.status_code == 200, response.text
        (item,) = _invalid_items(response.json(), code="method.name_conflict")
        assert item["params"] == {"name": "Rating", "conflict": "native_concept"}
        assert item["location"]["file"] == Data.BUNDLE_PATH

    def test_a_concept_two_bundles_declare_names_both_bundles(self):
        response = _build_client().post("/v1/validate", json={"files": Data.DUPLICATE_BUNDLES})
        assert response.status_code == 200, response.text
        items = _invalid_items(response.json(), code="method.name_conflict")
        assert sorted(item["location"]["file"] for item in items) == sorted(Data.DUPLICATE_BUNDLES), items
        for item in items:
            assert item["params"] == {"name": "dup.Doc", "conflict": "duplicate_declaration"}, item

    def test_a_dependency_keyed_by_its_repository_address_names_the_address_to_key_it_by(self):
        body = {"files": {Data.BUNDLE_PATH: Data.CALLER_MTHDS}, "dependencies": {Data.DEPENDENCY_REPOSITORY_ADDRESS: Data.DEPENDENCY_TREE}}
        response = _build_client().post("/v1/validate", json=body)
        problem = assert_problem(response, status=422, code="pipelex.request.dependency_key_mismatch")
        assert problem["params"] == {"key": Data.DEPENDENCY_REPOSITORY_ADDRESS, "address": Data.DEPENDENCY_ADDRESS}
        assert problem["location"] == {"field": "dependencies"}
