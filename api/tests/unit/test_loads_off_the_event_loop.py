import asyncio
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mthds.protocol.problem.registry import CoreCode
from pipelex.config import get_config
from pipelex.methods.exceptions import MethodFetchError
from pipelex.methods.fetching import FetchedMethodPackage
from pipelex.methods.method_ref import MethodRef
from pipelex.plugins.pipe_func_package_offer_registry import (
    PipeFuncPackageOffer,
    PipeFuncPackageOfferRegistry,
    PipeFuncPackageOfferRequest,
    PipeFuncPackageRefusal,
)
from pytest_mock import MockerFixture

from pipelex_api.api_config import ApiConfig
from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.routes import router as api_router
from tests.unit._constants import VENDORED_PROBE_ADDRESS, VENDORED_PROBE_FILES

_PIPELINE_NS = "pipelex_api.routes.pipelex.pipeline"

_ECHO_MTHDS = """\
domain = "echo_demo"
main_pipe = "echo"

[pipe.echo]
type = "PipeCompose"
description = "Echo the data"
inputs = { data = "Text" }
output = "Text"
template = "$data"
"""

# A method whose tree holds Python and a requirements.txt, so its every load asks the package-offer factory.
_TREE_WITH_REQUIREMENTS = {
    "main.mthds": _ECHO_MTHDS,
    "helpers/constants.py": "ANSWER = 42\n",
    "requirements.txt": "pandas>=2\n",
}


def _runs_an_event_loop() -> bool:
    """Whether the calling thread is running an event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


class _RecordingOffer:
    """The package-offer factory of the neutral `sandbox` mode, noting, at each call, whether its thread runs an event loop."""

    def __init__(self) -> None:
        self.calls_on_a_loop: list[bool] = []

    def __call__(self, request: PipeFuncPackageOfferRequest) -> PipeFuncPackageOffer | PipeFuncPackageRefusal | None:  # noqa: ARG002
        self.calls_on_a_loop.append(_runs_an_event_loop())
        return PipeFuncPackageOffer(
            environment="the sandbox under test",
            distributions={"pandas": "2.2.3"},
            marker_environment={"python_version": "3.12", "sys_platform": "linux"},
        )


@pytest.fixture(name="recording_offer")
def recording_offer_fixture(mocker: MockerFixture) -> Generator[_RecordingOffer, None, None]:
    """Run PipeFunc steps in the neutral `sandbox` mode, whose plugin's factory records the thread of each call."""
    offer = _RecordingOffer()
    mocker.patch(
        "pipelex.libraries.package_environments.get_pipe_func_package_offer_registry", return_value=PipeFuncPackageOfferRegistry({"sandbox": offer})
    )
    pipe_func_config = get_config().interpreter.pipe_func
    previous = pipe_func_config.execution_mode
    pipe_func_config.execution_mode = "sandbox"
    try:
        yield offer
    finally:
        pipe_func_config.execution_mode = previous


def _build_client(mocker: MockerFixture, *, tmp_path: Path) -> TestClient:
    """The routes behind the production handlers, validating and running in-process, with no installed method to find."""
    mocker.patch("pipelex.cli.installed_methods.GLOBAL_METHODS_DIR", tmp_path / "global-methods")
    mocker.patch("pipelex.cli.installed_methods.PROJECT_METHODS_DIR", tmp_path / "project-methods")
    mocker.patch(
        f"{_PIPELINE_NS}.get_api_config", return_value=ApiConfig(orchestration_mode="direct", allow_request_orchestration_mode_override=False)
    )
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(app)


class TestLoadsOffTheEventLoop:
    def test_a_validation_asks_the_package_offer_off_the_event_loop(self, mocker: MockerFixture, tmp_path: Path, recording_offer: _RecordingOffer):
        """The runner's check of the served method asks the factory first, then the in-process validator's load does."""
        client = _build_client(mocker, tmp_path=tmp_path)

        response = client.post("/v1/validate", json={"files": _TREE_WITH_REQUIREMENTS})

        assert response.status_code == 200, response.text
        assert response.json()["is_valid"] is True, response.text
        assert len(recording_offer.calls_on_a_loop) > 1, recording_offer.calls_on_a_loop
        assert True not in recording_offer.calls_on_a_loop

    def test_a_run_asks_the_package_offer_off_the_event_loop(self, mocker: MockerFixture, tmp_path: Path, recording_offer: _RecordingOffer):
        """The runner's check of the served method asks the factory first, then the run's own load does."""
        client = _build_client(mocker, tmp_path=tmp_path)

        response = client.post("/v1/execute", json={"files": _TREE_WITH_REQUIREMENTS, "inputs": {"data": "hello"}})

        assert response.status_code == 200, response.text
        assert len(recording_offer.calls_on_a_loop) > 1, recording_offer.calls_on_a_loop
        assert True not in recording_offer.calls_on_a_loop

    def test_a_validation_fetches_an_unshipped_dependency_off_the_event_loop(self, mocker: MockerFixture, tmp_path: Path):
        """A tree calling a package nothing shipped resolves as its run would, by a fetch on a miss, in a worker thread."""
        client = _build_client(mocker, tmp_path=tmp_path)
        mocker.patch("pipelex.methods.fetch_on_miss.is_method_fetch_on_miss_enabled", return_value=True)
        fetches_on_a_loop: list[bool] = []

        def fail_the_fetch_after_noting_the_thread(*, ref: MethodRef, dest_dir: Path, refuse_structures: bool) -> FetchedMethodPackage:  # noqa: ARG001
            fetches_on_a_loop.append(_runs_an_event_loop())
            msg = "The clone failed."
            raise MethodFetchError(msg).for_method_ref(method_ref=ref.ref_str)

        mocker.patch("pipelex.methods.fetch_on_miss.fetch_method_package", side_effect=fail_the_fetch_after_noting_the_thread)
        files = {tree_path: content for tree_path, content in VENDORED_PROBE_FILES.items() if not tree_path.startswith(".mthds/")}

        response = client.post("/v1/validate", json={"files": files})

        assert response.status_code == 200, response.text
        verdict = response.json()
        assert verdict["is_valid"] is False, verdict
        assert [(item["code"], item["params"]["name"]) for item in verdict["errors"]] == [
            (CoreCode.METHOD_DEPENDENCY_MISSING, VENDORED_PROBE_ADDRESS)
        ], verdict
        assert fetches_on_a_loop == [False]
