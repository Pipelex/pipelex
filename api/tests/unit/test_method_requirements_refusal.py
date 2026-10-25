"""A sandbox-hosted deployment refuses a method whose requirements.txt its PipeFunc sandbox does not meet, naming the packages.

The package set is what the plugin providing the execution mode states; here a stub registered for the neutral
`sandbox` mode. A run is refused on the runner before the method's files load, before any dispatch, as a 422
`method.invalid` whose items locate each refused line of `requirements.txt`, the problem a local load of the same method
raises, and a validation is refused on the runner as the invalid verdict carrying the same items, before the validator is
reached, since a dispatched validator never reads the method's Python. A method of the runner's own library directories
whose requirements are not met is the deployment's fault, never the caller's.
"""

import asyncio
import sys
from collections.abc import Callable, Generator, Mapping, Sequence
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from mthds.protocol.problem.registry import CoreCode, MethodDependencyMissingKind, MethodDependencyMissingReason
from pipelex.config import get_config
from pipelex.errors.bundle_validation_failure import BundleValidationFailure
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.interpreter_hub import get_interpreter_hub
from pipelex.libraries.exceptions import MethodRequirementsNotMetError
from pipelex.libraries.method_tree_listing import MethodTreeListing
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.plugins.bundle_validator_registry import BundleValidatorRegistry
from pipelex.plugins.orchestrator_registry import OrchestratorRegistry
from pipelex.plugins.pipe_func_package_offer_registry import (
    PipeFuncPackageOffer,
    PipeFuncPackageOfferRegistry,
    PipeFuncPackageOfferRequest,
    PipeFuncPackageRefusal,
)
from pipelex.runtime_bridge.payloads import PipelexPipeDispatchAck, PipelexPipeRunOutput
from pipelex.system.caller_identity import CallerIdentity
from pytest_mock import MockerFixture

from pipelex_api.api_config import ApiConfig
from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.problem_view import mark_operator_request
from pipelex_api.routes import router as api_router
from tests.unit._constants import STUB_METHOD_ADDRESS

_PIPELINE_NS = "pipelex_api.routes.pipelex.pipeline"
_SANDBOX_ENVIRONMENT = "the Daytona sandbox snapshot 'pipelex-base-test'"
_ABSENT_PACKAGE = "pipelex-requirements-test-absent"
_UNRESOLVABLE_REQUIREMENT = "pandas<2"
_REFUSAL_REASON = "uv explains: Because pandas<2 conflicts with the base snapshot's pandas==2.2.3, the requirements are unsatisfiable."
# The conformance fixture's requirements.txt: a comment, then a requirement the sandbox holds at a version it refuses.
_UNMET_REQUIREMENTS_TEXT = "# The function imports pipelex alone\npydantic>=9999\n"
_REQUIREMENTS_FILE = "requirements.txt"

_PLAIN_MTHDS = """\
domain = "plain_demo"
main_pipe = "echo"

[pipe.echo]
type = "PipeCompose"
description = "Echo the data"
inputs = { data = "Text" }
output = "Text"
template = "$data"
"""

_PIPE_FUNC_MTHDS = """\
domain = "crunch_demo"
main_pipe = "crunch"

[pipe.crunch]
type = "PipeFunc"
description = "Crunch numbers in caller code"
inputs = { data = "Text" }
output = "Text"
function_name = "funcs.pipe_func.crunch"
"""

_PIPE_FUNC_PY = """\
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.system.registries.func_registry import pipe_func


@pipe_func()
async def crunch(working_memory: WorkingMemory) -> TextContent:
    return TextContent(text="crunched")
"""


class _RecordingOrchestrator:
    supports_fire_and_forget = True

    def __init__(self) -> None:
        self.dispatches: list[str] = []

    async def execute(self, *, pipe_job: PipeJob, delivery_assignment: DeliveryAssignment | None) -> PipelexPipeRunOutput:  # noqa: ARG002
        self.dispatches.append(pipe_job.pipe.code)
        msg = "These tests dispatch through /start only."
        raise AssertionError(msg)

    async def start(self, *, pipe_job: PipeJob, delivery_assignment: DeliveryAssignment | None) -> PipelexPipeDispatchAck:  # noqa: ARG002
        self.dispatches.append(pipe_job.pipe.code)
        return PipelexPipeDispatchAck(pipeline_run_id="run-1", workflow_id="wf-1")


class _UnreachableValidator:
    """A dispatched validator the requirements check must never let a refused method reach."""

    def __init__(self) -> None:
        self.calls = 0

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
        self.calls += 1
        msg = "A method refused for its requirements must not reach the validator."
        raise AssertionError(msg)


def _stated_offer(request: PipeFuncPackageOfferRequest) -> PipeFuncPackageOffer | PipeFuncPackageRefusal | None:
    """A small package set, whatever the requirements, except for a method asking for `pandas<2`, which no environment holds."""
    if any(line.text == _UNRESOLVABLE_REQUIREMENT for line in request.requirements):
        return PipeFuncPackageRefusal(environment="the Daytona sandbox", reason=_REFUSAL_REASON)
    return PipeFuncPackageOffer(
        environment=_SANDBOX_ENVIRONMENT,
        distributions={"pandas": "2.2.3", "openpyxl": "3.1.5", "pydantic": "2.12.3"},
        marker_environment={"python_version": "3.12", "sys_platform": "linux"},
    )


@pytest.fixture(name="sandbox_hosted_mode")
def sandbox_hosted_mode_fixture(mocker: MockerFixture) -> Generator[None, None, None]:
    """Run PipeFunc steps in the neutral `sandbox` mode, whose plugin states a small package set or refuses `pandas<2`."""
    mocker.patch(
        "pipelex.libraries.package_environments.get_pipe_func_package_offer_registry",
        return_value=PipeFuncPackageOfferRegistry({"sandbox": _stated_offer}),
    )
    pipe_func_config = get_config().interpreter.pipe_func
    previous = pipe_func_config.execution_mode
    pipe_func_config.execution_mode = "sandbox"
    try:
        yield
    finally:
        pipe_func_config.execution_mode = previous


def _build_client(
    mocker: MockerFixture, *, orchestrator: _RecordingOrchestrator, validator: _UnreachableValidator, as_operator: bool = False
) -> TestClient:
    """The routes behind the production handlers; `as_operator` marks each request as the operator's, who reads `diagnostics`."""
    mocker.patch(
        f"{_PIPELINE_NS}.get_api_config", return_value=ApiConfig(orchestration_mode="temporal", allow_request_orchestration_mode_override=False)
    )
    mocker.patch(f"{_PIPELINE_NS}.get_orchestrator_registry", return_value=OrchestratorRegistry({"temporal": orchestrator}))
    mocker.patch(f"{_PIPELINE_NS}.get_bundle_validator_registry", return_value=BundleValidatorRegistry({"temporal": validator}))
    app = FastAPI()
    app.include_router(api_router, prefix="/v1", dependencies=[Depends(mark_operator_request)] if as_operator else [])
    register_exception_handlers(app)
    return TestClient(app)


class TestMethodRequirementsRefusal:
    @pytest.mark.usefixtures("sandbox_hosted_mode")
    @pytest.mark.parametrize("route", ["/v1/execute", "/v1/start"])
    def test_a_run_whose_requirement_the_sandbox_does_not_meet_is_an_invalid_method_located_on_the_line(
        self, mocker: MockerFixture, route: str
    ) -> None:
        """The conformance case's refusal: a 422 `method.invalid` whose one item locates the requirement, as the caller reads it."""
        orchestrator = _RecordingOrchestrator()
        client = _build_client(mocker, orchestrator=orchestrator, validator=_UnreachableValidator())

        files = {"main.mthds": _PIPE_FUNC_MTHDS, "funcs/pipe_func.py": _PIPE_FUNC_PY, _REQUIREMENTS_FILE: _UNMET_REQUIREMENTS_TEXT}
        response = client.post(route, json={"files": files, "inputs": {"data": "1,2,3"}})

        assert response.status_code == 422, response.text
        assert response.headers["content-type"].startswith("application/problem+json")
        body = response.json()
        assert body["type"] == "https://mthds.ai/errors/method.invalid"
        assert body["code"] == CoreCode.METHOD_INVALID
        assert body["domain"] == "method"
        assert body["status"] == 422
        assert body["next_step"]["kind"] == "change_method"
        # The refusal of the method is an item, not the problem: the problem itself names no parameter and no location.
        assert "params" not in body
        assert "location" not in body
        assert body["errors"] == [
            {
                "code": CoreCode.METHOD_DEPENDENCY_MISSING,
                "detail": "The method depends on the requirement 'pydantic', which is not available here (reason: no_matching_version).",
                "params": {
                    "kind": MethodDependencyMissingKind.REQUIREMENT,
                    "name": "pydantic",
                    "reason": MethodDependencyMissingReason.NO_MATCHING_VERSION,
                },
                "location": {"file": _REQUIREMENTS_FILE, "line": 2},
            }
        ]
        # The caller's view: the operator's message, which names the sandbox, stays out of it.
        assert "diagnostics" not in body
        assert orchestrator.dispatches == []

    @pytest.mark.usefixtures("sandbox_hosted_mode")
    def test_a_run_whose_requirements_the_sandbox_does_not_meet_is_refused_before_dispatch(self, mocker: MockerFixture) -> None:
        orchestrator = _RecordingOrchestrator()
        client = _build_client(mocker, orchestrator=orchestrator, validator=_UnreachableValidator(), as_operator=True)

        files = {"main.mthds": _PIPE_FUNC_MTHDS, "funcs/pipe_func.py": _PIPE_FUNC_PY, _REQUIREMENTS_FILE: "pandas>=2\npandas>=3\npolars\n"}
        response = client.post("/v1/start", json={"files": files, "inputs": {"data": "1,2,3"}})

        assert response.status_code == 422, response.text
        body = response.json()
        assert body["code"] == CoreCode.METHOD_INVALID
        # One item per requirement not met, each on its line, naming the distribution that fails it and why.
        assert [(item["code"], item["params"], item["location"]) for item in body["errors"]] == [
            (
                CoreCode.METHOD_DEPENDENCY_MISSING,
                {"kind": "requirement", "name": "pandas", "reason": "no_matching_version"},
                {"file": _REQUIREMENTS_FILE, "line": 2},
            ),
            (
                CoreCode.METHOD_DEPENDENCY_MISSING,
                {"kind": "requirement", "name": "polars", "reason": "not_found"},
                {"file": _REQUIREMENTS_FILE, "line": 3},
            ),
        ]
        # The operator reads which requirement the sandbox refuses and why, and no directory of the runner.
        diagnostics = body["diagnostics"]
        assert diagnostics["error_class"] == "ValidateBundleError"
        assert diagnostics["causes"] == [{"error_class": "MethodRequirementsNotMetError", "code": CoreCode.METHOD_DEPENDENCY_MISSING}]
        assert diagnostics["message"] == (
            f"2 validation errors (first: The requirement 'pandas>=3' is not met by {_SANDBOX_ENVIRONMENT}: pandas 2.2.3 is there.)"
        )
        assert "rooted at" not in response.text
        assert orchestrator.dispatches == []

    @pytest.mark.usefixtures("sandbox_hosted_mode")
    def test_a_run_whose_requirements_the_deployment_refuses_carries_its_reason_before_dispatch(self, mocker: MockerFixture) -> None:
        orchestrator = _RecordingOrchestrator()
        client = _build_client(mocker, orchestrator=orchestrator, validator=_UnreachableValidator(), as_operator=True)

        files = {"main.mthds": _PIPE_FUNC_MTHDS, "funcs/pipe_func.py": _PIPE_FUNC_PY, _REQUIREMENTS_FILE: f"{_UNRESOLVABLE_REQUIREMENT}\n"}
        response = client.post("/v1/start", json={"files": files, "inputs": {"data": "1,2,3"}})

        assert response.status_code == 422, response.text
        body = response.json()
        assert body["code"] == CoreCode.METHOD_INVALID
        # The deployment's reason is about the requirements together, so its one item is on the file and no line.
        (item,) = body["errors"]
        assert item["code"] == CoreCode.METHOD_DEPENDENCY_MISSING
        assert item["params"] == {"kind": "requirement", "name": "pandas", "reason": "no_matching_version"}
        assert item["location"] == {"file": _REQUIREMENTS_FILE}
        # The deployment's own reason reaches the operator, with no directory of the runner.
        assert body["diagnostics"]["message"] == f"The requirements are refused by the Daytona sandbox: {_REFUSAL_REASON}"
        assert orchestrator.dispatches == []

    @pytest.mark.usefixtures("sandbox_hosted_mode")
    def test_a_run_whose_requirements_the_sandbox_meets_dispatches(self, mocker: MockerFixture) -> None:
        orchestrator = _RecordingOrchestrator()
        client = _build_client(mocker, orchestrator=orchestrator, validator=_UnreachableValidator())

        files = {"main.mthds": _PIPE_FUNC_MTHDS, "funcs/pipe_func.py": _PIPE_FUNC_PY, "requirements.txt": "# data\npandas>=2.2,<3\nopenpyxl\n"}
        response = client.post("/v1/start", json={"files": files, "inputs": {"data": "1,2,3"}})

        assert response.status_code in {200, 202}, response.text
        assert orchestrator.dispatches == ["crunch"]

    @pytest.mark.usefixtures("sandbox_hosted_mode")
    def test_a_refused_requirements_line_refuses_the_run(self, mocker: MockerFixture) -> None:
        orchestrator = _RecordingOrchestrator()
        client = _build_client(mocker, orchestrator=orchestrator, validator=_UnreachableValidator(), as_operator=True)

        files = {"main.mthds": _PIPE_FUNC_MTHDS, "funcs/pipe_func.py": _PIPE_FUNC_PY, _REQUIREMENTS_FILE: "-r base.txt\n"}
        response = client.post("/v1/start", json={"files": files, "inputs": {"data": "1,2,3"}})

        assert response.status_code == 422, response.text
        body = response.json()
        assert body["code"] == CoreCode.METHOD_INVALID
        assert body["errors"] == [
            {
                "code": CoreCode.METHOD_PACKAGE_INVALID,
                "detail": "The method's package breaks a package rule (reason: requirements_invalid).",
                "params": {"reason": "requirements_invalid", "path": _REQUIREMENTS_FILE},
                "location": {"file": _REQUIREMENTS_FILE, "line": 1},
            }
        ]
        assert body["diagnostics"]["causes"] == [{"error_class": "MethodRequirementsFileError", "code": CoreCode.METHOD_PACKAGE_INVALID}]
        assert "line 1 '-r base.txt'" in body["diagnostics"]["message"]
        assert orchestrator.dispatches == []

    @pytest.mark.usefixtures("sandbox_hosted_mode")
    @pytest.mark.parametrize(
        "requirements_text",
        [
            pytest.param(_UNMET_REQUIREMENTS_TEXT, id="requirement-not-met"),
            pytest.param("-r base.txt\n", id="line-the-standard-refuses"),
            pytest.param(f"{_UNRESOLVABLE_REQUIREMENT}\n", id="refused-by-the-deployment"),
        ],
    )
    def test_a_run_is_refused_with_the_items_of_the_validation_verdict(self, mocker: MockerFixture, requirements_text: str) -> None:
        """The run's refusal and the verdict on the same tree are the one translation of the requirements check: same items."""
        validator = _UnreachableValidator()
        client = _build_client(mocker, orchestrator=_RecordingOrchestrator(), validator=validator)
        files = {"main.mthds": _PIPE_FUNC_MTHDS, "funcs/pipe_func.py": _PIPE_FUNC_PY, _REQUIREMENTS_FILE: requirements_text}

        run_response = client.post("/v1/execute", json={"files": files, "inputs": {"data": "1,2,3"}})
        validate_response = client.post("/v1/validate", json={"files": files})

        assert run_response.status_code == 422, run_response.text
        assert validate_response.status_code == 200, validate_response.text
        verdict = validate_response.json()
        assert verdict["is_valid"] is False
        assert run_response.json()["errors"] == verdict["errors"]
        assert validator.calls == 0

    @pytest.mark.usefixtures("sandbox_hosted_mode")
    def test_a_validation_by_address_is_an_invalid_verdict_located_on_the_requirement(
        self, mocker: MockerFixture, install_method_package: Callable[..., Path]
    ) -> None:
        validator = _UnreachableValidator()
        client = _build_client(mocker, orchestrator=_RecordingOrchestrator(), validator=validator)
        install_method_package(files={"main.mthds": _PIPE_FUNC_MTHDS, "funcs/pipe_func.py": _PIPE_FUNC_PY, "requirements.txt": "pandas>=3\n"})

        response = client.post("/v1/validate", json={"method_ref": f"{STUB_METHOD_ADDRESS}@v0.1.0"})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is False
        (item,) = body["errors"]
        assert item["code"] == "method.dependency_missing"
        assert item["location"] == {"file": "requirements.txt", "line": 1}
        assert validator.calls == 0

    @pytest.mark.usefixtures("sandbox_hosted_mode")
    def test_a_validation_checks_the_method_off_the_event_loop(self, mocker: MockerFixture, install_method_package: Callable[..., Path]) -> None:
        """The check lists and hashes the method's files, so it runs in a worker thread, never on the loop serving requests."""
        threads_holding_a_loop: list[bool] = []

        def refuse_after_noting_the_thread(*, library_dirs: Sequence[Path], tree_listing: MethodTreeListing) -> None:  # noqa: ARG001
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                threads_holding_a_loop.append(False)
            else:
                threads_holding_a_loop.append(True)
            msg = "The method needs Python packages."
            raise MethodRequirementsNotMetError(msg, items=[]).with_params(
                kind=MethodDependencyMissingKind.REQUIREMENT, name="pandas", reason=MethodDependencyMissingReason.NOT_FOUND
            )

        mocker.patch(f"{_PIPELINE_NS}.ensure_served_method_requirements_met", side_effect=refuse_after_noting_the_thread)
        validator = _UnreachableValidator()
        client = _build_client(mocker, orchestrator=_RecordingOrchestrator(), validator=validator)
        install_method_package(files={"main.mthds": _PIPE_FUNC_MTHDS, "funcs/pipe_func.py": _PIPE_FUNC_PY, "requirements.txt": "pandas>=3\n"})

        response = client.post("/v1/validate", json={"method_ref": f"{STUB_METHOD_ADDRESS}@v0.1.0"})

        assert response.status_code == 200, response.text
        assert response.json()["is_valid"] is False
        assert threads_holding_a_loop == [False]
        assert validator.calls == 0

    def test_a_host_library_whose_requirements_are_not_met_is_the_deployments_fault(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """In the direct mode, a method of the runner's own library directories is judged against its interpreter, and its refusal is withheld."""
        host_library = tmp_path / "host-library"
        (host_library / "funcs").mkdir(parents=True)
        (host_library / "host.mthds").write_text('domain = "host_demo"\n', encoding="utf-8")
        (host_library / "funcs" / "helpers.py").write_text("VALUE = 1\n", encoding="utf-8")
        (host_library / "requirements.txt").write_text(f"{_ABSENT_PACKAGE}>=1\n", encoding="utf-8")
        mocker.patch.object(get_interpreter_hub(), "get_default_library_dirs", return_value=[host_library])
        orchestrator = _RecordingOrchestrator()
        client = _build_client(mocker, orchestrator=orchestrator, validator=_UnreachableValidator())

        response = client.post("/v1/start", json={"mthds_contents": [_PLAIN_MTHDS], "inputs": {"data": "hello"}})

        assert response.status_code == 500, response.text
        body = response.json()
        # The deployment's own configuration: the caller reads the operator domain and is told to report it.
        assert body["code"] == PipelexErrorCode.CONFIG_INVALID
        assert body["domain"] == "operator"
        assert body["next_step"]["kind"] == "report"
        # Withheld from the caller: nothing of the host's paths, interpreter or packages reaches its view.
        assert "diagnostics" not in body
        for host_detail in (str(tmp_path), sys.executable, _ABSENT_PACKAGE):
            assert host_detail not in response.text, host_detail
        assert orchestrator.dispatches == []
