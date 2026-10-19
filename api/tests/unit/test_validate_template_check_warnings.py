from fastapi import FastAPI
from fastapi.testclient import TestClient
from pipelex.base_exceptions import ValidationErrorCategory, ValidationErrorItem
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.validation_error_types import TemplateCheckErrorType
from pytest_mock import MockerFixture

from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.routes import router as api_router
from tests.unit._constants import VALID_MTHDS

_TEMPLATE_WARNING = ValidationErrorItem(
    category=ValidationErrorCategory.DRY_RUN,
    error_type=TemplateCheckErrorType.TEMPLATE_CHECK_WARNING,
    pipe_code="print_invoice",
    domain_code="invoicing",
    template_file="invoice.xlsx",
    template_location="the defined name Totl",
    message="PipeDocGen 'print_invoice', template file 'invoice.xlsx': The name Totl matches no field (the defined name Totl)",
)


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(app)


class TestValidateTemplateCheckWarnings:
    def test_a_template_check_warning_rides_the_valid_verdict(self, mocker: MockerFixture) -> None:
        """The dry-run family of the advisory composition reaches the 200 valid arm with its locators, and never flips it.

        Only the family's output is stubbed: the real validation runs, through the same composition point, and pipelex's
        own suite proves a stub engine's warning reaches that family through `validate_bundles_in_process`, which the
        route's direct path calls (`test_pipe_doc_gen_template_warnings.py`).
        """
        family = mocker.patch("pipelex.pipeline.advisory_warnings.build_dry_run_warnings", return_value=[_TEMPLATE_WARNING])

        response = _build_client().post("/v1/validate", json={"mthds_contents": [VALID_MTHDS], "render": ["markdown"]})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is True
        family.assert_called_once()
        # The warning rides as a problem item under its code, with the facts its sentence is rendered from.
        template_warnings = [warning for warning in body["warnings"] if warning["code"] == PipelexErrorCode.DOCGEN_TEMPLATE_WARNING]
        assert len(template_warnings) == 1
        assert template_warnings[0] == {
            "code": PipelexErrorCode.DOCGEN_TEMPLATE_WARNING,
            "detail": f"The document template 'invoice.xlsx' may be faulty: {_TEMPLATE_WARNING.message}",
            "params": {"template": "invoice.xlsx", "finding": _TEMPLATE_WARNING.message},
            "location": {"pipe": "print_invoice"},
        }
        assert f"- **{TemplateCheckErrorType.TEMPLATE_CHECK_WARNING}** — {_TEMPLATE_WARNING.message}" in body["rendered_markdown"]
