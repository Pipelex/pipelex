"""Route-level tests for `method_ref` as a run source on /execute and /start.

The pipeline runner is mocked (as in `test_pipeline_bundle`) and the clone cache is stubbed
with a local git repository (`install_method_package` in conftest), so these pin the API
layer's contract: the fetched package is read from its commit's git objects as a method tree,
written as the run's one library directory, the caller's own; the entry pipe defaults to the
manifest's `main_pipe` (a request `pipe_code` overrides); provenance `{address, tag,
commit_sha, tree_digest, display_name}` lands on the response; the exclusivity rules 422; the
execution-locus gate refuses Python where it must; and each resolution failure maps to its
distinct code + status as RFC 7807 `problem+json`, the status being the code's.
"""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from mthds.method_tree.digest import digest_of_contents
from mthds.protocol.problem.registry import CoreCode
from pipelex.errors.error_codes import ErrorCode, error_code_spec
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.methods.exceptions import MethodFetchError
from pipelex.methods.package_reason import MethodPackageReason
from pipelex.pipeline.pipeline_response import PipelexRunResultStart, RunState
from pytest_mock import MockerFixture

from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.problem_view import mark_operator_request
from pipelex_api.routes.pipelex.pipeline import router as pipeline_router
from tests.unit._constants import STUB_METHOD_ADDRESS, STUB_METHOD_COMMIT_SHA, STUB_METHOD_MANIFEST, VALID_MTHDS
from tests.unit._problems import assert_problem

_METHOD_REF = f"{STUB_METHOD_ADDRESS}@v0.1.0"
_TREE_NS = "pipelex_api.method_tree_request"

# The digest of the stub package's tree: its manifest and its one bundle.
_STUB_TREE_DIGEST = digest_of_contents({"METHODS.toml": STUB_METHOD_MANIFEST.encode("utf-8"), "documents.mthds": VALID_MTHDS.encode("utf-8")})

# The stub manifest declaring the human-readable name a host names the run's method by.
_DISPLAY_NAME = "Document Smoke Test"
_MANIFEST_WITH_DISPLAY_NAME = STUB_METHOD_MANIFEST.replace('name = "documents"\n', f'name = "documents"\ndisplay_name = "{_DISPLAY_NAME}"\n', 1)
_DISPLAY_NAME_TREE_DIGEST = digest_of_contents(
    {"METHODS.toml": _MANIFEST_WITH_DISPLAY_NAME.encode("utf-8"), "documents.mthds": VALID_MTHDS.encode("utf-8")}
)

_PIPE_FUNC_PY = "def echo(working_memory):\n    return 'hi'\n"

_STRUCTURES_PY = """\
from pipelex.core.stuffs.structured_content import StructuredContent


class Invoice(StructuredContent):
    total: float
"""


def _build_client(mocker: MockerFixture, *, as_operator: bool = False) -> tuple[TestClient, dict[str, Any]]:
    """Wire an app whose ApiRunner is mocked and records what the run actually saw.

    `as_operator` marks each request as the operator's, whose view carries a refusal's own message in `diagnostics`.
    """
    app = FastAPI()
    app.include_router(pipeline_router, prefix="/v1", dependencies=[Depends(mark_operator_request)] if as_operator else [])
    register_exception_handlers(app)

    snapshot: dict[str, Any] = {}

    fake_execute_response = mocker.MagicMock()
    fake_execute_response.model_dump.return_value = {
        "pipeline_run_id": "run-1",
        "state": "COMPLETED",
        "pipe_output": {"working_memory": {"root": {}, "aliases": {}}},
    }
    fake_execute_response.pipe_output.tokens_usages = None

    def _record(library_dirs: list[str] | None, run_kwargs: dict[str, Any]) -> None:
        snapshot["library_dirs"] = library_dirs
        snapshot["mthds_contents"] = run_kwargs.get("mthds_contents")
        snapshot["pipe_code"] = run_kwargs.get("pipe_code")
        if library_dirs:
            root = Path(library_dirs[0])
            snapshot["files"] = sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())
        else:
            snapshot["files"] = None

    def _make_runner(**kwargs: Any) -> Any:
        library_dirs: list[str] | None = kwargs.get("library_dirs")
        snapshot["library_dirs_are_callers"] = kwargs.get("library_dirs_are_callers")
        runner = mocker.MagicMock()

        async def _execute(**run_kwargs: Any) -> Any:
            _record(library_dirs, run_kwargs)
            return fake_execute_response

        async def _start(**run_kwargs: Any) -> Any:
            _record(library_dirs, run_kwargs)
            return PipelexRunResultStart(
                pipeline_run_id="run-1",
                created_at="2026-01-15T12:00:00Z",
                state=RunState.STARTED,
                workflow_id="wf-1",
            )

        runner.execute = _execute
        runner.start = _start
        return runner

    mocker.patch("pipelex_api.routes.pipelex.pipeline.ApiRunner", side_effect=_make_runner)
    return TestClient(app), snapshot


class TestMethodRefRun:
    def test_execute_rides_fetched_contents_defaults_main_pipe_and_carries_provenance(
        self, mocker: MockerFixture, install_method_package: Callable[..., Path]
    ):
        install_method_package(files={"documents.mthds": VALID_MTHDS})
        client, snapshot = _build_client(mocker)
        response = client.post("/v1/execute", json={"method_ref": _METHOD_REF, "inputs": {"text": "hi"}})
        assert response.status_code == 200, response.text
        # The package is the run's method tree, written whole as its one library directory, the caller's own.
        assert snapshot["mthds_contents"] is None
        assert snapshot["files"] == ["METHODS.toml", "documents.mthds"]
        assert snapshot["library_dirs_are_callers"] is True
        # The entry pipe came from the manifest's `main_pipe`, qualified by the bundle that declares it.
        assert snapshot["pipe_code"] == "smoke.echo"
        # The tree is removed once the request returns.
        assert not Path(snapshot["library_dirs"][0]).exists()
        # Provenance: resolved full address, the requested tag, the fetched commit SHA, the digest of the tree it ran, and
        # no display name, which the stub manifest does not declare.
        assert response.json()["method_provenance"] == {
            "address": STUB_METHOD_ADDRESS,
            "tag": "v0.1.0",
            "commit_sha": STUB_METHOD_COMMIT_SHA,
            "tree_digest": _STUB_TREE_DIGEST,
            "display_name": None,
        }

    @pytest.mark.parametrize(
        ("method_ref", "expected_tag"),
        [
            (_METHOD_REF, "v0.1.0"),
            (STUB_METHOD_ADDRESS, None),
        ],
    )
    def test_the_resolution_line_names_the_tag_and_the_commit_the_run_executes(
        self,
        mocker: MockerFixture,
        install_method_package: Callable[..., Path],
        caplog: pytest.LogCaptureFixture,
        method_ref: str,
        expected_tag: str | None,
    ):
        """An operator reads off this line which version of the package a hosted run executed."""
        install_method_package(files={"documents.mthds": VALID_MTHDS})
        client, _ = _build_client(mocker)

        with caplog.at_level(logging.INFO, logger="pipelex_api.method_source"):
            response = client.post("/v1/execute", json={"method_ref": method_ref, "inputs": {"text": "hi"}})

        assert response.status_code == 200, response.text
        (resolution_record,) = [record for record in caplog.records if record.getMessage() == "A method reference was resolved to a package"]
        record_fields = vars(resolution_record)
        assert record_fields["method_ref"] == method_ref
        assert record_fields["package_address"] == STUB_METHOD_ADDRESS
        assert record_fields["fetched_tag"] == expected_tag
        assert record_fields["commit_sha"] == STUB_METHOD_COMMIT_SHA

    def test_request_pipe_code_overrides_manifest_main_pipe(self, mocker: MockerFixture, install_method_package: Callable[..., Path]):
        install_method_package(files={"documents.mthds": VALID_MTHDS})
        client, snapshot = _build_client(mocker)
        response = client.post("/v1/execute", json={"method_ref": _METHOD_REF, "pipe_code": "smoke.echo", "inputs": {"text": "hi"}})
        assert response.status_code == 200, response.text
        assert snapshot["pipe_code"] == "smoke.echo"

    def test_start_carries_provenance_on_the_ack(self, mocker: MockerFixture, install_method_package: Callable[..., Path]):
        install_method_package(files={"documents.mthds": VALID_MTHDS})
        client, snapshot = _build_client(mocker)
        response = client.post("/v1/start", json={"method_ref": STUB_METHOD_ADDRESS, "inputs": {"text": "hi"}})
        assert response.status_code == 202, response.text
        assert snapshot["files"] == ["METHODS.toml", "documents.mthds"]
        body = response.json()
        assert body["pipeline_run_id"] == "run-1"
        # A bare address: provenance records tag=None and the resolved HEAD commit.
        assert body["method_provenance"] == {
            "address": STUB_METHOD_ADDRESS,
            "tag": None,
            "commit_sha": STUB_METHOD_COMMIT_SHA,
            "tree_digest": _STUB_TREE_DIGEST,
            "display_name": None,
        }

    @pytest.mark.parametrize(("route", "expected_status"), [("/v1/execute", 200), ("/v1/start", 202)])
    def test_provenance_carries_the_display_name_the_manifest_declares(
        self, mocker: MockerFixture, install_method_package: Callable[..., Path], route: str, expected_status: int
    ):
        """Both run routes report the package's declared display name, which a host names the run's method by."""
        install_method_package(files={"documents.mthds": VALID_MTHDS}, manifest_toml=_MANIFEST_WITH_DISPLAY_NAME)
        client, _ = _build_client(mocker)
        response = client.post(route, json={"method_ref": _METHOD_REF, "inputs": {"text": "hi"}})
        assert response.status_code == expected_status, response.text
        assert response.json()["method_provenance"] == {
            "address": STUB_METHOD_ADDRESS,
            "tag": "v0.1.0",
            "commit_sha": STUB_METHOD_COMMIT_SHA,
            "tree_digest": _DISPLAY_NAME_TREE_DIGEST,
            "display_name": _DISPLAY_NAME,
        }

    def test_inline_runs_carry_no_provenance(self, mocker: MockerFixture):
        client, _ = _build_client(mocker)
        execute_response = client.post("/v1/execute", json={"mthds_contents": [VALID_MTHDS], "inputs": {"text": "hi"}})
        assert execute_response.status_code == 200
        assert "method_provenance" not in execute_response.json()
        start_response = client.post("/v1/start", json={"mthds_contents": [VALID_MTHDS], "inputs": {"text": "hi"}})
        assert start_response.status_code == 202
        assert start_response.json()["method_provenance"] is None

    def test_method_ref_is_exclusive_with_inline_contents_and_bundles(self, mocker: MockerFixture, install_method_package: Callable[..., Path]):
        install_method_package(files={"documents.mthds": VALID_MTHDS})
        client, _ = _build_client(mocker, as_operator=True)
        with_contents = client.post("/v1/execute", json={"method_ref": _METHOD_REF, "mthds_contents": [VALID_MTHDS]})
        with_bundle = client.post("/v1/execute", json={"method_ref": _METHOD_REF, "files": {"main.mthds": VALID_MTHDS}})
        for response in (with_contents, with_bundle):
            assert response.status_code == 422, response.text
            problem = response.json()
            assert problem["code"] == CoreCode.REQUEST_INVALID
            assert problem.get("params") == {"field": "method_ref"}
            assert "mutually exclusive" in problem["diagnostics"]["message"]

    def test_an_address_this_runtime_does_not_fetch_is_a_422_naming_the_field(
        self, mocker: MockerFixture, install_method_package: Callable[..., Path]
    ):
        install_method_package(files={"documents.mthds": VALID_MTHDS})
        client, _ = _build_client(mocker, as_operator=True)
        response = client.post("/v1/execute", json={"method_ref": "gitlab.com/acme/tools", "inputs": {}})
        assert response.status_code == 422, response.text
        assert response.headers["content-type"] == "application/problem+json"
        problem = response.json()
        assert problem["code"] == CoreCode.REQUEST_UNSUPPORTED
        assert problem["domain"] == "input"
        assert problem.get("params", {}).get("field") == "method_ref"
        assert problem["diagnostics"]["error_class"] == "MethodRefParseError"

    def test_unknown_package_is_404_problem_json(self, mocker: MockerFixture, install_method_package: Callable[..., Path]):
        install_method_package(files={"documents.mthds": VALID_MTHDS})
        client, _ = _build_client(mocker, as_operator=True)
        unknown_address = "github.com/pipelex/methods/nonexistent"
        response = client.post("/v1/execute", json={"method_ref": unknown_address, "inputs": {}})
        assert response.status_code == 404, response.text
        assert response.headers["content-type"] == "application/problem+json"
        problem = response.json()
        assert problem["code"] == CoreCode.METHOD_NOT_FOUND
        assert problem.get("params") == {"method_ref": unknown_address}
        assert problem["diagnostics"]["error_class"] == "MethodPackageNotFoundError"
        # The operator's message teaches: it lists the packages the repository does contain.
        assert STUB_METHOD_ADDRESS in problem["diagnostics"]["message"]

    @pytest.mark.parametrize(
        ("code", "params", "expected_status"),
        [
            (CoreCode.METHOD_FETCH_FAILED, {}, 502),
            (CoreCode.METHOD_NOT_FOUND, {}, 404),
            (CoreCode.METHOD_PACKAGE_INVALID, {"reason": MethodPackageReason.MANIFEST_INVALID}, 422),
            (PipelexErrorCode.CONFIG_DEPENDENCY_MISSING, {}, 500),
        ],
    )
    def test_a_fetch_failure_answers_the_status_of_its_code(
        self, mocker: MockerFixture, code: ErrorCode, params: dict[str, Any], expected_status: int
    ):
        """A failed fetch answers whatever code its raise site chose, with that code's status from the error registry."""
        fetch_error = MethodFetchError(f"Failed to fetch method '{STUB_METHOD_ADDRESS}': boom").for_method_ref(method_ref=STUB_METHOD_ADDRESS)
        stub_cache = mocker.MagicMock()
        stub_cache.pinned_package.side_effect = fetch_error.with_error_code(code).with_params(**params)
        mocker.patch("pipelex_api.method_source.get_method_clone_cache", return_value=stub_cache)
        client, _ = _build_client(mocker)
        response = client.post("/v1/execute", json={"method_ref": STUB_METHOD_ADDRESS, "inputs": {}})
        assert response.status_code == expected_status, response.text
        assert response.headers["content-type"] == "application/problem+json"
        problem = response.json()
        assert error_code_spec(code).status == expected_status
        assert problem["status"] == expected_status
        assert problem["code"] == code
        assert problem["retry"] == error_code_spec(code).retry
        # The caller's view: the code's sentences, never the fetch's own message.
        assert "boom" not in response.text
        assert "diagnostics" not in problem

    def test_python_package_forbidden_when_not_sandbox_hosted(self, mocker: MockerFixture, install_method_package: Callable[..., Path]):
        install_method_package(files={"documents.mthds": VALID_MTHDS, "funcs/pipe_func.py": _PIPE_FUNC_PY})
        mocker.patch(f"{_TREE_NS}.is_pipe_func_sandbox_hosted", return_value=False)
        client, _ = _build_client(mocker)
        response = client.post("/v1/execute", json={"method_ref": _METHOD_REF, "inputs": {}})
        problem = assert_problem(response, status=501, code="pipelex.deployment.custom_code_requires_sandbox")
        assert problem["params"] == {"origin": "package"}

    def test_python_package_is_written_whole_when_sandbox_hosted(self, mocker: MockerFixture, install_method_package: Callable[..., Path]):
        install_method_package(files={"documents.mthds": VALID_MTHDS, "funcs/pipe_func.py": _PIPE_FUNC_PY})
        mocker.patch(f"{_TREE_NS}.is_pipe_func_sandbox_hosted", return_value=True)
        client, snapshot = _build_client(mocker)
        response = client.post("/v1/execute", json={"method_ref": _METHOD_REF, "inputs": {}})
        assert response.status_code == 200, response.text
        # The whole tree is written, its bundle, its manifest and its Python, for the load to read as one method.
        assert snapshot["mthds_contents"] is None
        assert snapshot["files"] == ["METHODS.toml", "documents.mthds", "funcs/pipe_func.py"]
        # The temp dir is cleaned once the request returns.
        assert not Path(snapshot["library_dirs"][0]).exists()

    def test_structures_package_refused_even_when_sandbox_hosted(self, mocker: MockerFixture, install_method_package: Callable[..., Path]):
        install_method_package(files={"documents.mthds": VALID_MTHDS, "structures/models.py": _STRUCTURES_PY})
        mocker.patch(f"{_TREE_NS}.is_pipe_func_sandbox_hosted", return_value=True)
        client, _ = _build_client(mocker, as_operator=True)
        response = client.post("/v1/execute", json={"method_ref": _METHOD_REF, "inputs": {}})
        # The method's own structure classes are its author's to change: a 422, the code's status.
        assert response.status_code == 422, response.text
        assert response.headers["content-type"] == "application/problem+json"
        problem = response.json()
        assert problem["code"] == PipelexErrorCode.DEPLOYMENT_PYTHON_STRUCTURES_REFUSED
        assert problem["domain"] == "method"
        assert problem["next_step"]["kind"] == "change_method"
        assert problem["diagnostics"]["error_class"] == "MethodStructuresRefusedError"
        # The operator's message names the rule and teaches the fix.
        assert "MTHDS concepts" in problem["diagnostics"]["message"]
