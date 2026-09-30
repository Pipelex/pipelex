"""`/execute` dispatches by orchestration_mode through the OrchestratorRegistry (full synchronous output).

Pins the dispatch + output-mapping independent of any real backend, with a stub orchestrator: the
runner resolves the deployment's orchestration_mode, dispatches the locally-built PipeJob through the
orchestrator the registry holds for it with `DeliveryMode.BLOCKING`, and rehydrates the orchestrator's
JSON-safe output back into the full PipeOutput the `/execute` response wraps — exercising the real
serialize -> rehydrate round-trip (`serialize_completed_output` -> `hydrate_working_memory`), including
the `graph_spec` and `pipe_io_artifacts` `strict=False` re-validation branches. Also pins the policy-gated per-request override
(symmetric with `/start`), the no-orchestrator case (`MissingOrchestratorError`), and the request id reaching the job the
orchestrator is handed, which is the payload a Temporal worker deserializes and binds its log context from. The boot slot is
never used — every mode dispatches through the per-call registry. (Delivery is endpoint-set, never
requestable, so `/execute` has no fire-and-forget refusal — that axis is `/start`'s.)
"""

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mthds.protocol.input_form import PipeInputFormDescriptor, TextField
from mthds.protocol.output_form import PipeOutputFormDescriptor
from mthds.protocol.pipe_io_contracts import (
    IOMultiplicity,
    PipeInputContract,
    PipeIOContract,
    PipeOutputContract,
    PresenceMarker,
)
from pipelex.core.memory.working_memory import MAIN_STUFF_NAME
from pipelex.core.pipes.pipe_io_artifacts import PipeIOArtifacts
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.graph.graphspec import GraphSpec
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.plugins.orchestrator_registry import OrchestratorRegistry
from pipelex.runtime_bridge.exceptions import MissingOrchestratorError
from pipelex.runtime_bridge.payloads import PipelexPipeDispatchAck, PipelexPipeRunOutput
from pipelex.runtime_bridge.serialization import serialize_completed_output
from pytest_mock import MockerFixture

from pipelex_api.api_config import ApiConfig
from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.middleware import REQUEST_ID_HEADER, RequestIdMiddleware
from pipelex_api.routes import router as api_router
from pipelex_api.routes.pipelex.pipeline import ApiRunner
from tests.unit._constants import VALID_MTHDS

_PIPELINE_NS = "pipelex_api.routes.pipelex.pipeline"


class _StubOrchestrator:
    """A backend-agnostic stand-in orchestrator: echoes the job's working memory back as completed output.

    Returning via `serialize_completed_output` is the point — it produces the real JSON-safe
    `PipelexPipeRunOutput` (the same shape that crosses the Temporal worker boundary), so the route
    exercises the production serialize -> rehydrate round-trip instead of a hand-built payload. It
    records each dispatch so a test can assert `/execute` drove the blocking `execute` arm, and what the
    dispatched job's `RunMetadata` carries, since that is all a worker ever learns of the request. `start` (the
    fire-and-forget arm) is present only to satisfy the protocol — `/execute` never calls it.
    """

    def __init__(
        self,
        *,
        graph_spec: GraphSpec | None = None,
        pipe_io_artifacts: PipeIOArtifacts | None = None,
        pipe_io_artifacts_error: str | None = None,
        supports_fire_and_forget: bool = False,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self._graph_spec = graph_spec
        self._pipe_io_artifacts = pipe_io_artifacts
        self._pipe_io_artifacts_error = pipe_io_artifacts_error
        self.supports_fire_and_forget = supports_fire_and_forget

    async def execute(self, *, pipe_job: PipeJob, delivery_assignment: DeliveryAssignment | None) -> PipelexPipeRunOutput:
        self.calls.append(
            {
                "pipe_code": pipe_job.pipe.code,
                "delivery_assignment": delivery_assignment,
                "request_id": pipe_job.job_metadata.run_metadata.request_id,
            }
        )
        # A completed run always delivers a main stuff (pipelex invariant; enforced by
        # `resolve_main_stuff_root_key` in both `serialize_completed_output` and `from_pipe_output`).
        # This stub is an echo: promote the job's input stuff to the run's main stuff via the
        # `main_stuff` alias, so the serialize -> rehydrate round-trip yields a valid completed memory.
        working_memory = pipe_job.get_working_memory()
        working_memory.set_alias(alias=MAIN_STUFF_NAME, target=next(iter(working_memory.root)))
        return serialize_completed_output(
            pipe_output=PipeOutput(
                working_memory=working_memory,
                pipeline_run_id=pipe_job.job_metadata.run_metadata.pipeline_run_id,
                graph_spec=self._graph_spec,
                pipe_io_artifacts=self._pipe_io_artifacts,
                pipe_io_artifacts_error=self._pipe_io_artifacts_error,
            ),
            workflow_id=None,
        )

    async def start(self, *, pipe_job: PipeJob, delivery_assignment: DeliveryAssignment | None) -> PipelexPipeDispatchAck:
        msg = "/execute drives the blocking `execute` arm; `start` must not be reached."
        raise NotImplementedError(msg)


def _echo_pipe_io_artifacts() -> PipeIOArtifacts:
    """The I/O artifacts a run of the echo bundle would carry, keyed by its `pipe_ref`.

    Minimal but real: each of the carrier's members is the standard's own artifact type, so the
    dump the orchestrator produces is the shape a live run produces, not a stand-in dict.
    """
    return PipeIOArtifacts(
        pipe_io_contracts={
            "echo.echo": PipeIOContract(
                inputs={
                    "text": PipeInputContract(
                        concept_ref="native.Text",
                        presence=PresenceMarker.PLAIN,
                        multiplicity=IOMultiplicity.SINGLE,
                        item_count=None,
                        json_schema={"type": "string"},
                    )
                },
                output=PipeOutputContract(
                    concept_ref="native.Text",
                    multiplicity=IOMultiplicity.SINGLE,
                    item_count=None,
                    optional=False,
                    json_schema={"type": "string"},
                ),
            )
        },
        input_form={
            "echo.echo": PipeInputFormDescriptor(fields=[TextField(name="text", required=True, presence=PresenceMarker.PLAIN, gating=False)])
        },
        output_form={"echo.echo": PipeOutputFormDescriptor(field=TextField(name="result", required=True))},
    )


def _build_client(*, with_request_id_middleware: bool = False) -> TestClient:
    """Wire the real routes; `with_request_id_middleware` wraps the app the way `pipelex_api.main` does."""
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(RequestIdMiddleware(app) if with_request_id_middleware else app)


def _register_stub(mocker: MockerFixture, *, mode: str, stub: _StubOrchestrator) -> None:
    """Patch the orchestrator registry so the route's mode lookup finds `stub` for `mode`."""
    registry = OrchestratorRegistry({mode: stub})
    mocker.patch(f"{_PIPELINE_NS}.get_orchestrator_registry", return_value=registry)


def _force_config(mocker: MockerFixture, *, mode: str, allow_override: bool) -> None:
    """Patch the api config so `resolve_orchestration_mode` sees `mode` as the deployment default + policy."""
    config = ApiConfig(orchestration_mode=mode, allow_request_orchestration_mode_override=allow_override)
    mocker.patch(f"{_PIPELINE_NS}.get_api_config", return_value=config)


class TestExecuteDispatch:
    def test_direct_dispatch_returns_rehydrated_full_output(self, mocker: MockerFixture) -> None:
        """`direct` (the packaged default) dispatches through the registry and returns the full output."""
        stub = _StubOrchestrator()
        _register_stub(mocker, mode="direct", stub=stub)

        client = _build_client()
        response = client.post(
            "/v1/execute",
            json={"pipe_code": "echo", "mthds_contents": [VALID_MTHDS], "inputs": {"text": "hello"}},
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["state"] == "COMPLETED"
        # The full output survived the serialize -> rehydrate round-trip: the echo input is in the
        # rehydrated working memory the /execute response wraps.
        root = body["pipe_output"]["working_memory"]["root"]
        assert root["text"]["content"]["text"] == "hello"
        # The dispatch reached the registered orchestrator's blocking `execute` arm; /execute is
        # synchronous, so no delivery target (never the caller's to choose).
        assert len(stub.calls) == 1
        assert stub.calls[0]["delivery_assignment"] is None

    def test_graph_spec_survives_strict_false_rehydration(self, mocker: MockerFixture) -> None:
        """A non-None graph_spec round-trips through the helper's `strict=False` reverse of `model_dump(mode="json")`.

        Pins the most subtle line of `_pipe_output_from_run_output`: the orchestrator dumps `graph_spec`
        in JSON mode (so `GraphSpec.created_at`, a `strict=True` datetime, becomes an ISO string), and the
        helper must re-validate it with `strict=False` to restore the typed `GraphSpec`. Without the
        graph_spec branch exercised, a regression there (strict default, wrong key) would stay green.
        """
        graph_spec = GraphSpec(graph_id="g-1", created_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC))
        stub = _StubOrchestrator(graph_spec=graph_spec)
        _register_stub(mocker, mode="direct", stub=stub)

        client = _build_client()
        response = client.post(
            "/v1/execute",
            json={"pipe_code": "echo", "mthds_contents": [VALID_MTHDS], "inputs": {"text": "hello"}},
        )

        assert response.status_code == 200, response.text
        # The graph_spec survived the dump -> strict=False re-validation: it is present in the response.
        assert response.json()["pipe_output"]["graph_spec"]["graph_id"] == "g-1"

    def test_pipe_io_artifacts_survive_strict_false_rehydration(self, mocker: MockerFixture) -> None:
        """A non-None `pipe_io_artifacts` reaches the `/execute` response beside `graph_spec`.

        The rule the design ratified is "wherever the graph travels, its description travels with
        it": the runtime fills `pipe_io_artifacts_dump` on the SPI payload exactly as it fills
        `graph_spec_dump`, and this repo is the only reader that puts it back on the public wire.
        Pins the carrier under its own key, so a dropped or misnamed key cannot stay green while
        the OpenAPI artifact still advertises the field. The error slot is `null` here only
        because the build succeeded; what pins *that* key is the failed-build test below, since a
        `null` assertion alone is also satisfied by the field's own default.
        """
        stub = _StubOrchestrator(pipe_io_artifacts=_echo_pipe_io_artifacts())
        _register_stub(mocker, mode="direct", stub=stub)

        client = _build_client()
        response = client.post(
            "/v1/execute",
            json={"pipe_code": "echo", "mthds_contents": [VALID_MTHDS], "inputs": {"text": "hello"}},
        )

        assert response.status_code == 200, response.text
        pipe_output = response.json()["pipe_output"]
        artifacts = pipe_output["pipe_io_artifacts"]
        # All three members survived the dump -> strict=False re-validation, under the standard's names.
        assert artifacts["pipe_io_contracts"]["echo.echo"]["output"]["concept_ref"] == "native.Text"
        assert artifacts["input_form"]["echo.echo"]["fields"][0]["name"] == "text"
        assert artifacts["output_form"]["echo.echo"]["field"]["name"] == "result"
        # The error slot rides along, null when the build succeeded (a host must tell that apart
        # from "the build failed", exactly as it does for the graph).
        assert pipe_output["pipe_io_artifacts_error"] is None

    def test_pipe_io_artifacts_error_reaches_the_wire(self, mocker: MockerFixture) -> None:
        """A failed artifact build is reported on the wire, and does not cost the run its result.

        Upstream builds the artifacts best-effort in a `finally` ahead of delivery and swallows
        whatever the builders raise onto `pipe_io_artifacts_error`, so the only way a caller can
        tell "the build failed" from "no artifacts were requested" is that field arriving non-null
        beside a `null` carrier. This is what actually pins the key through the SPI round-trip:
        asserting it is `null` on a successful run would pass just as well if the route stopped
        mapping it altogether.
        """
        message = "Failed to build the I/O artifacts for pipeline_run_id=run-1: contract will not render"
        stub = _StubOrchestrator(pipe_io_artifacts_error=message)
        _register_stub(mocker, mode="direct", stub=stub)

        client = _build_client()
        response = client.post(
            "/v1/execute",
            json={"pipe_code": "echo", "mthds_contents": [VALID_MTHDS], "inputs": {"text": "hello"}},
        )

        assert response.status_code == 200, response.text
        pipe_output = response.json()["pipe_output"]
        assert pipe_output["pipe_io_artifacts_error"] == message
        # A failed description never invalidates the run: the carrier is null and the result stands.
        assert pipe_output["pipe_io_artifacts"] is None
        assert response.json()["state"] == "COMPLETED"

    def test_pipe_io_artifacts_absent_when_the_run_carried_none(self, mocker: MockerFixture) -> None:
        """A run that built no artifacts yields a null carrier, not a missing key or a fabricated empty one."""
        stub = _StubOrchestrator()
        _register_stub(mocker, mode="direct", stub=stub)

        client = _build_client()
        response = client.post(
            "/v1/execute",
            json={"pipe_code": "echo", "mthds_contents": [VALID_MTHDS], "inputs": {"text": "hello"}},
        )

        assert response.status_code == 200, response.text
        pipe_output = response.json()["pipe_output"]
        assert pipe_output["pipe_io_artifacts"] is None
        assert pipe_output["pipe_io_artifacts_error"] is None

    def test_per_request_override_honored_when_policy_allows(self, mocker: MockerFixture) -> None:
        """With override ON, a per-request orchestration_mode is resolved and dispatched (symmetric with /start)."""
        _force_config(mocker, mode="direct", allow_override=True)
        stub = _StubOrchestrator()
        _register_stub(mocker, mode="temporal", stub=stub)

        client = _build_client()
        response = client.post(
            "/v1/execute",
            json={
                "pipe_code": "echo",
                "mthds_contents": [VALID_MTHDS],
                "inputs": {"text": "hello"},
                "orchestration_mode": "temporal",
            },
        )

        assert response.status_code == 200, response.text
        # The requested (non-default) backend was honored: dispatch reached the temporal-keyed stub.
        assert len(stub.calls) == 1

    def test_forbidden_orchestration_mode_override_is_a_403(self) -> None:
        """The route threads orchestration_mode into the same override policy /start uses: a forbidden override is a 403."""
        client = _build_client()
        # Packaged default is `direct` with override OFF; forcing a different backend is refused before dispatch.
        response = client.post(
            "/v1/execute",
            json={
                "pipe_code": "echo",
                "mthds_contents": [VALID_MTHDS],
                "inputs": {"text": "hello"},
                "orchestration_mode": "temporal",
            },
        )

        assert response.status_code == 403, response.text
        assert response.headers["content-type"].startswith("application/problem+json")
        assert response.json()["error_type"] == "OrchestrationModeOverrideForbidden"

    def test_inbound_request_id_reaches_the_dispatched_job(self, mocker: MockerFixture) -> None:
        """On a `temporal` deployment, the inbound `X-Request-ID` rides the job the orchestrator is handed.

        A worker never sees the request: it binds its log context from the deserialized job's
        `RunMetadata.request_id`, and the middleware's in-process binding does not cross to it. So
        the proof is the payload, not the runner call — a route that passed the id to a runner which
        dropped it would still leave every worker line of the run without one.
        """
        _force_config(mocker, mode="temporal", allow_override=False)
        stub = _StubOrchestrator()
        _register_stub(mocker, mode="temporal", stub=stub)
        inbound_request_id = "01HNJZ4XR7K3Q9D8MWAQ7FY2E5"

        client = _build_client(with_request_id_middleware=True)
        response = client.post(
            "/v1/execute",
            json={"pipe_code": "echo", "mthds_contents": [VALID_MTHDS], "inputs": {"text": "hello"}},
            headers={REQUEST_ID_HEADER: inbound_request_id},
        )

        assert response.status_code == 200, response.text
        assert response.headers[REQUEST_ID_HEADER] == inbound_request_id
        assert len(stub.calls) == 1
        assert stub.calls[0]["request_id"] == inbound_request_id

    def test_minted_request_id_reaches_the_dispatched_job(self, mocker: MockerFixture) -> None:
        """Without an inbound header, the job carries the id the middleware minted, which the response echoes."""
        stub = _StubOrchestrator()
        _register_stub(mocker, mode="direct", stub=stub)

        client = _build_client(with_request_id_middleware=True)
        response = client.post(
            "/v1/execute",
            json={"pipe_code": "echo", "mthds_contents": [VALID_MTHDS], "inputs": {"text": "hello"}},
        )

        assert response.status_code == 200, response.text
        minted_request_id = response.headers[REQUEST_ID_HEADER]
        assert minted_request_id
        assert len(stub.calls) == 1
        assert stub.calls[0]["request_id"] == minted_request_id

    @pytest.mark.asyncio
    async def test_missing_orchestrator_for_resolved_mode_raises(self, mocker: MockerFixture) -> None:
        """A resolved mode with no registered orchestrator fails loud with MissingOrchestratorError."""
        mocker.patch(f"{_PIPELINE_NS}.get_orchestrator_registry", return_value=OrchestratorRegistry({}))

        with pytest.raises(MissingOrchestratorError) as exc_info:
            await ApiRunner().execute(
                pipe_code="echo",
                mthds_contents=[VALID_MTHDS],
                inputs={"text": "hello"},
            )
        # The packaged default is `direct`; the empty registry holds no orchestrator for it.
        assert exc_info.value.mode == "direct"
