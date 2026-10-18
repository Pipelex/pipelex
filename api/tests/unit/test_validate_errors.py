"""`/validate` 200-diagnostic verdict + structured error envelope + per-file `source` threading.

`/validate` is a **diagnostic endpoint**: a produced verdict — valid or invalid — always rides a
**200**, discriminated in the body on `is_valid`. An invalid bundle answers a 200 `InvalidReport`
carrying `errors[]`, one problem item per finding (the per-error diagnostics the VS Code extension
maps to per-line problems), each with its registry code, the parameters its sentence is rendered
from, and its location, built by pipelex's one shared builder; the structural artifacts
(`bundle_blueprint`, `pipe_io_contracts`, `graph_spec`, `validated_pipes`) are absent on the invalid
arm. Non-2xx is reserved for *no-verdict* conditions: a malformed body or an
`mthds_sources`/`mthds_contents` length mismatch is a request-shape **422**; a server fault that
is not a produced verdict (a host-wiring `PipelexError` / `PipelexUnexpectedError`) is a **5xx**.

When the caller sends `mthds_sources` parallel to `mthds_contents`, each name is threaded onto
`blueprint.source`, so pipe/concept and blueprint errors name the owning file on BOTH the invalid
arm (`errors[].location.file`) and the valid arm (`bundle_blueprint.source`).

Asserts the in-process wire response via `TestClient`; the conformance HTTP arm asserts the same
200-diagnostic contract on the REAL wire (the spec's `<!-- unverified -->` markers point there).
"""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mthds.protocol.problem.registry import CoreCode
from pipelex.base_exceptions import PipelexConfigError
from pipelex.core.exceptions import (
    DryRunFailureErrorData,
    PipeFactoryErrorData,
    PipelexBundleBlueprintValidationErrorData,
    PipesAndConceptValidationErrorData,
)
from pipelex.errors.bundle_validation_failure import BundleValidationFailure
from pipelex.errors.problem import ProblemView
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.validation_error_types import PipeFactoryErrorType, PipeValidationErrorType
from pytest_mock import MockerFixture

from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.routes import router as api_router
from pipelex_api.routes.pipelex.pipeline import ApiRunner
from tests.unit._constants import INVALID_MAIN_PIPE_MTHDS, UNKNOWN_MODEL_MTHDS, VALID_MTHDS
from tests.unit._problems import assert_problem

# Structural artifacts that exist only on the valid arm — the invalid arm must NOT carry them.
_STRUCTURAL_FIELDS = ("bundle_blueprint", "pipe_io_contracts", "graph_spec", "validated_pipes")


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(app)


def _failure_of(refusal: ValidateBundleError) -> BundleValidationFailure:
    """The invalid verdict a validator returns as a value for a refusal: its operator problem and its validation items."""
    return BundleValidationFailure(problem=refusal.to_problem(view=ProblemView.OPERATOR), validation_errors=refusal.validation_error_items())


def _multi_category_error() -> ValidateBundleError:
    """A `ValidateBundleError` carrying one item per structured category, fields fully populated.

    The shared builder projects these onto `validation_errors[]`; collectively the three items
    exercise every field of `ValidationErrorItem` (the blueprint item carries `variable_names`,
    the factory item `missing_concept_code` / `declared_concepts`, the pipe item
    `field_path` / `field_name`). Mocked rather than provoked from a crafted bundle so the
    envelope projection is asserted independently of which bundle happens to trip which category.
    """
    return ValidateBundleError(
        message="Bundle has multiple validation problems.",
        pipelex_bundle_blueprint_validation_errors=[
            PipelexBundleBlueprintValidationErrorData(
                error_type=PipeValidationErrorType.MISSING_INPUT_VARIABLE,
                domain_code="legal",
                source="blueprint.mthds",
                pipe_code="summarize",
                concept_code="Contract",
                message="Blueprint validation failed.",
                variable_names=["contract"],
            )
        ],
        pipe_factory_errors=[
            PipeFactoryErrorData(
                error_type=PipeFactoryErrorType.UNKNOWN_CONCEPT,
                domain_code="legal",
                pipe_code="summarize",
                missing_concept_code="Summari",
                declared_concepts=["Contract", "Summary"],
                message="Pipe references an unknown concept.",
            )
        ],
        pipe_validation_errors=[
            PipesAndConceptValidationErrorData(
                error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT,
                domain_code="legal",
                source="pipe.mthds",
                pipe_code="summarize",
                concept_code="Summary",
                field_name="output",
                field_path="pipe.summarize.output",
                message="Output concept is inadequate.",
                params={"declared": "Summary", "expected": ["Contract"], "pipe_type": "PipeLLM"},
            )
        ],
    )


class TestValidateErrors:
    def test_invalid_bundle_returns_200_invalid_report(self):
        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [INVALID_MAIN_PIPE_MTHDS]})

        # A produced "invalid" verdict is a 200 InvalidReport, not a transport failure (422).
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("application/json")
        body = response.json()
        assert body["is_valid"] is False
        assert body["is_runnable"] is False
        # The discriminated invalid arm carries diagnostics, not the valid arm's structural artifacts.
        for field in _STRUCTURAL_FIELDS:
            assert field not in body, f"invalid arm leaked structural field {field!r}: {body}"
        # The retired wire extra is gone — the verdict is `is_valid`, never `success`.
        assert "success" not in body
        items: list[dict[str, Any]] = body["errors"]
        assert isinstance(items, list)
        assert items, body
        assert all(item["code"] and item["detail"] for item in items)
        # An item writes no member as null.
        assert all(None not in item.values() for item in items)

    def test_validation_errors_carry_threaded_source(self):
        client = _build_client()
        response = client.post(
            "/v1/validate",
            json={"mthds_contents": [INVALID_MAIN_PIPE_MTHDS], "mthds_sources": ["broken.mthds"]},
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is False
        items: list[dict[str, Any]] = body["errors"]
        # Pins that the dict-seeded blueprint-validation item carries the threaded name (not some
        # coincidental other item): a regression that stopped seeding `source` would fail here.
        sourced = [item for item in items if item.get("location", {}).get("file") == "broken.mthds"]
        assert sourced, f"no errors item carried the threaded source: {items}"
        assert any(item["code"] == "method.identifier_invalid" for item in sourced)

    def test_toml_syntax_errors_carry_threaded_source(self):
        client = _build_client()
        response = client.post(
            "/v1/validate",
            json={
                "mthds_contents": ['domain = "broken" trailing'],
                "mthds_sources": ["broken.mthds"],
            },
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is False
        items: list[dict[str, Any]] = body["errors"]
        sourced = [item for item in items if item.get("location", {}).get("file") == "broken.mthds"]
        assert sourced, f"no errors item carried the threaded source: {items}"
        (item,) = sourced
        assert item["code"] == "method.syntax"
        assert item["location"] == {"file": "broken.mthds", "line": 1, "column": 19}
        assert item["params"]["finding"].startswith("TOML syntax error")

    def test_unknown_model_is_a_located_item_of_the_invalid_verdict(self):
        # A model the deck does not define is refused while the pipe is built. That refusal is an
        # item of the verdict like any other, located on the pipe's `model` field and carrying the
        # reference as written, not a no-verdict fault.
        client = _build_client()
        response = client.post(
            "/v1/validate",
            json={"mthds_contents": [UNKNOWN_MODEL_MTHDS], "mthds_sources": ["echo.mthds"]},
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is False
        items: list[dict[str, Any]] = body["errors"]
        assert len(items) == 1, items
        item = items[0]
        assert item["code"] == "model.unknown"
        assert item["params"] == {"model": "no-such-model-in-any-deck", "model_type": "llm", "suggestions": []}
        assert item["location"] == {"pipe": "echo", "field": "model", "file": "echo.mthds"}
        assert item["detail"] == "The method names the llm model 'no-such-model-in-any-deck', which no catalog knows."

    def test_all_categories_project_onto_invalid_report(self, mocker: MockerFixture):
        # Every structured category lands on the 200 InvalidReport as a problem item under its own code, and
        # collectively the items carry every member of a problem item and every locator (so a dropped one would fail
        # here, not silently vanish at the verdict->wire boundary). The runner returns the invalid verdict as a value
        # (a BundleValidationFailure) — here the one a validator builds from the ValidateBundleError.
        mocker.patch.object(ApiRunner, "validate_verdict", new=mocker.AsyncMock(return_value=_failure_of(_multi_category_error())))
        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [VALID_MTHDS]})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is False
        assert body["is_runnable"] is False
        items: list[dict[str, Any]] = body["errors"]
        assert [item["code"] for item in items] == [
            "method.input_undeclared",
            "method.concept_unresolved",
            "method.output_concept_mismatch",
        ]
        # The union of members across the items covers every member of a problem item and every locator.
        assert {key for item in items for key in item} == {"code", "detail", "params", "location"}
        assert {key for item in items for key in item.get("location", {})} == {"pipe", "field", "file"}
        undeclared, unresolved, mismatched = items
        assert undeclared["params"] == {"pipe": "summarize", "variables": ["contract"]}
        # The concepts the domain declares nearest the one that resolves to nothing are offered in its place.
        assert unresolved["params"] == {"concept": "Summari", "suggestions": ["Summary"]}
        # The facts the raise site gave ride the item beside those its locators give.
        assert mismatched["params"] == {"pipe": "summarize", "declared": "Summary", "expected": ["Contract"], "pipe_type": "PipeLLM"}

    @pytest.mark.builds_problems_without_required_params(reason="a dry-run failure the sweep could not locate names no pipe")
    def test_dry_run_failures_become_one_located_item_per_failing_pipe(self, mocker: MockerFixture):
        # A failing dry run is one `dry_run` item per failing pipe, located at the innermost pipe
        # that failed (its `pipe_code`, `domain_code` and `source`), never one item holding the whole
        # sweep. A failure the sweep could not locate still becomes its own item carrying only the
        # message — the structured-info invariant (never a bare detail with an empty list) — and so
        # carries no locator.
        failing_dry_run = ValidateBundleError(
            message="Dry run failed.",
            dry_run_failures=[
                DryRunFailureErrorData(
                    code=CoreCode.METHOD_WIRING_INVALID,
                    pipe_code="summarize",
                    domain_code="legal",
                    source="pipe.mthds",
                    message="Pipe 'summarize' failed: boom.",
                    params={"variable_path": "contract.title"},
                ),
                DryRunFailureErrorData(
                    code=CoreCode.METHOD_WIRING_INVALID, message="Dry run failed: unlocated.", params={"variable_path": "contract"}
                ),
            ],
        )
        mocker.patch.object(ApiRunner, "validate_verdict", new=mocker.AsyncMock(return_value=_failure_of(failing_dry_run)))
        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [VALID_MTHDS]})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is False
        items: list[dict[str, Any]] = body["errors"]
        assert len(items) == 2, items
        # Each item carries the code the dry-run failure was raised under.
        assert all(item["code"] == CoreCode.METHOD_WIRING_INVALID for item in items)
        located_item, unlocated_item = items
        assert located_item["location"] == {"pipe": "summarize", "file": "pipe.mthds"}
        assert located_item["params"]["finding"] == "Pipe 'summarize' failed: boom."
        assert unlocated_item["params"] == {"finding": "Dry run failed: unlocated.", "variable_path": "contract"}
        assert "location" not in unlocated_item, unlocated_item

    def test_non_verdict_failure_is_not_a_200_verdict(self, mocker: MockerFixture):
        # The runner returns a produced verdict (valid report | BundleValidationFailure) as a value; only
        # a no-verdict fault propagates. A genuine host-wiring/server fault must reach the global
        # problem+json handler as a 5xx, never be masqueraded as a 200 verdict. (Route invariant: the
        # route maps the returned verdict and lets a raised fault propagate.)
        mocker.patch.object(ApiRunner, "validate_verdict", new=mocker.AsyncMock(side_effect=PipelexConfigError("host wiring fault")))
        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [VALID_MTHDS]})

        assert response.status_code >= 500, response.text
        assert response.headers["content-type"].startswith("application/problem+json")
        # Not a verdict body: the discriminated-union arms always carry `is_valid`; a no-verdict
        # problem document does not.
        assert "is_valid" not in response.json()

    def test_valid_bundle_threads_source_onto_blueprint(self):
        client = _build_client()
        response = client.post(
            "/v1/validate",
            json={"mthds_contents": [VALID_MTHDS], "mthds_sources": ["api://smoke.mthds"]},
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is True
        # Valid arm threads the same name, so a client can correlate the report's primary blueprint to
        # its file exactly as it would a failure's `errors[].location.file`.
        assert body["bundle_blueprint"]["source"] == "api://smoke.mthds"

    def test_length_mismatch_is_a_request_error(self):
        client = _build_client()
        response = client.post(
            "/v1/validate",
            json={"mthds_contents": [VALID_MTHDS], "mthds_sources": ["a.mthds", "b.mthds"]},
        )

        # Caught at request validation as a 422 — never reaches the runtime (which would 500 on the
        # mismatch). The model's own rule names the field to correct, and its message rides the operator's
        # diagnostics alone. This is a no-verdict request-shape condition, NOT a content verdict.
        assert_problem(response, status=422, code="request.invalid", field="mthds_sources")
