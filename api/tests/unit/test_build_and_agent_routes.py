"""Smoke + validation tests for /validate, /build/* and /build/{concept,pipe-spec,models}."""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mthds.protocol.models import ModelCategory as MthdsModelCategory
from pipelex.builder.operations.models_ops import ModelCategory
from pipelex.interpreter_hub import get_library_manager
from pipelex.pipe_run.exceptions import DryRunError
from pipelex.pipeline.bundle_validator import DryRunOutput, DryRunStatus
from pytest_mock import MockerFixture

from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.routes import router as api_router
from tests.unit._constants import VALID_MTHDS


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(app)


class TestBuildAndAgentRoutes:
    def test_validate_rejects_oversized_mthds(self):
        client = _build_client()
        oversized = "a" * (2 * 1024 * 1024)  # 2 MiB > 1 MiB cap
        response = client.post(
            "/v1/validate",
            json={"mthds_contents": [oversized]},
        )
        assert response.status_code == 422
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["error_type"] == "ValidationError"

    def test_validate_rejects_too_many_files(self):
        client = _build_client()
        response = client.post(
            "/v1/validate",
            json={"mthds_contents": [VALID_MTHDS] * 32},
        )
        assert response.status_code == 422
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["error_type"] == "ValidationError"

    def test_validate_invalid_mthds_returns_200_invalid_report(self):
        # `/validate` is a diagnostic endpoint: an invalid bundle is a produced verdict, so it rides
        # a 200 `InvalidReport` (discriminated on `is_valid: false`) — NOT a 422 problem document,
        # and NOT the older `{success, mthds_contents, message}` 422 envelope. Invalid TOML reliably
        # triggers a `ValidateBundleError` from the interpreter, which the route converts to the
        # invalid arm. The verdict is carried by `is_valid`/`message`, not the status code.
        client = _build_client()
        response = client.post(
            "/v1/validate",
            json={"mthds_contents": ["this is not valid TOML !!!"]},
        )
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("application/json")
        body = response.json()
        assert body["is_valid"] is False
        assert body["is_runnable"] is False
        # The pipelex message is preserved (caller-facing under `_authors_caller_facing_message`) so
        # the client gets the actual interpreter complaint, not a generic placeholder.
        assert "TOML" in body["message"]
        # The diagnostics list is non-empty on every invalid arm — the structured-info invariant is
        # total. A raw TOML-syntax error is a parse-level failure the interpreter raises with no
        # categorized error-data, but the shared builder's last-resort residual still emits one
        # `blueprint_validation` item carrying the message (no `source` at this layer). A categorized
        # failure (e.g. an invalid `main_pipe`) yields richer items; that path is pinned in
        # test_validate_errors.py.
        assert isinstance(body["validation_errors"], list)
        assert body["validation_errors"], "an invalid verdict must carry a non-empty validation_errors[]"
        assert body["validation_errors"][0]["category"] == "blueprint_validation"
        assert body["validation_errors"][0]["message"]
        # The valid arm's structural artifacts + the retired `success` extra are absent.
        assert "bundle_blueprint" not in body
        assert "success" not in body

    # NOTE: the former `main_pipe` precondition on /validate is deleted (protocol alignment
    # D2) — a bundle without `main_pipe` now answers 200 with `graph_spec=null`. The
    # regression pin for that behavior (both backends) lives in `test_validate_envelope.py`.

    def test_build_inputs_rejects_oversized_pipe_ref(self):
        client = _build_client()
        long_ref = "x" * 1024
        response = client.post(
            "/v1/build/inputs",
            json={"files": [{"content": VALID_MTHDS}], "pipe_ref": long_ref},
        )
        assert response.status_code == 422
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["error_type"] == "ValidationError"

    def test_build_concept_rejects_oversized_spec(self):
        client = _build_client()
        big_spec = {"description": "x" * (512 * 1024)}  # 512 KiB > 256 KiB cap
        response = client.post("/v1/build/concept", json={"spec": big_spec})
        assert response.status_code == 422
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["error_type"] == "ValidationError"

    @pytest.mark.parametrize("structure", ["string", {"f": 42}])
    def test_build_concept_refuses_malformed_structure_with_a_typed_error(self, structure: Any):
        # `parse_concept_spec` validates the raw shape of `structure` and raises the
        # typed `ConceptSpecError`, so the route answers a problem document rather
        # than an opaque 500 from a bare AttributeError / TypeError.
        client = _build_client()
        response = client.post(
            "/v1/build/concept",
            json={"spec": {"concept_code": "Thing", "description": "d", "structure": structure}},
        )
        assert response.status_code == 422
        assert response.headers["content-type"] == "application/problem+json"
        body = response.json()
        assert body["error_type"] == "ConceptSpecError"
        assert body["error_domain"] == "input"

    def test_build_pipe_spec_rejects_unknown_pipe_type(self):
        # `parse_pipe_spec` raises a bare `ValueError` for an unknown pipe_type
        # (documented in its docstring). The route must classify that as a
        # caller-input 422 — not let it escape as an opaque 500 through the
        # global `Exception` fallback. Regression for `TODOS.md` Q4.
        client = _build_client()
        response = client.post(
            "/v1/build/pipe-spec",
            json={"pipe_type": "NotARealPipeType", "spec": {"pipe_code": "x", "description": "d", "output": "Text"}},
        )
        assert response.status_code == 422
        assert response.headers["content-type"] == "application/problem+json"
        body = response.json()
        assert body["error_type"] == "ValidationError"
        assert "NotARealPipeType" in body["detail"]

    @pytest.mark.parametrize("bad_type", ["not-a-real-category", ""])
    def test_models_rejects_invalid_category(self, bad_type: str):
        # The empty string is an explicitly-supplied (invalid) filter value, not an absent
        # param — it must fail loudly like any other unknown category, not silently return
        # the unfiltered deck.
        client = _build_client()
        response = client.get(f"/v1/models?type={bad_type}")
        assert response.status_code == 422
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["error_type"] == "InvalidModelCategory"

    def test_models_rejects_repeated_type_param(self):
        # D11: the protocol's `type` filter is a single plain value. The old route accepted
        # repeated `?type=` values (list[str] Query) — that extension is dropped, and FastAPI
        # would otherwise silently keep one of the values, so the rejection is explicit.
        # Generic ValidationError (not InvalidModelCategory): both values are valid
        # categories — what's wrong is the arity.
        client = _build_client()
        response = client.get("/v1/models?type=llm&type=extract")
        assert response.status_code == 422
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["error_type"] == "ValidationError"

    def test_models_returns_protocol_deck(self):
        # The deck is the protocol `ModelDeck` shape produced by `PipelexMTHDSProtocol.models`:
        # a non-empty flat `models` list (regression for the silently-empty deck the old raw
        # per-category payload caused in the SDK — F2) plus this implementation's routing
        # extensions, keyed by category (the same alias name exists in several categories —
        # a flat map would silently drop entries on collision). The old raw keys (`presets`
        # by category, `success`) are gone. The flat list speaks the protocol's categories only,
        # while the extensions are keyed by every category this runtime serves, `judgment` included.
        client = _build_client()
        response = client.get("/v1/models")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["models"], "the protocol deck must carry a non-empty models list"
        first_model = body["models"][0]
        assert first_model["name"]
        assert first_model["type"]
        assert {model["type"] for model in body["models"]} <= {category.value for category in MthdsModelCategory}
        valid_categories = {category.value for category in ModelCategory}
        assert set(body["aliases"]) <= valid_categories
        assert all(isinstance(category_aliases, dict) for category_aliases in body["aliases"].values())
        assert set(body["waterfalls"]) <= valid_categories
        assert "presets" not in body
        assert "success" not in body

    def test_models_single_type_filter(self):
        client = _build_client()
        response = client.get("/v1/models?type=llm")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["models"]
        assert {model["type"] for model in body["models"]} == {"llm"}
        assert set(body["aliases"]) <= {"llm"}

    def test_empty_mthds_contents_rejected(self):
        # `/validate` is the last route on the `mthds_contents` envelope (it is protocol-owned; the
        # build routes moved to `files[]`, whose empty-selector rejection lives in the envelope suite).
        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": []})
        assert response.status_code == 422
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["error_type"] == "ValidationError"

    def test_build_runner_tears_down_library_when_success_path_raises(self, mocker: MockerFixture):
        # The loaded-on-success contract makes the route own teardown of validate_bundle's library.
        # A failure anywhere in the success window (here: the SKIPPED guard, the first statement
        # inside the try) must NOT leak that library — the finally tears down the exact id
        # validate_bundle opened.
        library_manager = get_library_manager()
        open_spy = mocker.spy(library_manager, "open_library")
        teardown_spy = mocker.spy(library_manager, "teardown")
        mocker.patch(
            "pipelex_api.routes.pipelex.build.runner._reject_if_requested_pipe_skipped",
            side_effect=RuntimeError("synthetic success-path failure"),
        )

        # raise_server_exceptions=False: the synthetic RuntimeError reaches the
        # catch-all `Exception` handler, but Starlette's ServerErrorMiddleware
        # would otherwise re-raise it through the TestClient in test mode. The
        # convention matches `test_exception_handlers.py`.
        app = FastAPI()
        app.include_router(api_router, prefix="/v1")
        register_exception_handlers(app)
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/v1/build/runner",
            json={"files": [{"content": VALID_MTHDS}], "pipe_ref": "smoke.echo"},
        )

        # The synthetic RuntimeError propagates to the global Exception handler.
        assert response.status_code == 500
        # validate_bundle DID open a library and leave it current — capture its id.
        assert open_spy.spy_return is not None
        created_library_id, _ = open_spy.spy_return
        # The fix: teardown runs anyway, with the exact id open_library returned.
        teardown_spy.assert_called_once_with(library_id=created_library_id)

    def test_build_runner_none_crate_is_a_server_fault_not_a_verdict(self, mocker: MockerFixture):
        # The "unreachable" None-crate guard is an internal invariant break — a server fault (5xx),
        # never a caller-facing verdict. Before the fix it raised ValidateBundleError OUTSIDE the
        # except that maps it to the 200 invalid arm, so it rendered as a request-shape-style 422,
        # contradicting the route's own contract. The library must still be torn down (no leak).
        library_manager = get_library_manager()
        open_spy = mocker.spy(library_manager, "open_library")
        teardown_spy = mocker.spy(library_manager, "teardown")
        mocker.patch.object(library_manager, "get_crate", return_value=None)

        app = FastAPI()
        app.include_router(api_router, prefix="/v1")
        register_exception_handlers(app)
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/v1/build/runner",
            json={"files": [{"content": VALID_MTHDS}], "pipe_ref": "smoke.echo"},
        )

        assert response.status_code == 500, response.text
        assert response.headers["content-type"] == "application/problem+json"
        assert open_spy.call_count >= 1
        assert open_spy.call_count == teardown_spy.call_count

    def test_build_runner_succeeds_and_returns_python_code_and_structures(self):
        # /build/runner rides validate_bundle (loaded-on-success) and the codegen types projection
        # (D9): a 200 valid arm proves the sweep passed, the library survived for code generation,
        # and the response carries BOTH the runner script and the stamped structures projection the
        # script imports from (structures.py + codegen.lock), the retired `success` bool gone.
        client = _build_client()
        response = client.post(
            "/v1/build/runner",
            json={"files": [{"content": VALID_MTHDS}], "pipe_ref": "smoke.echo"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is True
        assert "success" not in body
        assert body["pipe_ref"] == "smoke.echo"
        assert body["python_code"]
        assert "echo" in body["python_code"]
        structures = body["structures"]
        assert structures["directory"] == "structures"
        artifact_paths = [artifact["path"] for artifact in structures["artifacts"]]
        assert artifact_paths == ["structures.py"]
        assert structures["artifacts"][0]["content"].startswith("# >>> pipelex-codegen-stamp >>>")
        assert structures["lock_filename"] == "codegen.lock"
        assert "crate_fingerprint" in structures["lock"]

    def test_build_runner_keeps_library_open_for_codegen_then_tears_down_once(self, mocker: MockerFixture):
        # The loaded-on-success contract (D6): the inner sweep must NOT tear the library down — if it
        # did, get_required_pipe + generate_runner_code would have failed before the response. Teardown
        # happens exactly once, in the route's finally, after code generation.
        library_manager = get_library_manager()
        teardown_spy = mocker.spy(library_manager, "teardown")
        client = _build_client()
        response = client.post(
            "/v1/build/runner",
            json={"files": [{"content": VALID_MTHDS}], "pipe_ref": "smoke.echo"},
        )
        assert response.status_code == 200, response.text
        teardown_spy.assert_called_once()

    # NOTE: the "opens exactly one library, tears down that same id" property (C-2 / Q-5) is pinned for
    # all three build routes in `test_build_routes_envelope.py`, which covers both cores they now ride.

    def test_build_runner_rejects_when_requested_pipe_is_skipped(self, mocker: MockerFixture):
        # C-3: a cross-package unresolved dependency makes validate_pipes record the requested pipe
        # SKIPPED (not a hard failure), so the sweep returns normally. generate_runner_code reads only
        # the pipe's own inputs/output, so without a guard the route would emit runner code for a
        # pipeline that cannot run. The guard must reject the requested-pipe-SKIPPED case with a 422
        # and never reach code generation. (Other, unrelated SKIPPED pipes stay tolerated.)
        skipped_result = {
            "smoke.echo": DryRunOutput(
                pipe_code="echo",
                pipe_ref="smoke.echo",
                status=DryRunStatus.SKIPPED,
                error_message="Skipped dry run for pipe 'smoke.echo': unresolved dependency: other_pkg.missing",
            )
        }
        # The sweep now runs inside validate_bundle (the route no longer calls it directly), so the
        # SKIPPED outcome is planted at its source module.
        mocker.patch(
            "pipelex.pipeline.validate_bundle.BundleValidator.validate_pipes",
            new=mocker.AsyncMock(return_value=skipped_result),
        )
        generate_spy = mocker.patch("pipelex_api.routes.pipelex.build.runner.generate_runner_code")

        client = _build_client()
        response = client.post(
            "/v1/build/runner",
            json={"files": [{"content": VALID_MTHDS}], "pipe_ref": "smoke.echo"},
        )

        assert response.status_code == 422, response.text
        assert response.headers["content-type"] == "application/problem+json"
        body = response.json()
        assert body["error_type"] == "ValidationError"
        assert body["error_domain"] == "input"
        assert "echo" in body["detail"]
        # The guard short-circuits before code generation.
        generate_spy.assert_not_called()

    def test_build_runner_dry_run_failure_is_a_200_invalid_verdict(self, mocker: MockerFixture):
        # The `/validate` discipline on the build routes: a failed dry-run of a caller-submitted
        # bundle is a *produced negative verdict*, not a transport failure. validate_bundle's shared
        # cascade translates the DryRunError to ValidateBundleError, which the route renders as the
        # 200 invalid arm (is_valid: false + structured validation_errors[]) — the same wire shape
        # /build/inputs and /build/output return for the identical failure. (Breaking change from
        # the previous 422 problem+json.)
        mocker.patch(
            "pipelex.pipeline.validate_bundle.BundleValidator.validate_pipes",
            new=mocker.AsyncMock(side_effect=DryRunError("Dry run failed with 1 unexpected pipe failure(s): 'smoke.echo'")),
        )
        generate_spy = mocker.patch("pipelex_api.routes.pipelex.build.runner.generate_runner_code")

        client = _build_client()
        response = client.post(
            "/v1/build/runner",
            json={"files": [{"content": VALID_MTHDS}], "pipe_ref": "smoke.echo"},
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is False
        assert body["validation_errors"], "an invalid verdict must carry a non-empty validation_errors[]"
        assert "python_code" not in body
        # The failure short-circuits before code generation.
        generate_spy.assert_not_called()

    def test_validate_tears_down_validate_bundle_library_without_leaking(self, mocker: MockerFixture):
        # validate_bundle opens a library and leaves it loaded + current on success (the D6 contract);
        # /validate must own that teardown. Before the fix the route never tore it down, orphaning it on
        # every successful call (the best-effort graph dry-run opens + tears down its OWN library via
        # PipelexRunner, so that one was balanced). Assert the conservation property: every library opened
        # during the request is torn down — open count == teardown count. A leak shows up as opens > teardowns.
        library_manager = get_library_manager()
        open_spy = mocker.spy(library_manager, "open_library")
        teardown_spy = mocker.spy(library_manager, "teardown")

        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [VALID_MTHDS]})

        assert response.status_code == 200, response.text
        assert open_spy.call_count >= 1
        assert open_spy.call_count == teardown_spy.call_count
