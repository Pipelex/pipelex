"""An error carrying a problem recovered across a transport boundary, as a distributed submitter raises one.

Its class declares the catch-all code, as a host plugin's carrier does, while the problem it reports carries the code the
far side found: a surface that reads the class's code instead of the problem's tells the two apart, which is what the
tests using it check.
"""

from typing import ClassVar

from mthds.protocol.problem.registry import CoreCode
from typing_extensions import override

from pipelex.base_exceptions import PipelexError
from pipelex.errors.error_code_declaration import ErrorCodeDeclaration
from pipelex.errors.problem import PipelexProblem, ProblemView, make_problem


class RecoveredProblemError(PipelexError):
    """Carries a problem in the operator's view, which its `to_problem` reports projected to the view asked for."""

    error_code: ClassVar[ErrorCodeDeclaration] = CoreCode.RUNTIME_UNEXPECTED

    def __init__(self, message: str, *, problem: PipelexProblem):
        super().__init__(message)
        self.carried_problem = problem

    @override
    def recovered_problem(self) -> PipelexProblem | None:
        return self.carried_problem


def make_recovered_url_refusal() -> RecoveredProblemError:
    """A recovered refusal of an input URL: an `input` problem a retry can clear, unlike the carrier's own code."""
    problem = make_problem(code=CoreCode.INPUT_URL_UNREACHABLE, view=ProblemView.OPERATOR, params={"input": "document", "host": "example.com"})
    return RecoveredProblemError("a worker could not reach the document's URL", problem=problem)
