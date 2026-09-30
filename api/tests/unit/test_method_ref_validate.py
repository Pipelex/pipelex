"""Route-level tests for `method_ref` on /validate — validate-by-address.

The clone cache is stubbed with a local directory tree (`install_method_package` in
conftest); validation itself runs for real, in-process. Pins the addressing design's Phase 2
delta: `/validate` accepts `method_ref` natively, resolved through the same fetch path as a
`method_ref` run, with the package's real file names feeding `mthds_sources` — and the
verdict discipline holds: a selector-resolution failure is a non-2xx `problem+json`, never
an `is_valid: false` verdict.
"""

from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.exception_handlers import register_exception_handlers
from api.routes import router as api_router
from tests.unit._constants import INVALID_MAIN_PIPE_MTHDS, STUB_METHOD_ADDRESS, VALID_MTHDS

_METHOD_REF = f"{STUB_METHOD_ADDRESS}@v0.1.0"


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(app)


class TestMethodRefValidate:
    def test_valid_package_returns_200_valid_arm_echoing_fetched_contents(self, install_method_package: Callable[..., Path]):
        install_method_package(files={"documents.mthds": VALID_MTHDS})
        client = _build_client()
        response = client.post("/v1/validate", json={"method_ref": _METHOD_REF})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is True
        # The echo carries what was actually validated: the fetched package's contents.
        assert body["mthds_contents"] == [VALID_MTHDS]
        assert "smoke.echo" in body["pipe_io_contracts"]

    def test_invalid_package_diagnostics_carry_the_real_file_names(self, install_method_package: Callable[..., Path]):
        install_method_package(files={"broken.mthds": INVALID_MAIN_PIPE_MTHDS})
        client = _build_client()
        response = client.post("/v1/validate", json={"method_ref": _METHOD_REF})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is False
        assert body["validation_errors"], "an invalid verdict must carry a non-empty validation_errors[]"
        # The package's real relative file name fed `mthds_sources`, so the diagnostic points
        # at the owning file rather than carrying a null source.
        assert body["validation_errors"][0]["source"] == "broken.mthds"

    def test_resolution_failure_is_non_2xx_problem_json_never_a_false_verdict(self, install_method_package: Callable[..., Path]):
        install_method_package(files={"documents.mthds": VALID_MTHDS})
        client = _build_client()
        response = client.post("/v1/validate", json={"method_ref": "github.com/pipelex/methods/nonexistent"})
        assert response.status_code == 404, response.text
        assert response.headers["content-type"] == "application/problem+json"
        body = response.json()
        assert body["error_type"] == "MethodPackageNotFoundError"
        # The verdict discipline: no verdict was produced, so nothing here says `is_valid`.
        assert "is_valid" not in body

    def test_method_ref_and_mthds_contents_are_a_422_xor_violation(self, install_method_package: Callable[..., Path]):
        install_method_package(files={"documents.mthds": VALID_MTHDS})
        client = _build_client()
        both = client.post("/v1/validate", json={"method_ref": _METHOD_REF, "mthds_contents": [VALID_MTHDS]})
        neither = client.post("/v1/validate", json={})
        for response in (both, neither):
            assert response.status_code == 422, response.text
            assert response.headers["content-type"] == "application/problem+json"
            assert "exactly one of" in response.json()["detail"]

    def test_mthds_sources_do_not_accompany_a_method_ref(self, install_method_package: Callable[..., Path]):
        install_method_package(files={"documents.mthds": VALID_MTHDS})
        client = _build_client()
        response = client.post("/v1/validate", json={"method_ref": _METHOD_REF, "mthds_sources": ["main.mthds"]})
        assert response.status_code == 422, response.text
        assert "package's own file names" in response.json()["detail"]
