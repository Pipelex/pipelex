import pytest
from mthds.protocol.problem.registry import ProblemDomain, StepKind

from pipelex.errors.problem import ProblemView
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.runtime_bridge.exceptions import MissingOrchestratorError


class TestRuntimeBridgeExceptionDisclosure:
    @pytest.mark.parametrize("mode", ["temporal", "mistral-workflows", "acme"])
    def test_generic_plugin_hint_reaches_the_operator(self, mode: str) -> None:
        """MissingOrchestratorError's plugin-decoupled hint is the operator's to read, its code the caller's.

        A configured mode with no orchestrator is the deployment's to fix: the operator reads the message naming the
        mode and asking whether its plugin is installed, and the caller reads the code's sentences, which name no
        plugin of the deployment.
        """
        error = MissingOrchestratorError(mode=mode)

        caller = error.to_problem(view=ProblemView.CALLER)
        operator = error.to_problem(view=ProblemView.OPERATOR)

        assert caller.code == PipelexErrorCode.PLUGIN_NOT_FOUND
        assert caller.domain == ProblemDomain.OPERATOR
        assert caller.next_step.kind == StepKind.REPORT
        assert caller.diagnostics is None
        assert "is its plugin installed?" not in str(caller.to_wire())
        assert operator.next_step.kind == StepKind.FIX_CONFIGURATION
        assert operator.diagnostics is not None
        assert operator.diagnostics.message == f"No orchestrator is registered for orchestration mode '{mode}'; is its plugin installed?"
