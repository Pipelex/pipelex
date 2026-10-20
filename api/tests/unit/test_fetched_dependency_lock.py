"""A run checks a dependency the runner fetches on a miss against the `methods.lock` the calling method carries.

The calling method is sent as `files` or fetched by `method_ref`, its lock at the root of its tree. Its bundle calls the
invented probe package by address, which nothing ships and no store holds, so the runner fetches it on a miss, the fetch
mocked to a local copy of the package. The installed store is an empty temporary directory, and nothing reaches the
network.
"""

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from mthds.method_tree.lister import list_method_tree_at_root
from mthds.package.lock_file import LOCK_FILENAME
from mthds.package.manifest.parser import parse_methods_toml
from mthds.protocol.problem.registry import CoreCode
from pipelex.errors.security_event import SECURITY_EVENT_MESSAGE
from pipelex.methods.fetching import FetchedMethodPackage
from pipelex.methods.method_ref import parse_method_ref
from pytest_mock import MockerFixture, MockType

from pipelex_api.api_config import ApiConfig
from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.problem_view import mark_operator_request
from pipelex_api.routes import router as api_router
from tests.unit._constants import (
    STUB_METHOD_ADDRESS,
    UNRESOLVED_PACKAGE_MTHDS,
    VENDORED_PROBE_ADDRESS,
    VENDORED_PROBE_MANIFEST,
    VENDORED_PROBE_MARKER,
    VENDORED_PROBE_MTHDS,
)
from tests.unit._problems import assert_problem

_PIPELINE_NS = "pipelex_api.routes.pipelex.pipeline"
_METHOD_REF = f"{STUB_METHOD_ADDRESS}@v0.1.0"
_OTHER_DIGEST = "sha256:" + "0" * 64
_SECURITY_EVENT_LOGGER = "pipelex.errors.security_event"


def _lock_naming(*, address: str, digest: str) -> str:
    """A `methods.lock` holding one entry, for `address` at the probe's version with the tree digest `digest`."""
    return f'["{address}"]\nversion = "1.0.0"\ndigest  = "{digest}"\nsource  = "https://github.com/invented/probe-lib.git"\n'


def _mock_probe_fetch(*, mocker: MockerFixture, tmp_path: Path) -> tuple[MockType, str]:
    """Serve a fetch of the probe package from a local copy; return the mock and the copy's tree digest."""
    package_dir = tmp_path / "fetched-probe"
    package_dir.mkdir(parents=True)
    (package_dir / "METHODS.toml").write_text(VENDORED_PROBE_MANIFEST, encoding="utf-8")
    (package_dir / "probe.mthds").write_text(VENDORED_PROBE_MTHDS, encoding="utf-8")
    fetched = FetchedMethodPackage(
        ref=parse_method_ref(VENDORED_PROBE_ADDRESS),
        full_address=VENDORED_PROBE_ADDRESS,
        commit_sha="c" * 40,
        clone_dir=tmp_path,
        package_dir=package_dir,
        manifest=parse_methods_toml(VENDORED_PROBE_MANIFEST),
    )
    fetch_mock = mocker.patch("pipelex.methods.fetch_on_miss.fetch_method_package", return_value=fetched)
    return fetch_mock, list_method_tree_at_root(package_dir).digest


def _build_client(mocker: MockerFixture, *, tmp_path: Path, as_operator: bool = False) -> TestClient:
    """The routes behind the production handlers, with fetch-on-miss on; `as_operator` lets each request read `diagnostics`."""
    mocker.patch("pipelex.cli.installed_methods.GLOBAL_METHODS_DIR", tmp_path / "global-methods")
    mocker.patch("pipelex.cli.installed_methods.PROJECT_METHODS_DIR", tmp_path / "project-methods")
    mocker.patch("pipelex.methods.fetch_on_miss.is_method_fetch_on_miss_enabled", return_value=True)
    mocker.patch(
        f"{_PIPELINE_NS}.get_api_config", return_value=ApiConfig(orchestration_mode="direct", allow_request_orchestration_mode_override=False)
    )
    app = FastAPI()
    app.include_router(api_router, prefix="/v1", dependencies=[Depends(mark_operator_request)] if as_operator else [])
    register_exception_handlers(app)
    return TestClient(app)


def _execute_files(client: TestClient, *, lock: str | None) -> Any:
    files = {"bundle.mthds": UNRESOLVED_PACKAGE_MTHDS}
    if lock is not None:
        files[LOCK_FILENAME] = lock
    return client.post("/v1/execute", json={"files": files, "inputs": {"text": "hello"}})


class TestFetchedDependencyLock:
    @pytest.mark.parametrize("locks_the_fetched_tree", [True, False])
    def test_a_sent_tree_s_lock_checks_the_dependency_fetched_for_it(
        self, mocker: MockerFixture, tmp_path: Path, caplog: pytest.LogCaptureFixture, locks_the_fetched_tree: bool
    ):
        fetch_mock, digest = _mock_probe_fetch(mocker=mocker, tmp_path=tmp_path)
        client = _build_client(mocker, tmp_path=tmp_path, as_operator=True)
        locked_digest = digest if locks_the_fetched_tree else _OTHER_DIGEST

        with caplog.at_level(logging.WARNING, logger=_SECURITY_EVENT_LOGGER):
            response = _execute_files(client, lock=_lock_naming(address=VENDORED_PROBE_ADDRESS, digest=locked_digest))

        assert fetch_mock.call_count == 1
        events = [vars(record) for record in caplog.records if record.getMessage() == SECURITY_EVENT_MESSAGE]
        if locks_the_fetched_tree:
            assert response.status_code == 200, response.text
            assert f"{VENDORED_PROBE_MARKER}: hello" in json.dumps(response.json()["pipe_output"]["working_memory"])
            assert events == []
            return
        body = assert_problem(response, status=422, code=CoreCode.SECURITY_INTEGRITY_MISMATCH)
        assert body["domain"] == "method"
        assert body["params"] == {"dependency": VENDORED_PROBE_ADDRESS}
        # The operator reads the digest the lock records and the digest of the tree that was fetched.
        message = body["diagnostics"]["message"]
        assert _OTHER_DIGEST in message
        assert digest in message
        assert str(tmp_path) not in json.dumps(body)
        # The refusal is a security rule's, so the deployment logs its security event, once, naming the kind of target.
        (event,) = events
        assert event["error.code"] == CoreCode.SECURITY_INTEGRITY_MISMATCH
        assert event["security.target"] == "dependency"

    @pytest.mark.parametrize("locks_the_fetched_tree", [True, False])
    def test_validation_checks_the_dependency_fetched_for_a_sent_tree(self, mocker: MockerFixture, tmp_path: Path, locks_the_fetched_tree: bool):
        """A validation loads what a run loads, so a lock refusal is no verdict: the security refusal answers, as on a run."""
        _fetch_mock, digest = _mock_probe_fetch(mocker=mocker, tmp_path=tmp_path)
        client = _build_client(mocker, tmp_path=tmp_path)
        files = {
            "bundle.mthds": UNRESOLVED_PACKAGE_MTHDS,
            LOCK_FILENAME: _lock_naming(address=VENDORED_PROBE_ADDRESS, digest=digest if locks_the_fetched_tree else _OTHER_DIGEST),
        }

        response = client.post("/v1/validate", json={"files": files})

        if locks_the_fetched_tree:
            assert response.status_code == 200, response.text
            assert response.json()["is_valid"] is True
            return
        body = assert_problem(response, status=422, code=CoreCode.SECURITY_INTEGRITY_MISMATCH)
        assert body["params"] == {"dependency": VENDORED_PROBE_ADDRESS}

    def test_a_sent_tree_without_a_lock_runs_the_fetched_dependency(self, mocker: MockerFixture, tmp_path: Path):
        _mock_probe_fetch(mocker=mocker, tmp_path=tmp_path)
        client = _build_client(mocker, tmp_path=tmp_path)

        response = _execute_files(client, lock=None)

        assert response.status_code == 200, response.text

    def test_a_method_ref_package_s_lock_checks_the_dependency_fetched_for_it(
        self, mocker: MockerFixture, tmp_path: Path, install_method_package: Callable[..., Path]
    ):
        _mock_probe_fetch(mocker=mocker, tmp_path=tmp_path)
        install_method_package(
            files={"smoke.mthds": UNRESOLVED_PACKAGE_MTHDS, LOCK_FILENAME: _lock_naming(address=VENDORED_PROBE_ADDRESS, digest=_OTHER_DIGEST)}
        )
        client = _build_client(mocker, tmp_path=tmp_path)

        response = client.post("/v1/execute", json={"method_ref": _METHOD_REF, "inputs": {"text": "hello"}})

        body = assert_problem(response, status=422, code=CoreCode.SECURITY_INTEGRITY_MISMATCH)
        assert body["params"] == {"dependency": VENDORED_PROBE_ADDRESS}
        assert "diagnostics" not in body

    def test_a_lock_the_runner_cannot_read_refuses_the_fetched_dependency(self, mocker: MockerFixture, tmp_path: Path):
        """A lock written before tree digests records a `hash`: the method's own fault, refused as an invalid method."""
        _mock_probe_fetch(mocker=mocker, tmp_path=tmp_path)
        client = _build_client(mocker, tmp_path=tmp_path)

        response = _execute_files(client, lock=f'["{VENDORED_PROBE_ADDRESS}"]\nversion = "1.0.0"\nhash = "sha256:{"c" * 64}"\n')

        body = assert_problem(response, status=422, code=CoreCode.METHOD_INVALID)
        assert [(item["code"], item["params"]) for item in body["errors"]] == [
            (CoreCode.METHOD_PACKAGE_INVALID, {"reason": "lock_invalid", "path": LOCK_FILENAME})
        ], body
