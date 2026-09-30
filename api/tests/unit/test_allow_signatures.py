"""`allow_signatures` is sweep-mechanics, not a gate (D-B: signatures-as-data).

After the signatures-as-data reframe, an unimplemented `PipeSignature` is **never** a validation
error — it is a *runnability fact*. `allow_signatures` no longer gates acceptance; it only controls
whether signature pipes are mock-run during the dry-run sweep (and therefore listed in
`validated_pipes`). So a bundle containing a signature is accepted in BOTH modes on the two routes
that still run that sweep — `/validate` and `/build/runner`. On `/validate` the outstanding signature
surfaces as `pending_signatures` + `is_runnable: false` (a 200 `ValidReport`, since the verdict is
"sound but not runnable"), and the only mode difference is whether the signature pipe appears in
`validated_pipes`.

The static projections (`/build/{inputs,output}`) dropped the sweep entirely, so they no longer take
the flag at all — a signature bundle is simply accepted there, and that is asserted in
`test_build_routes_envelope.py`, not here.

(`SignaturesNotAllowedError` — the strict-mode rejection this module used to assert — was removed
with the de-raise; the build routes no longer reject a signature bundle.)
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.exception_handlers import register_exception_handlers
from api.routes import router as api_router
from tests.unit._constants import SIGNATURE_MTHDS


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(app)


class TestAllowSignatures:
    @pytest.mark.parametrize(
        ("path", "payload_base"),
        [
            ("/v1/validate", {"mthds_contents": [SIGNATURE_MTHDS]}),
            ("/v1/build/runner", {"files": [{"content": SIGNATURE_MTHDS}], "pipe_ref": "sig_api.caller_seq"}),
        ],
    )
    @pytest.mark.parametrize("allow_signatures", [False, True], ids=["strict", "lenient"])
    def test_signature_bundle_accepted_in_both_modes(self, path: str, payload_base: dict[str, object], allow_signatures: bool):
        # An unimplemented signature is never a rejection (D-B): both modes answer 200 on the two routes
        # that still sweep. Strict no longer differs from lenient on acceptance.
        client = _build_client()
        response = client.post(path, json={**payload_base, "allow_signatures": allow_signatures})
        assert response.status_code == 200, response.text

    @pytest.mark.parametrize("allow_signatures", [False, True], ids=["strict", "lenient"])
    def test_validate_reports_pending_signature_in_both_modes(self, allow_signatures: bool):
        # The verdict is "valid but not runnable" regardless of the flag: the outstanding signature
        # rides `pending_signatures` + `is_runnable: false` on a 200 `ValidReport` (is_valid: true).
        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [SIGNATURE_MTHDS], "allow_signatures": allow_signatures})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is True
        assert body["is_runnable"] is False
        assert body["pending_signatures"] == ["sig_api.summary_sig"]

    def test_allow_signatures_only_changes_validated_pipes_inclusion(self):
        # The single behavioral effect of the flag (D-B): the signature pipe is mock-run and listed in
        # `validated_pipes` only in lenient mode. The verdict (`pending_signatures`, `is_runnable`) is
        # identical either way — `allow_signatures` is sweep-mechanics, not a verdict knob.
        client = _build_client()
        strict = client.post("/v1/validate", json={"mthds_contents": [SIGNATURE_MTHDS]}).json()
        lenient = client.post("/v1/validate", json={"mthds_contents": [SIGNATURE_MTHDS], "allow_signatures": True}).json()

        strict_refs = {entry["pipe_ref"] for entry in strict["validated_pipes"]}
        lenient_refs = {entry["pipe_ref"] for entry in lenient["validated_pipes"]}
        assert strict_refs == {"sig_api.caller_seq"}
        assert lenient_refs == {"sig_api.caller_seq", "sig_api.summary_sig"}
        # The verdict is the same in both modes.
        assert strict["pending_signatures"] == lenient["pending_signatures"] == ["sig_api.summary_sig"]
        assert strict["is_runnable"] is False
        assert lenient["is_runnable"] is False

    def test_build_runner_generates_code_for_bundle_with_signatures_when_opted_in(self):
        # The most concrete proof the flag threads through to the runner build: with allow_signatures
        # the dry-run sweep mock-runs the signature, the library stays open, and runner code is
        # generated for the caller pipe.
        client = _build_client()
        response = client.post(
            "/v1/build/runner",
            json={"files": [{"content": SIGNATURE_MTHDS}], "pipe_ref": "sig_api.caller_seq", "allow_signatures": True},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is True
        assert body["pipe_ref"] == "sig_api.caller_seq"
        assert body["python_code"]
