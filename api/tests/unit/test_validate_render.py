"""`/validate` opt-in `rendered_markdown` extra (D-D) — a Pipelex-API presentation layer.

The neutral 200 verdict body is unchanged by default; when the request's `render` includes the
supported `markdown` token, the response gains a `rendered_markdown` field on BOTH 200 arms (valid
and invalid). An unknown/unsupported token is silently ignored (lenient-ignore, NOT a 422) because
`render` is a presentation hint, not part of the verdict contract. The markdown is rendered
server-side by the shared pipelex renderers (`format_validate_markdown` / `render_invalid_verdict_markdown`), the
invalid arm's from the very items its `errors` holds, in the same view, so the Markdown never says what that view leaves
out of them.
"""

from collections.abc import Mapping, Sequence
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from mthds.protocol.problem.models import ProblemItem
from mthds.protocol.problem.registry import CoreCode
from pipelex.base_exceptions import ValidationErrorCategory, ValidationErrorItem
from pipelex.errors.bundle_validation_failure import BundleValidationFailure
from pipelex.errors.problem import ProblemView, make_problem, make_problem_item
from pipelex.plugins.bundle_validator_registry import BundleValidatorRegistry
from pipelex.system.caller_identity import CallerIdentity
from pytest_mock import MockerFixture

from pipelex_api.api_config import ApiConfig
from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.routes import router as api_router
from tests.unit._constants import INVALID_MAIN_PIPE_MTHDS, VALID_MTHDS

_PIPELINE_NS = "pipelex_api.routes.pipelex.pipeline"
_MODE = "temporal"

# The wording a validation item carries for the operator's tools, which no view of the verdict's items holds.
_OPERATOR_WORDING = "operator-wording-5c1e: the step failed reading /srv/pipelex/cache/index.db"

# A parameter its code declares operator-only, which an item read back from elsewhere may still carry.
_OPERATOR_ONLY_COMPONENT = "operator-only-component-9b2d"


class _InvalidVerdictValidator:
    """Answers an invalid verdict whose validation item speaks in the operator's words, and whose problem items do not."""

    async def validate_bundles(
        self,
        *,
        mthds_contents: list[str] | None,  # noqa: ARG002
        mthds_sources: list[str] | None,  # noqa: ARG002
        allow_signatures: bool,  # noqa: ARG002
        library_dirs: Sequence[Path] | None,  # noqa: ARG002
        caller_identity: CallerIdentity | None,  # noqa: ARG002
        graph_pipe_code: str | None,  # noqa: ARG002
        submitted_files: Mapping[str, bytes] | None,  # noqa: ARG002
        method_dir: Path | None,  # noqa: ARG002
        methods_dirs: Sequence[Path] | None,  # noqa: ARG002
        read_scope: str | None,  # noqa: ARG002
    ) -> BundleValidationFailure:
        located_item = make_problem_item(code=CoreCode.METHOD_SCHEMA_VIOLATION, params={"field_path": "pipe.echo", "finding": "it is not a pipe"})
        # Built by hand, as a stored record read back may be, with a parameter only the operator reads.
        read_back_item = ProblemItem.model_validate(
            {
                "code": CoreCode.RUNTIME_MISCONFIGURED,
                "detail": "The runtime is misconfigured, so it cannot serve this request.",
                "params": {"component": _OPERATOR_ONLY_COMPONENT},
            }
        )
        return BundleValidationFailure(
            problem=make_problem(code=CoreCode.METHOD_INVALID, view=ProblemView.OPERATOR, errors=[located_item, read_back_item]),
            validation_errors=[
                ValidationErrorItem(category=ValidationErrorCategory.BLUEPRINT_VALIDATION, message=_OPERATOR_WORDING),
                ValidationErrorItem(category=ValidationErrorCategory.BLUEPRINT_VALIDATION, message=_OPERATOR_WORDING),
            ],
        )


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(app)


class TestValidateRenderedMarkdown:
    def test_default_request_has_no_rendered_markdown(self):
        # Off by default: the response is the plain structured verdict, byte-parity with today.
        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [VALID_MTHDS]})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is True
        assert "rendered_markdown" not in body

    def test_markdown_requested_valid_arm_carries_rendered_markdown(self):
        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [VALID_MTHDS], "render": ["markdown"]})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is True
        assert body["rendered_markdown"].startswith("# Validation passed")
        # The view rides alongside the structured fields, which remain the contract.
        assert "validated_pipes" in body

    def test_markdown_requested_invalid_arm_carries_rendered_markdown(self):
        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [INVALID_MAIN_PIPE_MTHDS], "render": ["markdown"]})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is False
        assert body["rendered_markdown"].startswith("# Validation failed")
        # The structured verdict is still present; markdown is the view, not a replacement.
        assert body["errors"]

    def test_invalid_arm_without_render_has_no_rendered_markdown(self):
        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [INVALID_MAIN_PIPE_MTHDS]})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is False
        assert "rendered_markdown" not in body

    def test_unknown_render_token_is_ignored_not_422(self):
        # Lenient-ignore: an unsupported token yields the 200 verdict with NO rendered field —
        # the one place the request-shape-422 contract deliberately does not apply.
        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [VALID_MTHDS], "render": ["bogus"]})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is True
        assert "rendered_markdown" not in body

    def test_mixed_known_and_unknown_tokens_render_the_known_one(self):
        # Per-token resolution: a known token renders, the unknown one is dropped (not poisoning).
        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [VALID_MTHDS], "render": ["markdown", "bogus"]})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["rendered_markdown"].startswith("# Validation passed")

    def test_a_caller_reads_only_the_caller_s_wording_in_both_the_items_and_the_markdown(self, mocker: MockerFixture):
        # The request is the caller's (no authentication marked it the operator's): its `errors` are the caller's view of
        # the verdict's items, and the Markdown beside them is rendered from those very items, never from the validation
        # items' own messages or a parameter that view leaves out.
        config = ApiConfig(orchestration_mode=_MODE, allow_request_orchestration_mode_override=False)
        mocker.patch(f"{_PIPELINE_NS}.get_api_config", return_value=config)
        registry = BundleValidatorRegistry({_MODE: _InvalidVerdictValidator()})
        mocker.patch(f"{_PIPELINE_NS}.get_bundle_validator_registry", return_value=registry)

        response = _build_client().post("/v1/validate", json={"mthds_contents": [VALID_MTHDS], "render": ["markdown"]})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is False
        assert _OPERATOR_WORDING not in response.text
        assert _OPERATOR_ONLY_COMPONENT not in response.text
        markdown = body["rendered_markdown"]
        assert markdown.startswith("# Validation failed")
        # Every item of `errors` is in the Markdown, by its code and in its sentence.
        for item in body["errors"]:
            assert f"(`{item['code']}`)" in markdown
            assert f"   - {item['detail']}" in markdown
