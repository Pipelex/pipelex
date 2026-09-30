"""`/validate` envelope contract — the canonical report + wire extras.

Phase 2 of the MTHDS Protocol surface alignment: `/validate` routes through
`ApiRunner.validate`, so the HTTP envelope is the canonical `PipelexValidationReport`
(`bundle_blueprint`, `pipe_io_contracts` keyed by namespaced `pipe_ref`, `validated_pipes`,
`pending_signatures` + `is_runnable`, best-effort `graph_spec`) plus this server's
wire-only extras (`mthds_contents` echo, `message`). The valid verdict carries `is_valid: true`
(the discriminant of the 200 response union — the `success` extra is retired). Validation runs
DIRECT in-process on the orchestrator-agnostic base (F2): the real in-process validation, with no
orchestrator-backend selection.

Includes the D2 regression pin: a bundle that declares no `main_pipe` validates with 200 and
`graph_spec=null` — the former 422 precondition is deleted.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pipelex.pipeline.bundle_validator import DryRunStatus

from api.exception_handlers import register_exception_handlers
from api.routes import router as api_router
from tests.unit._constants import NO_MAIN_PIPE_MTHDS, SIGNATURE_MTHDS, VALID_MTHDS


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(app)


class TestValidateEnvelope:
    def test_direct_success_envelope_is_canonical_report_plus_wire_extras(self):
        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [VALID_MTHDS]})
        assert response.status_code == 200, response.text
        body = response.json()

        # Canonical report (D1/D3/D7/D8): primary blueprint under `bundle_blueprint` —
        # the pipelex_-prefixed field and the old local `blueprint` dump are both gone.
        assert "pipelex_bundle_blueprint" not in body
        assert "blueprint" not in body
        assert body["bundle_blueprint"]["domain"] == "smoke"
        assert body["bundle_blueprint"]["main_pipe"] == "echo"

        # `pipe_io_contracts` keyed by namespaced pipe_ref with typed IO contracts.
        io_contract = body["pipe_io_contracts"]["smoke.echo"]
        assert io_contract["output"]["multiplicity"] == "single"
        assert io_contract["output"]["concept_ref"]
        assert "text" in io_contract["inputs"]
        assert io_contract["inputs"]["text"]["concept_ref"]

        # Per-pipe sweep outcomes, entries keyed `pipe_ref` (D7) — never `pipe_code`.
        assert body["validated_pipes"] == [{"pipe_ref": "smoke.echo", "status": DryRunStatus.SUCCESS}]

        # Runnability verdict + best-effort graph (main_pipe declared → graph produced).
        assert body["pending_signatures"] == []
        assert body["is_runnable"] is True
        assert body["graph_spec"] is not None

        # Wire extras the webapp depends on.
        assert body["mthds_contents"] == [VALID_MTHDS]
        assert body["is_valid"] is True
        assert body["message"]

    def test_direct_lenient_signatures_report_verdict(self):
        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [SIGNATURE_MTHDS], "allow_signatures": True})
        assert response.status_code == 200, response.text
        body = response.json()
        # The runnability verdict crosses the HTTP surface at last (F5 closed).
        assert body["pending_signatures"] == ["sig_api.summary_sig"]
        assert body["is_runnable"] is False
        # The signature placeholder is a first-class pipe on every artifact.
        assert set(body["pipe_io_contracts"]) == {"sig_api.caller_seq", "sig_api.summary_sig"}
        validated_refs = {entry["pipe_ref"] for entry in body["validated_pipes"]}
        assert validated_refs == {"sig_api.caller_seq", "sig_api.summary_sig"}

    def test_direct_no_main_pipe_returns_200_without_graph(self):
        # D2 regression pin (direct backend): this used to be a 422 route precondition.
        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [NO_MAIN_PIPE_MTHDS]})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["graph_spec"] is None
        assert body["bundle_blueprint"]["domain"] == "nomain"
        assert body["pipe_io_contracts"]["nomain.echo"]["output"]["multiplicity"] == "single"
        assert body["validated_pipes"] == [{"pipe_ref": "nomain.echo", "status": DryRunStatus.SUCCESS}]
        assert body["is_runnable"] is True
        assert body["is_valid"] is True
