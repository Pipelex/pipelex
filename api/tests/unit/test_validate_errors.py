"""`/validate` 200-diagnostic verdict + structured error envelope + per-file `source` threading.

`/validate` is a **diagnostic endpoint**: a produced verdict — valid or invalid — always rides a
**200**, discriminated in the body on `is_valid`. An invalid bundle answers a 200 `InvalidReport`
carrying a structured `validation_errors[]` list (the per-error diagnostics the VS Code extension
maps to per-line problems), built by pipelex's one shared builder; the structural artifacts
(`bundle_blueprint`, `pipe_io_contracts`, `graph_spec`, `validated_pipes`) are absent on the invalid
arm. Non-2xx is reserved for *no-verdict* conditions: a malformed body or an
`mthds_sources`/`mthds_contents` length mismatch is a request-shape **422**; a server fault that
is not a produced verdict (a host-wiring `PipelexError` / `PipelexUnexpectedError`) is a **5xx**.

When the caller sends `mthds_sources` parallel to `mthds_contents`, each name is threaded onto
`blueprint.source`, so pipe/concept and blueprint errors name the owning file on BOTH the invalid
arm (`validation_errors[].source`) and the valid arm (`bundle_blueprint.source`).

Asserts the in-process wire response via `TestClient`; the conformance HTTP arm asserts the same
200-diagnostic contract on the REAL wire (the spec's `<!-- unverified -->` markers point there).
"""

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pipelex.base_exceptions import PipelexConfigError, ValidationErrorCategory
from pipelex.core.exceptions import (
    DryRunFailureErrorData,
    PipeFactoryErrorData,
    PipelexBundleBlueprintValidationErrorData,
    PipesAndConceptValidationErrorData,
)
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.validation_error_types import PipeFactoryErrorType, PipeValidationErrorType
from pytest_mock import MockerFixture

from api.exception_handlers import register_exception_handlers
from api.routes import router as api_router
from api.routes.pipelex.pipeline import ApiRunner
from tests.unit._constants import INVALID_MAIN_PIPE_MTHDS, UNKNOWN_MODEL_MTHDS, VALID_MTHDS

# Structural artifacts that exist only on the valid arm — the invalid arm must NOT carry them.
_STRUCTURAL_FIELDS = ("bundle_blueprint", "pipe_io_contracts", "graph_spec", "validated_pipes")


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(app)


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
        items: list[dict[str, Any]] = body["validation_errors"]
        assert isinstance(items, list)
        assert items, body
        assert all(item["category"] in set(ValidationErrorCategory) and "message" in item for item in items)

    def test_validation_errors_carry_threaded_source(self):
        client = _build_client()
        response = client.post(
            "/v1/validate",
            json={"mthds_contents": [INVALID_MAIN_PIPE_MTHDS], "mthds_sources": ["broken.mthds"]},
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is False
        items: list[dict[str, Any]] = body["validation_errors"]
        # Pins that the dict-seeded blueprint-validation item carries the threaded name (not some
        # coincidental other item): a regression that stopped seeding `source` would fail here.
        sourced = [item for item in items if item.get("source") == "broken.mthds"]
        assert sourced, f"no validation_errors item carried the threaded source: {items}"
        assert any(item["category"] == ValidationErrorCategory.BLUEPRINT_VALIDATION for item in sourced)

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
        items: list[dict[str, Any]] = body["validation_errors"]
        sourced = [item for item in items if item.get("source") == "broken.mthds"]
        assert sourced, f"no validation_errors item carried the threaded source: {items}"
        assert any(item["category"] == ValidationErrorCategory.BLUEPRINT_VALIDATION for item in sourced)
        assert any("TOML syntax error" in item["message"] for item in sourced)

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
        items: list[dict[str, Any]] = body["validation_errors"]
        assert len(items) == 1, items
        item = items[0]
        assert item["category"] == ValidationErrorCategory.PIPE_VALIDATION
        assert item["error_type"] == "unknown_model"
        assert item["pipe_code"] == "echo"
        assert item["source"] == "echo.mthds"
        assert item["field_path"] == "pipe.echo.model"
        assert item["model_reference"] == "no-such-model-in-any-deck"
        assert item["model_type"] == "llm"

    def test_all_categories_project_onto_invalid_report(self, mocker: MockerFixture):
        # Every structured category lands on the 200 InvalidReport, and collectively the items cover
        # the full ValidationErrorItem field set (so a dropped field would fail here, not silently
        # vanish at the verdict->wire boundary). The runner returns the invalid verdict as a value
        # (an ErrorReport) — here the ValidateBundleError's own `to_error_report()` projection.
        mocker.patch.object(ApiRunner, "validate_verdict", new=mocker.AsyncMock(return_value=_multi_category_error().to_error_report()))
        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [VALID_MTHDS]})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is False
        assert body["is_runnable"] is False
        items: list[dict[str, Any]] = body["validation_errors"]
        categories = {item["category"] for item in items}
        assert categories == {
            ValidationErrorCategory.BLUEPRINT_VALIDATION,
            ValidationErrorCategory.PIPE_FACTORY,
            ValidationErrorCategory.PIPE_VALIDATION,
        }
        # The union of populated fields across the items covers every ValidationErrorItem field.
        populated = {key for item in items for key, value in item.items() if value is not None}
        assert populated.issuperset(
            {
                "category",
                "message",
                "error_type",
                "pipe_code",
                "concept_code",
                "domain_code",
                "source",
                "field_path",
                "field_name",
                "variable_names",
                "missing_concept_code",
                "declared_concepts",
            }
        ), f"missing fields: {populated}"

    def test_dry_run_failures_become_one_located_item_per_failing_pipe(self, mocker: MockerFixture):
        # A failing dry run is one `dry_run` item per failing pipe, located at the innermost pipe
        # that failed (its `pipe_code`, `domain_code` and `source`), never one item holding the whole
        # sweep. A failure the sweep could not locate still becomes its own item carrying only the
        # message — the structured-info invariant (never a bare detail with an empty list) — and so
        # carries no locator.
        failing_dry_run = ValidateBundleError(
            message="Dry run failed.",
            dry_run_failures=[
                DryRunFailureErrorData(pipe_code="summarize", domain_code="legal", source="pipe.mthds", message="Pipe 'summarize' failed: boom."),
                DryRunFailureErrorData(message="Dry run failed: unlocated."),
            ],
        )
        mocker.patch.object(ApiRunner, "validate_verdict", new=mocker.AsyncMock(return_value=failing_dry_run.to_error_report()))
        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [VALID_MTHDS]})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is False
        items: list[dict[str, Any]] = body["validation_errors"]
        assert len(items) == 2, items
        assert all(item["category"] == ValidationErrorCategory.DRY_RUN for item in items)
        assert all(item["error_type"] == "DryRunError" for item in items)
        located_item, unlocated_item = items
        assert located_item["pipe_code"] == "summarize"
        assert located_item["domain_code"] == "legal"
        assert located_item["source"] == "pipe.mthds"
        assert located_item["message"] == "Pipe 'summarize' failed: boom."
        assert unlocated_item["message"] == "Dry run failed: unlocated."
        for locator in ("pipe_code", "domain_code", "source"):
            assert locator not in unlocated_item, unlocated_item

    def test_non_verdict_failure_is_not_a_200_verdict(self, mocker: MockerFixture):
        # The runner returns a produced verdict (valid report | invalid ErrorReport) as a value; only
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
        # its file exactly as it would a failure's `validation_errors[].source`.
        assert body["bundle_blueprint"]["source"] == "api://smoke.mthds"

    def test_length_mismatch_is_a_request_error(self):
        client = _build_client()
        response = client.post(
            "/v1/validate",
            json={"mthds_contents": [VALID_MTHDS], "mthds_sources": ["a.mthds", "b.mthds"]},
        )

        # Caught at request validation as a 422 — never reaches the runtime (which would 500 on the
        # mismatch). The validator message rides the problem `detail`. This is a no-verdict
        # request-shape condition, NOT a content verdict.
        assert response.status_code == 422, response.text
        assert response.headers["content-type"].startswith("application/problem+json")
        assert "mthds_sources" in response.text
