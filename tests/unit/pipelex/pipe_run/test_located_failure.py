from __future__ import annotations

import pytest
from typing_extensions import override

from pipelex.base_exceptions import INTERNAL_ERROR_PLACEHOLDER, DisclosureMode, ErrorDomain, ErrorReport, PipelexError
from pipelex.cogt.exceptions import CogtError, InferenceErrorCategory
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.core.memory.absence import AbsenceKind, AbsenceRecord
from pipelex.core.pipes.inputs.exceptions import OptionalValueAbsentError
from pipelex.pipe_run.exceptions import PipeRouterError, find_failure_location
from pipelex.pipe_run.located_failure import compose_located_message, find_root_fault
from pipelex.pipeline.exceptions import PipelineExecutionError
from pipelex.runtime_bridge.exceptions import PipelexBridgeDispatchError
from pipelex.system.pipe_run_mode import PipeRunMode


class _RecoveredReportError(PipelexError):
    """Carries a report recovered across a transport boundary, and reports it as it is."""

    def __init__(self, message: str, *, error_report: ErrorReport):
        super().__init__(message)
        self.error_report = error_report

    @override
    def to_error_report(self) -> ErrorReport:
        return self.error_report


def _locate(failure: PipelexError, *, pipe_stack: list[str]) -> PipeRouterError:
    located = PipeRouterError.make_located(
        failure=failure,
        run_mode=PipeRunMode.LIVE,
        pipe_code=pipe_stack[-1],
        output_name=None,
        pipe_stack=pipe_stack,
    )
    located.__cause__ = failure
    return located


def _wrap_in_runner(failure: PipelexError, *, entry_pipe_code: str) -> PipelineExecutionError:
    wrapped = PipelineExecutionError.make_for_run_failure(
        failure=failure,
        run_mode=PipeRunMode.LIVE,
        entry_pipe_code=entry_pipe_code,
        output_name=None,
    )
    wrapped.__cause__ = failure
    return wrapped


def _make_absence_error() -> OptionalValueAbsentError:
    return OptionalValueAbsentError.make(
        run_mode=PipeRunMode.LIVE,
        pipe_code="force_echo",
        variable_name="clause",
        concept_ref="native.Text",
        absence_record=AbsenceRecord(variable_name="clause", kind=AbsenceKind.NOT_PROVIDED, reason="not provided by the caller"),
    )


class TestLocatedFailureReport:
    @pytest.mark.parametrize(
        ("pipe_stack", "expected_message"),
        [
            (["two_steps", "summarize"], "Pipe 'summarize' failed (two_steps → summarize): boom"),
            (["summarize"], "Pipe 'summarize' failed: boom"),
            ([], "boom"),
        ],
    )
    def test_compose_located_message(self, pipe_stack: list[str], expected_message: str) -> None:
        """A nested pipe names its path, an entry pipe does not, and an unknown location leaves the message alone."""
        assert compose_located_message(pipe_code="summarize", pipe_stack=pipe_stack, message="boom") == expected_message

    def test_identity_and_message_are_the_root_faults(self) -> None:
        """Through the router, a bridge and the runner, the report is the root fault's, located once."""
        root_fault = CogtError(message="rate limited", error_category=InferenceErrorCategory.TRANSIENT)
        located = _locate(root_fault, pipe_stack=["flow", "analyze", "gen_ideas"])
        bridge_error = PipelexBridgeDispatchError(f"Pipe execution failed in DIRECT mode for pipe 'flow': {located}")
        bridge_error.__cause__ = located
        run_failure = _wrap_in_runner(bridge_error, entry_pipe_code="flow")

        assert find_root_fault(error=run_failure) is root_fault
        assert find_failure_location(error=run_failure) is located
        assert run_failure.pipe_code == "gen_ideas"
        assert run_failure.pipe_stack == ["flow", "analyze", "gen_ideas"]

        report = run_failure.to_error_report()
        assert report.error_type == "CogtError"
        assert report.title == CogtError.title()
        assert report.type_uri == CogtError.type_uri()
        assert report.message == "Pipe 'gen_ideas' failed (flow → analyze → gen_ideas): rate limited"
        assert run_failure.message == report.message
        # Classification inherited from the chain, untouched by the floor.
        assert report.error_category == InferenceErrorCategory.TRANSIENT
        assert report.retryable is True
        assert report == located.to_error_report()

    def test_caller_facing_flag_is_the_root_faults(self) -> None:
        """A caller-facing root keeps its located message under STRICT; the wrapper grants nothing of its own."""
        report = _wrap_in_runner(
            _locate(_make_absence_error(), pipe_stack=["force_flow", "force_echo"]), entry_pipe_code="force_flow"
        ).to_error_report()

        assert report.caller_facing_message is True
        strict_payload = report.to_dict(disclosure_mode=DisclosureMode.STRICT)
        assert strict_payload["message"] == report.message
        assert strict_payload["message"].startswith("Pipe 'force_echo' failed (force_flow → force_echo): ")
        assert strict_payload["user_action"]["kind"] == UserActionKind.CHANGE_INPUT

    def test_a_bridge_sentence_is_never_caller_facing(self) -> None:
        """A bridge error with no PipelexError under it reports as itself, and stays redacted under STRICT."""
        bridge_error = PipelexBridgeDispatchError("Pipe execution failed in DIRECT mode for pipe 'flow': internal detail")
        report = _wrap_in_runner(bridge_error, entry_pipe_code="flow").to_error_report()

        assert report.error_type == "PipelexBridgeDispatchError"
        assert report.caller_facing_message is False
        assert report.to_dict(disclosure_mode=DisclosureMode.STRICT)["message"] == INTERNAL_ERROR_PLACEHOLDER

    def test_floor_and_fallback_apply_only_when_the_chain_is_silent(self) -> None:
        """No domain and no action on the chain: RUNTIME, and a fallback naming the failing pipe."""
        report = _locate(PipelexError("combine failed"), pipe_stack=["flow", "analyze"]).to_error_report()

        assert report.error_domain == ErrorDomain.RUNTIME
        assert report.user_action == UserAction(kind=UserActionKind.UNKNOWN, detail="The run failed in pipe 'analyze': the message gives the cause.")

    def test_a_categorized_action_is_kept(self) -> None:
        root_fault = CogtError(
            message="quota exceeded",
            error_category=InferenceErrorCategory.CAPACITY,
            user_action=UserAction(kind=UserActionKind.CHECK_BILLING, detail="Check your billing"),
        )
        report = _locate(root_fault, pipe_stack=["flow"]).to_error_report()

        assert report.user_action == UserAction(kind=UserActionKind.CHECK_BILLING, detail="Check your billing")

    def test_a_recovered_report_is_taken_as_it_is(self) -> None:
        """A report recovered across a boundary already names its pipe: the runner does not locate it again."""
        recovered_report = _locate(PipelexError("combine failed"), pipe_stack=["flow", "analyze"]).to_error_report()
        recovered = _RecoveredReportError(recovered_report.message, error_report=recovered_report)
        bridge_error = PipelexBridgeDispatchError(f"Pipe execution failed in temporal blocking delivery for pipe 'flow': {recovered}")
        bridge_error.__cause__ = recovered
        run_failure = _wrap_in_runner(bridge_error, entry_pipe_code="flow")

        assert run_failure.pipe_code == "flow"
        assert run_failure.pipe_stack == []
        assert run_failure.message == recovered_report.message
        assert run_failure.to_error_report() == recovered_report

    def test_a_recovered_leaf_report_is_located_by_the_router(self) -> None:
        """A PipelexError carrying a leaf's recovered report is located with the leaf's identity."""
        leaf_report = CogtError(message="model refused", error_category=InferenceErrorCategory.CONFIGURATION).to_error_report()
        report = _locate(_RecoveredReportError(leaf_report.message, error_report=leaf_report), pipe_stack=["flow", "summarize"]).to_error_report()

        assert report.error_type == "CogtError"
        assert report.message == "Pipe 'summarize' failed (flow → summarize): model refused"
        assert report.error_domain == ErrorDomain.CONFIG

    def test_a_cyclic_chain_reports_the_wrapper_as_itself(self) -> None:
        """A chain that loops back to the wrapper cannot make the report recurse."""
        root_fault = PipelexError("combine failed")
        located = _locate(root_fault, pipe_stack=["flow"])
        root_fault.__cause__ = located

        report = located.to_error_report()

        assert report.error_type == "PipeRouterError"
        assert report.message.endswith("combine failed")
