"""The invalid verdict a bundle validator returns: the refusal's problem, and the items the verdict lists."""

from pydantic import BaseModel, ConfigDict, Field

from pipelex.base_exceptions import ValidationErrorItem
from pipelex.errors.problem import PipelexProblem
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of


class BundleValidationFailure(BaseModel):
    """A bundle refused by validation, as a value: its problem in the operator's view, and its validation items.

    A validator returns it rather than raising, since an invalid bundle is a verdict and not a fault, and the host that
    serves the verdict projects the problem to the view of whoever asked (``pipelex.errors.problem.caller_view_of``).
    It crosses process boundaries, a worker-dispatched validator's included, so it is a model.

    Attributes:
        problem: The refusal's problem, in the operator's view.
        validation_errors: One item per refusal, in the order the validation stages found them, which the verdict lists.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    problem: PipelexProblem
    validation_errors: list[ValidationErrorItem] = Field(default_factory=empty_list_factory_of(ValidationErrorItem))
