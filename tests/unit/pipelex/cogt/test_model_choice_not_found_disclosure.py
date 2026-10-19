from mthds.protocol.problem.registry import CoreCode, ProblemDomain, StepKind

from pipelex.cogt.exceptions import ModelChoiceNotFoundError
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.errors.problem import PipelexProblem, ProblemView


class TestModelChoiceNotFoundDisclosure:
    @staticmethod
    def _make_error() -> ModelChoiceNotFoundError:
        return ModelChoiceNotFoundError(
            message="Model handle 'gpt-5.1' was not found in the model deck",
            model_type=ModelType.LLM,
            model_choice="gpt-5.1",
            suggestions=["gpt-5.5", "gpt-5.4"],
        )

    def test_the_caller_reads_the_unknown_model_and_its_suggestions(self) -> None:
        """The unknown model name and its suggestions reach a hosted caller, in the code's sentence and its parameters."""
        caller = self._make_error().to_problem(view=ProblemView.CALLER)
        assert caller.code == CoreCode.MODEL_UNKNOWN
        assert caller.domain == ProblemDomain.METHOD
        assert caller.detail == "The method names the llm model 'gpt-5.1', which no catalog knows."
        assert caller.next_step.kind == StepKind.CHANGE_MODEL
        assert caller.params is not None
        assert caller.params.as_wire() == {"model": "gpt-5.1", "model_type": "llm", "suggestions": ["gpt-5.5", "gpt-5.4"]}
        assert caller.diagnostics is None

    def test_the_operator_reads_the_error_s_own_message(self) -> None:
        """The error's own message, its suggestions included, is the operator's diagnostics."""
        operator = self._make_error().to_problem(view=ProblemView.OPERATOR)
        assert operator.diagnostics is not None
        assert operator.diagnostics.error_class == "ModelChoiceNotFoundError"
        assert operator.diagnostics.message == "Model handle 'gpt-5.1' was not found in the model deck\n\nDid you mean: gpt-5.5, gpt-5.4"

    def test_the_caller_s_view_survives_the_worker_to_runner_hop(self) -> None:
        """The hosted path builds the problem on the worker and reads it back on the runner, which answers the caller with it."""
        packed = self._make_error().to_problem(view=ProblemView.CALLER).to_wire()
        recovered = PipelexProblem.model_validate(packed)
        assert recovered.to_wire() == packed
        assert recovered.params is not None
        assert recovered.params.as_wire()["model"] == "gpt-5.1"
        assert recovered.params.as_wire()["suggestions"] == ["gpt-5.5", "gpt-5.4"]
