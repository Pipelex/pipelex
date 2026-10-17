from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from mthds.protocol.problem.registry import CoreCode, StepKind
from typing_extensions import override

from pipelex.base_exceptions import PipelexError
from pipelex.cogt.exceptions import CogtError, InferenceErrorCategory, LLMCompletionError, ModelChoiceNotFoundError
from pipelex.cogt.inference.error_classification import ProviderErrorMetadata
from pipelex.cogt.inference.provider_name import ProviderName
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.core.memory.absence import AbsenceKind, AbsenceRecord
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.core.pipes.inputs.exceptions import OptionalValueAbsentError
from pipelex.errors.error_codes import error_code_spec
from pipelex.errors.problem import PipelexProblem, ProblemView, caller_view_of, merge_locations
from pipelex.pipe_run.exceptions import PipeRouterError, find_failure_location
from pipelex.pipe_run.located_failure import compose_located_message, find_foreign_fault, find_root_fault, make_unexpected_failure
from pipelex.pipeline.exceptions import PipelineExecutionError
from pipelex.runtime_bridge.exceptions import PipelexBridgeDispatchError
from pipelex.system.pipe_run_mode import PipeRunMode

if TYPE_CHECKING:
    from mthds.protocol.problem.models import ProblemLocation


class _RecoveredProblemError(PipelexError):
    """Carries a problem recovered across a transport boundary, and reports it as it is, located where it is told."""

    def __init__(self, message: str, *, problem: PipelexProblem):
        super().__init__(message)
        self.recovered_problem = problem

    @override
    def to_problem(
        self,
        *,
        view: ProblemView,
        request_id: str | None = None,
        pipeline_run_id: str | None = None,
        failure_location: ProblemLocation | None = None,
    ) -> PipelexProblem:
        problem = self.recovered_problem
        if failure_location is not None:
            problem = problem.model_copy(update={"location": merge_locations(base=problem.location, override=failure_location)})
        match view:
            case ProblemView.OPERATOR:
                return problem
            case ProblemView.CALLER:
                return caller_view_of(problem=problem)


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


class TestLocatedFailureProblem:
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

    def test_foreign_fault_is_found_only_behind_a_stand_in(self) -> None:
        """The foreign exception a located PipelexUnexpectedError stands in for is found; a Pipelex root fault has none."""
        foreign_fault = KeyError("boom")
        located_foreign = _locate(make_unexpected_failure(error=foreign_fault), pipe_stack=["flow", "analyze"])
        located_pipelex = _locate(PipelexError("combine failed"), pipe_stack=["flow", "analyze"])

        assert find_foreign_fault(error=_wrap_in_runner(located_foreign, entry_pipe_code="flow")) is foreign_fault
        assert find_foreign_fault(error=located_pipelex) is None

    def test_a_foreign_exception_ends_the_walk(self) -> None:
        """A foreign exception raised from an older PipelexError: its stand-in is the root fault, not the older error."""
        older_error = PipelexError("older failure")
        foreign_fault = KeyError("boom")
        foreign_fault.__cause__ = older_error
        unexpected_failure = make_unexpected_failure(error=foreign_fault)
        located = _locate(unexpected_failure, pipe_stack=["flow"])

        assert find_root_fault(error=located) is unexpected_failure
        assert find_foreign_fault(error=located) is foreign_fault
        problem = located.to_problem(view=ProblemView.OPERATOR)
        assert problem.code == CoreCode.RUNTIME_UNEXPECTED
        assert problem.diagnostics is not None
        assert problem.diagnostics.error_class == "PipelexUnexpectedError"
        assert "boom" not in str(located.to_problem(view=ProblemView.CALLER).to_wire())

    def test_a_same_class_rethrow_keeps_its_added_context(self) -> None:
        """An error raised from one of its own class restates the fault with context: the outer one is reported."""
        low_level = CogtError(message="size out of range", error_category=InferenceErrorCategory.CONTENT)
        with_remedy = CogtError(message="Size tier '4k' is not satisfiable: use '1k' or '2k'", error_category=InferenceErrorCategory.CONTENT)
        with_remedy.__cause__ = low_level
        located = _locate(with_remedy, pipe_stack=["flow", "draw"])

        assert find_root_fault(error=located) is with_remedy
        assert located.message == "Pipe 'draw' failed (flow → draw): Size tier '4k' is not satisfiable: use '1k' or '2k'"
        problem = located.to_problem(view=ProblemView.OPERATOR)
        assert problem.diagnostics is not None
        assert problem.diagnostics.message == "Size tier '4k' is not satisfiable: use '1k' or '2k'"

    def test_the_problem_is_the_root_faults_located_at_the_failing_pipe(self) -> None:
        """Through the router, a bridge and the runner, the problem is the root fault's, located once at the innermost pipe."""
        root_fault = LLMCompletionError(message="rate limited", error_category=InferenceErrorCategory.TRANSIENT).with_error_code(
            CoreCode.PROVIDER_RATE_LIMITED
        )
        located = _locate(root_fault, pipe_stack=["flow", "analyze", "gen_ideas"])
        bridge_error = PipelexBridgeDispatchError(f"Pipe execution failed in DIRECT mode for pipe 'flow': {located}")
        bridge_error.__cause__ = located
        run_failure = _wrap_in_runner(bridge_error, entry_pipe_code="flow")

        assert find_root_fault(error=run_failure) is root_fault
        assert find_failure_location(error=run_failure) is located
        assert run_failure.pipe_code == "gen_ideas"
        assert run_failure.pipe_stack == ["flow", "analyze", "gen_ideas"]
        assert run_failure.message == "Pipe 'gen_ideas' failed (flow → analyze → gen_ideas): rate limited"

        for view in ProblemView:
            problem = run_failure.to_problem(view=view, pipeline_run_id="run-1")
            root_spec = error_code_spec(CoreCode.PROVIDER_RATE_LIMITED)
            assert problem.code == root_spec.code
            assert problem.title == root_spec.title
            assert problem.type == root_spec.type_uri
            assert problem.is_retryable is True
            assert problem.location is not None
            assert problem.location.pipe == "gen_ideas"
            assert problem.location.path == ["flow", "analyze", "gen_ideas"]
            assert problem.pipeline_run_id == "run-1"
            assert problem.to_wire() == located.to_problem(view=view, pipeline_run_id="run-1").to_wire()
        operator = run_failure.to_problem(view=ProblemView.OPERATOR)
        assert operator.diagnostics is not None
        assert operator.diagnostics.error_class == "LLMCompletionError"
        assert operator.diagnostics.message == "rate limited"

    def test_the_location_names_the_pipe_and_its_path_in_the_caller_view(self) -> None:
        """The caller reads where its run failed as members, never only inside the detail: they are its own pipe codes."""
        run_failure = _wrap_in_runner(_locate(_make_absence_error(), pipe_stack=["force_flow", "force_echo"]), entry_pipe_code="force_flow")

        caller = run_failure.to_problem(view=ProblemView.CALLER)

        assert caller.code == CoreCode.PIPE_FORCED_INPUT_ABSENT
        assert caller.location is not None
        assert caller.location.as_wire() == {"pipe": "force_echo", "path": ["force_flow", "force_echo"]}
        assert caller.params is not None
        assert caller.params.as_wire() == {"pipe": "force_echo", "variable": "clause"}
        assert caller.detail == "Pipe 'force_echo' forces 'clause' with '!', and it was absent in this run."
        assert caller.next_step.kind == StepKind.CHANGE_METHOD
        assert caller.diagnostics is None

    def test_an_entry_pipe_failure_has_no_location(self) -> None:
        """A failure no router located has no path, so its problem holds no location rather than an empty one."""
        run_failure = _wrap_in_runner(PipelexError("combine failed"), entry_pipe_code="flow")

        problem = run_failure.to_problem(view=ProblemView.CALLER)

        assert problem.location is None
        assert "location" not in problem.to_wire()

    def test_a_bridge_sentence_never_reaches_the_caller(self) -> None:
        """A bridge error with no PipelexError under it reports as itself, its sentence the operator's alone."""
        bridge_error = PipelexBridgeDispatchError("Pipe execution failed in DIRECT mode for pipe 'flow': internal detail")
        run_failure = _wrap_in_runner(bridge_error, entry_pipe_code="flow")

        caller = run_failure.to_problem(view=ProblemView.CALLER)
        operator = run_failure.to_problem(view=ProblemView.OPERATOR)

        assert "internal detail" not in str(caller.to_wire())
        assert operator.diagnostics is not None
        assert operator.diagnostics.error_class == "PipelexBridgeDispatchError"

    def test_a_recovered_problem_is_taken_as_it_is(self) -> None:
        """A problem recovered across a boundary already names its pipe: the runner does not locate it again."""
        recovered_problem = _locate(PipelexError("combine failed"), pipe_stack=["flow", "analyze"]).to_problem(view=ProblemView.OPERATOR)
        recovered = _RecoveredProblemError("combine failed", problem=recovered_problem)
        bridge_error = PipelexBridgeDispatchError(f"Pipe execution failed in temporal blocking delivery for pipe 'flow': {recovered}")
        bridge_error.__cause__ = recovered
        run_failure = _wrap_in_runner(bridge_error, entry_pipe_code="flow")

        assert run_failure.pipe_code == "flow"
        assert run_failure.pipe_stack == []
        assert run_failure.to_problem(view=ProblemView.OPERATOR).to_wire() == recovered_problem.to_wire()
        assert run_failure.to_problem(view=ProblemView.CALLER).to_wire() == caller_view_of(problem=recovered_problem).to_wire()

    def test_a_recovered_leaf_problem_is_located_by_the_router(self) -> None:
        """A PipelexError carrying a leaf's recovered problem is located with the leaf's identity."""
        leaf_problem = CogtError(message="model refused", error_category=InferenceErrorCategory.CONFIGURATION).to_problem(view=ProblemView.OPERATOR)
        located = _locate(_RecoveredProblemError("model refused", problem=leaf_problem), pipe_stack=["flow", "summarize"])

        problem = located.to_problem(view=ProblemView.OPERATOR)

        assert problem.code == leaf_problem.code
        assert problem.domain == leaf_problem.domain
        assert problem.diagnostics == leaf_problem.diagnostics
        assert problem.location is not None
        assert problem.location.as_wire() == {"pipe": "summarize", "path": ["flow", "summarize"]}

    def test_a_wrapper_attributing_its_coded_cause_reaches_the_run_problem(self) -> None:
        """A worker fills the model and the backend on a wrapper that takes its cause's code: the run's problem names both."""
        provider_refusal = LLMCompletionError(
            message="429 from the provider",
            error_category=InferenceErrorCategory.TRANSIENT,
            provider_metadata=ProviderErrorMetadata(
                provider=ProviderName.OPENAI, sdk_exception_type="RateLimitError", status_code=429, retry_after_seconds=7.0, request_id="req_abc"
            ),
        ).with_error_code(CoreCode.PROVIDER_RATE_LIMITED)
        attributed = LLMCompletionError(message="the completion failed")
        attributed.__cause__ = provider_refusal
        attributed.fill_model_and_provider("gpt-4o-mini", backend_name="openai")
        run_failure = _wrap_in_runner(_locate(attributed, pipe_stack=["flow", "summarize"]), entry_pipe_code="flow")

        operator = run_failure.to_problem(view=ProblemView.OPERATOR)
        caller = run_failure.to_problem(view=ProblemView.CALLER)

        assert operator.code == CoreCode.PROVIDER_RATE_LIMITED
        assert operator.diagnostics is not None
        assert operator.diagnostics.error_class == "LLMCompletionError"
        assert operator.diagnostics.message == "429 from the provider"
        assert operator.diagnostics.model == "gpt-4o-mini"
        assert operator.diagnostics.provider is not None
        # The wrapper names the backend, and the cause keeps what the provider answered.
        assert operator.diagnostics.provider.name == "openai"
        assert operator.diagnostics.provider.status == 429
        assert operator.diagnostics.provider.request_id == "req_abc"
        assert operator.retry_after == 7.0
        assert caller.detail == "The provider 'openai' is rate limiting this deployment's calls to the model 'gpt-4o-mini'."
        assert caller.retry_after == 7.0

    def test_a_wrapper_locating_its_coded_cause_keeps_its_location(self) -> None:
        """A pipe's refusal of an unknown model is located on the pipe, the field and the file, run or no run."""
        deck_refusal = ModelChoiceNotFoundError("no model 'gpt-9' in the deck", model_type=ModelType.LLM, model_choice="gpt-9")
        located_refusal = PipeOperatorModelChoiceError.make_from_model_choice_not_found(
            model_choice_error=deck_refusal, pipe_type="PipeLLM", pipe_code="summarize", domain_code="docs", field_name="model"
        )
        located_refusal.source = "docs.mthds"
        located_refusal.__cause__ = deck_refusal

        problem = located_refusal.to_problem(view=ProblemView.CALLER)
        assert problem.code == CoreCode.MODEL_UNKNOWN
        assert problem.location is not None
        assert problem.location.as_wire() == {"pipe": "summarize", "field": "model", "file": "docs.mthds"}

        run_problem = _wrap_in_runner(_locate(located_refusal, pipe_stack=["flow", "summarize"]), entry_pipe_code="flow").to_problem(
            view=ProblemView.CALLER
        )
        assert run_problem.location is not None
        assert run_problem.location.as_wire() == {"pipe": "summarize", "path": ["flow", "summarize"], "field": "model", "file": "docs.mthds"}

    def test_a_cyclic_chain_reports_the_wrapper_as_itself(self) -> None:
        """A chain that loops back to the wrapper cannot make the problem recurse."""
        root_fault = PipelexError("combine failed")
        located = _locate(root_fault, pipe_stack=["flow"])
        root_fault.__cause__ = located

        problem = located.to_problem(view=ProblemView.OPERATOR)

        assert problem.diagnostics is not None
        assert problem.diagnostics.error_class == "PipeRouterError"
        assert problem.diagnostics.message.endswith("combine failed")
