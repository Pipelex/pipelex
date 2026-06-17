"""Mode-1 isolation tests for the dry-run+validation Temporal activity (``act_dry_validate``).

The whole ``/validate`` job — validation sweep **+** graph-producing dry-run — runs as ONE
in-process activity dispatched via the one-step wrapper workflow ``WfDryValidate``. A real worker
runs the wrapper-workflow→activity against the in-process Temporal server, and the tests pin the
Phase-3 contract (TODOS.md):

- the per-pipe status map and the ``GraphSpec`` are correct, in one round-trip;
- ZERO nested dispatch: the workflow history contains exactly one scheduled activity
  (``act_dry_validate``) and no child workflows (asserted at the Temporal-history level, per D6 —
  not on the ``WorkflowExecutor`` wrapper);
- tracing stays in memory: no NDJSON partition appears, ``make_event_log`` is never called;
- the graph is best-effort (D5): an expected dry-run failure yields ``graph_spec=None`` with
  validation still successful, while a non-Pipelex programming bug propagates and fails the run;
- a validation failure crosses back as a structured ``ErrorReport`` whose per-error
  ``validation_errors`` data survives the crossing (D3/T3);
- concurrent invocations don't cross-contaminate the scoped overrides.
"""

import asyncio
import uuid
from pathlib import Path

import pytest
from pytest_mock import MockerFixture
from temporalio.api.enums.v1 import EventType
from temporalio.client import Client as TemporalClient
from temporalio.client import WorkflowFailureError
from temporalio.common import RetryPolicy
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from pipelex.base_exceptions import ValidationErrorCategory
from pipelex.config import get_config
from pipelex.hub import clear_current_library, get_current_library_id_or_none, get_library_manager
from pipelex.pipe_run.exceptions import DryRunError
from pipelex.pipeline.bundle_validator import DryRunStatus
from pipelex.pipeline.exceptions import PipeIOContractError
from pipelex.pipeline.execution_seams import acquire_library
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.system.configuration.configs import NdjsonTracingConfig, TracingBackend
from pipelex.temporal.tprl.temporal_error import recover_error_report
from pipelex.temporal.tprl_pipe.act_dry_validate import DryValidateArg, DryValidateResult, act_dry_validate
from pipelex.temporal.tprl_pipe.wf_dry_validate import WfDryValidate
from tests.integration.pipelex.temporal.test_data import PipeParallelTemporalTestData

_PARALLEL_MAIN_PIPE_REF = f"{PipeParallelTemporalTestData.DOMAIN}.{PipeParallelTemporalTestData.PIPE_CODE}"

_ALPHA_MTHDS = """
domain = "dry_validate_alpha"
description = "Alpha bundle for act_dry_validate isolation tests"
main_pipe = "alpha_sequence"

[pipe.alpha_sequence]
type = "PipeSequence"
description = "Two-step alpha sequence"
inputs = { subject = "Text" }
output = "Text"
steps = [
  { pipe = "alpha_first", result = "first_take" },
  { pipe = "alpha_second", result = "second_take" },
]

[pipe.alpha_first]
type = "PipeLLM"
description = "First alpha step"
inputs = { subject = "Text" }
output = "Text"
prompt = "Describe $subject"

[pipe.alpha_second]
type = "PipeLLM"
description = "Second alpha step"
inputs = { first_take = "Text" }
output = "Text"
prompt = "Refine $first_take"
"""

_BETA_MTHDS = """
domain = "dry_validate_beta"
description = "Beta bundle for act_dry_validate isolation tests"
main_pipe = "beta_single"

[pipe.beta_single]
type = "PipeLLM"
description = "Single beta pipe"
inputs = { topic = "Text" }
output = "Text"
prompt = "Expand on $topic"
"""

_NO_MAIN_MTHDS = """
domain = "dry_validate_no_main"
description = "Bundle with no main_pipe, for the no-graph arm"

[pipe.lone_pipe]
type = "PipeLLM"
description = "Single pipe, no main_pipe declared"
inputs = { topic = "Text" }
output = "Text"
prompt = "Expand on $topic"
"""

_SIGNATURE_MTHDS = """
domain = "dry_validate_sig"
description = "Bundle carrying an unimplemented PipeSignature"
main_pipe = "sig_caller"

[pipe.sig_caller]
type = "PipeSequence"
description = "Sequence that reaches a signature"
inputs = { doc = "Text" }
output = "Text"
steps = [
  { pipe = "unimplemented_sig", result = "sig_result" },
]

[pipe.unimplemented_sig]
type = "PipeSignature"
description = "A contract-only placeholder"
inputs = { doc = "Text" }
output = "Text"
"""

_INVALID_MTHDS = """
domain = "dry_validate_invalid"
description = "Bundle with a real validation error: an invalid main_pipe code fails blueprint validation"
main_pipe = "Not A Valid Pipe Code!"

[concept.InvalidDoc]
description = "A document for the invalid-bundle test"
"""


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestDryValidateActivityInMemory:
    def _forbid_event_log_factory(self, mocker: MockerFixture) -> None:
        factory_error = AssertionError("make_event_log must not be called: act_dry_validate traces in memory only")
        mocker.patch("pipelex.pipeline.pipeline_run_setup.make_event_log", side_effect=factory_error)
        mocker.patch("pipelex.pipe_run.tracing_assembly.make_event_log", side_effect=factory_error)

    def _point_ndjson_tracing_at(self, mocker: MockerFixture, traces_dir: Path) -> None:
        cfg = get_config().pipelex.tracing_config
        mocker.patch.object(cfg, "is_enabled", True)
        mocker.patch.object(cfg, "backend", TracingBackend.NDJSON)
        mocker.patch.object(cfg, "ndjson", NdjsonTracingConfig(traces_dir=str(traces_dir)))

    async def _execute(
        self,
        temporal_client: TemporalClient,
        arg: DryValidateArg,
        *,
        workflow_id: str | None = None,
        task_queue: str | None = None,
    ) -> DryValidateResult:
        workflow_id = workflow_id or f"wf_dry_validate_{uuid.uuid4().hex[:8]}"
        task_queue = task_queue or f"q_dry_validate_{uuid.uuid4().hex[:8]}"
        async with Worker(
            temporal_client,
            task_queue=task_queue,
            workflows=[WfDryValidate],
            activities=[act_dry_validate],
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            return await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
                workflow=WfDryValidate.run,
                arg=arg,
                id=workflow_id,
                task_queue=task_queue,
                retry_policy=RetryPolicy(maximum_attempts=1),
            )

    async def test_status_map_and_graph_in_one_round_trip_zero_nested_dispatch(
        self, temporal_client: TemporalClient, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        traces_dir = tmp_path / "traces"
        traces_dir.mkdir()
        self._point_ndjson_tracing_at(mocker, traces_dir)
        self._forbid_event_log_factory(mocker)

        workflow_id = f"wf_dry_validate_{uuid.uuid4().hex[:8]}"
        mthds_content = Path(PipeParallelTemporalTestData.BUNDLE_FILE).read_text(encoding="utf-8")
        result = await self._execute(
            temporal_client,
            DryValidateArg(mthds_contents=[mthds_content], pipe_code=_PARALLEL_MAIN_PIPE_REF),
            workflow_id=workflow_id,
        )

        # Status map: every pipe in the bundle swept SUCCESS.
        for pipe_ref in PipeParallelTemporalTestData.EXPECTED_PIPE_REFS:
            assert result.dry_run_outputs[pipe_ref].status == DryRunStatus.SUCCESS

        # GraphSpec: non-empty, covering the whole controller topology.
        assert result.graph_spec is not None
        traced_pipe_codes = {node.pipe_code for node in result.graph_spec.nodes if node.pipe_code}
        expected_pipe_codes = {pipe_ref.split(".")[-1] for pipe_ref in PipeParallelTemporalTestData.EXPECTED_PIPE_REFS}
        assert expected_pipe_codes <= traced_pipe_codes

        # Zero nested dispatch, asserted on the Temporal history itself (D6): exactly one scheduled
        # activity — act_dry_validate — and no child workflows.
        history = await temporal_client.get_workflow_handle(workflow_id).fetch_history()
        scheduled_activities = [
            event.activity_task_scheduled_event_attributes.activity_type.name
            for event in history.events
            if event.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED
        ]
        assert scheduled_activities == ["act_dry_validate"]
        child_workflow_initiations = [
            event for event in history.events if event.event_type == EventType.EVENT_TYPE_START_CHILD_WORKFLOW_EXECUTION_INITIATED
        ]
        assert child_workflow_initiations == []

        # In-memory tracing: no NDJSON partition appeared (make_event_log was also forbidden above).
        assert list(traces_dir.iterdir()) == []

    async def test_main_pipe_auto_resolution_from_bundle(self, temporal_client: TemporalClient, mocker: MockerFixture) -> None:
        """Without an explicit pipe_code, the graph arm targets the bundle's declared main_pipe."""
        self._forbid_event_log_factory(mocker)

        result = await self._execute(temporal_client, DryValidateArg(mthds_contents=[_ALPHA_MTHDS]))

        assert result.dry_run_outputs["dry_validate_alpha.alpha_sequence"].status == DryRunStatus.SUCCESS
        assert result.graph_spec is not None
        traced_pipe_codes = {node.pipe_code for node in result.graph_spec.nodes if node.pipe_code}
        assert {"alpha_sequence", "alpha_first", "alpha_second"} <= traced_pipe_codes

        # D10: the worker-computed wire fields cross the boundary — pipe_io_contracts keyed by
        # namespaced pipe_ref with typed entries surviving (de)serialization, and a complete
        # bundle reporting nothing pending.
        assert result.pending_signatures == []
        assert set(result.pipe_io_contracts) == {
            "dry_validate_alpha.alpha_sequence",
            "dry_validate_alpha.alpha_first",
            "dry_validate_alpha.alpha_second",
        }
        sequence_contract = result.pipe_io_contracts["dry_validate_alpha.alpha_sequence"]
        assert sequence_contract.inputs["subject"].concept_ref == "native.Text"
        assert sequence_contract.output.concept_ref == "native.Text"

    async def test_graph_failure_is_best_effort(self, temporal_client: TemporalClient, mocker: MockerFixture) -> None:
        """D5: an expected dry-run failure in the graph arm yields graph_spec=None, validation still OK."""
        mocker.patch(
            "pipelex.pipe_run.dry_run_in_process.dry_run_pipe_in_process",
            side_effect=DryRunError("simulated graph dry-run failure"),
        )

        result = await self._execute(temporal_client, DryValidateArg(mthds_contents=[_ALPHA_MTHDS]))

        assert result.graph_spec is None
        assert result.dry_run_outputs["dry_validate_alpha.alpha_sequence"].status == DryRunStatus.SUCCESS

    async def test_graph_bug_propagates(self, temporal_client: TemporalClient, mocker: MockerFixture) -> None:
        """D5 (bug-propagates arm): a non-Pipelex programming bug in the graph arm fails the run."""
        mocker.patch(
            "pipelex.pipe_run.dry_run_in_process.dry_run_pipe_in_process",
            side_effect=KeyError("simulated programming bug"),
        )

        with pytest.raises(WorkflowFailureError):
            await self._execute(temporal_client, DryValidateArg(mthds_contents=[_ALPHA_MTHDS]))

    async def test_validation_failure_crosses_as_structured_error_report(self, temporal_client: TemporalClient) -> None:
        """D3/T3: a genuine validation failure raises, and the structured per-error ``validation_errors``
        data survives the ErrorReport crossing (it must not degrade to a plain message).

        Signatures are never an error (D-B), so the trigger is a real validation fault — an invalid
        ``main_pipe`` code that fails blueprint validation. The sweep goes through ``validate_bundle``'s
        cascade, so the crossing report carries the SAME identity the direct-mode route's body carries —
        ``ValidateBundleError``, ``error_domain=input`` — with the per-error items in
        ``validation_errors`` (the API ``InvalidReport`` is built from exactly these ErrorReport fields).
        """
        with pytest.raises(WorkflowFailureError) as exc_info:
            await self._execute(temporal_client, DryValidateArg(mthds_contents=[_INVALID_MTHDS]))

        error_report = recover_error_report(exc_info.value)
        assert error_report.error_type == "ValidateBundleError"
        assert error_report.error_domain == "input"
        # The structured per-error data survives the crossing (not a bare message).
        assert error_report.validation_errors is not None
        assert any(item.category == ValidationErrorCategory.BLUEPRINT_VALIDATION for item in error_report.validation_errors)

    async def test_signatures_allowed_in_lenient_mode(self, temporal_client: TemporalClient) -> None:
        """The same signature bundle validates in lenient mode (allow_signatures=True), and the
        runnability verdict's input crosses the boundary (D10/F5): the unsatisfied header is
        reported in pending_signatures, with a structures entry like any concrete pipe.
        """
        result = await self._execute(temporal_client, DryValidateArg(mthds_contents=[_SIGNATURE_MTHDS], allow_signatures=True))

        assert result.dry_run_outputs["dry_validate_sig.sig_caller"].status == DryRunStatus.SUCCESS
        assert result.graph_spec is not None
        assert result.pending_signatures == ["dry_validate_sig.unimplemented_sig"]
        assert "dry_validate_sig.unimplemented_sig" in result.pipe_io_contracts
        assert result.pipe_io_contracts["dry_validate_sig.unimplemented_sig"].output.concept_ref == "native.Text"

    async def test_validation_failure_does_not_retry_activity(self, temporal_client: TemporalClient, mocker: MockerFixture) -> None:
        """D-C5 regression: a deterministic validation failure must run the activity exactly once.
        ValidateBundleError is non-retryable at the activity tier via a string match on the
        ApplicationError type name — if that match drifts (class rename, boundary change), the
        whole sweep silently re-runs and only this assertion catches it.
        """
        sweep_spy = mocker.patch(
            "pipelex.temporal.tprl_pipe.act_dry_validate.validate_bundle",
            wraps=validate_bundle,
        )
        with pytest.raises(WorkflowFailureError):
            await self._execute(temporal_client, DryValidateArg(mthds_contents=[_INVALID_MTHDS]))
        assert sweep_spy.call_count == 1

    async def test_pipe_io_contracts_failure_does_not_retry_activity(self, temporal_client: TemporalClient, mocker: MockerFixture) -> None:
        """PipeIOContractError is non-retryable at the workflow tier, like ValidateBundleError —
        a deterministic schema-render failure must run the activity exactly once. Pins the
        string match on the ApplicationError type name in wf_dry_validate's retry policy: if
        the class is renamed without updating the policy, the sweep silently re-runs and only
        this assertion catches it.
        """
        io_contracts_mock = mocker.patch(
            "pipelex.temporal.tprl_pipe.act_dry_validate.build_pipe_io_contracts",
            side_effect=PipeIOContractError(message="simulated schema render failure"),
        )
        with pytest.raises(WorkflowFailureError):
            await self._execute(temporal_client, DryValidateArg(mthds_contents=[_ALPHA_MTHDS]))
        assert io_contracts_mock.call_count == 1

    async def test_no_main_pipe_and_no_pipe_code_yields_no_graph(self, temporal_client: TemporalClient) -> None:
        """Without a declared main_pipe and without an explicit pipe_code, the graph arm is
        skipped: validation succeeds with graph_spec=None.
        """
        result = await self._execute(temporal_client, DryValidateArg(mthds_contents=[_NO_MAIN_MTHDS]))

        assert result.dry_run_outputs["dry_validate_no_main.lone_pipe"].status == DryRunStatus.SUCCESS
        assert result.graph_spec is None

    async def test_unknown_explicit_pipe_code_degrades_to_no_graph(self, temporal_client: TemporalClient) -> None:
        """Graph-arm parity: an unknown explicit pipe_code is a graph-arm domain failure
        (PipeNotFoundError, a PipelexError) and degrades to graph_spec=None with validation
        still successful — the same answer the direct route gives, never a failed request.
        """
        result = await self._execute(temporal_client, DryValidateArg(mthds_contents=[_ALPHA_MTHDS], pipe_code="dry_validate_alpha.does_not_exist"))

        assert result.graph_spec is None
        assert result.dry_run_outputs["dry_validate_alpha.alpha_sequence"].status == DryRunStatus.SUCCESS

    async def test_direct_call_restores_outer_current_library(self) -> None:
        """The activity's finally restores the caller's outer current-library (the
        prev != validated arm) after tearing the validated library down. Exercised by calling
        the activity directly — through a worker, the activity runs in its own copied context
        and the test task could not observe the ContextVar restore.
        """
        outer_library_id = "outer_lib_dry_validate"
        acquire_library(library_id=outer_library_id, mthds_contents=[_BETA_MTHDS])
        try:
            result = await act_dry_validate(DryValidateArg(mthds_contents=[_ALPHA_MTHDS]))

            assert result.graph_spec is not None
            assert get_current_library_id_or_none() == outer_library_id
        finally:
            get_library_manager().teardown(library_id=outer_library_id)
            clear_current_library()

    async def test_concurrent_invocations_do_not_cross_contaminate(self, temporal_client: TemporalClient, mocker: MockerFixture) -> None:
        """Two concurrent dispatches return distinct GraphSpecs with no shared/merged trace events."""
        self._forbid_event_log_factory(mocker)

        result_alpha, result_beta = await asyncio.gather(
            self._execute(temporal_client, DryValidateArg(mthds_contents=[_ALPHA_MTHDS])),
            self._execute(temporal_client, DryValidateArg(mthds_contents=[_BETA_MTHDS])),
        )

        assert result_alpha.graph_spec is not None
        assert result_beta.graph_spec is not None
        assert result_alpha.graph_spec.graph_id != result_beta.graph_spec.graph_id
        alpha_codes = {node.pipe_code for node in result_alpha.graph_spec.nodes if node.pipe_code}
        beta_codes = {node.pipe_code for node in result_beta.graph_spec.nodes if node.pipe_code}
        assert "alpha_sequence" in alpha_codes
        assert "beta_single" not in alpha_codes
        assert "beta_single" in beta_codes
        assert "alpha_sequence" not in beta_codes
        assert "dry_validate_beta.beta_single" not in result_alpha.dry_run_outputs
        assert "dry_validate_alpha.alpha_sequence" not in result_beta.dry_run_outputs
