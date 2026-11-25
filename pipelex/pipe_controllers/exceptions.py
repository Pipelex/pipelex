from typing import Any, ClassVar

from mthds.protocol.problem.models import ProblemLocation
from mthds.protocol.problem.registry import CoreCode
from typing_extensions import override

from pipelex.base_exceptions import PipelexError
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.errors.error_code_declaration import ABSTRACT_ERROR, ErrorCodeDeclaration
from pipelex.errors.problem import make_location


class PipeControllerError(PipelexError):
    """Base of the errors of the pipe controllers."""

    error_code: ClassVar[ErrorCodeDeclaration] = ABSTRACT_ERROR


class PipeBatchTooWideError(PipeControllerError):
    """A ``PipeBatch`` whose items would write more into its run's durable history than the history has room for.

    A durable runtime keeps a history per run, which its engine bounds in bytes and in events, and every branch of a
    batch writes into its parent's history. A durable router raises this error from
    ``PipeRouterProtocol.check_batch_fits``, before the batch's first branch starts, when its estimate of what the whole
    batch would write passes the room left; or from its own dispatch, during the fan-out, when the branches already
    started turn out larger than the first one promised and the history comes too close to its limit to start another.
    The two shapes differ only by ``started_item_count``: ``None`` for a batch refused before any item started, the
    number of items started for a batch stopped on its way, whose message then says how many started and speaks of
    the items left.

    The error builds its own message from the figures it is given, so a refusal reads the same whichever backend
    raises it, and its problem is ``input.too_large``: the batched list is the step's input, and the remedy is a
    shorter list. The problem names the list as its ``input``, the item count as its ``size`` and the largest item count
    that fits as its ``limit``; the bytes and the events are the operator's, in the message.
    """

    error_code = CoreCode.INPUT_TOO_LARGE

    def __init__(
        self,
        *,
        pipe_code: str,
        input_list_label: str,
        item_count: int,
        estimated_bytes: int,
        estimated_events: int,
        bytes_left: int,
        events_left: int,
        max_fitting_item_count: int,
        started_item_count: int | None = None,
    ):
        """Build the refusal from the backend's figures; every argument is keyword-only.

        Args:
            pipe_code: The code of the ``PipeBatch`` refused or stopped.
            input_list_label: The list the batch runs over, named as its author wrote it (``BatchParams.input_list_label``).
            item_count: How many items the list holds.
            estimated_bytes: The bytes the batch's items would write into the run's history: all of them, estimated
                from the first branch, when the batch is refused; those not yet started, at the rate the started ones
                wrote, when it is stopped.
            estimated_events: The events those same items would add to the run's history, estimated the same way.
            bytes_left: The bytes the run's history had left for those items when the backend decided, after any
                reserve the backend keeps.
            events_left: The events the run's history had left for those items when the backend decided, after its
                reserve.
            max_fitting_item_count: The largest item count of this list the backend estimates would fit in one batch
                of this run, in bytes and in events.
            started_item_count: ``None`` when the batch is refused before any of its items started; the number of items
                already started when the backend stops the batch during its fan-out.
        """
        self.pipe_code = pipe_code
        self.input_list_label = input_list_label
        self.item_count = item_count
        self.estimated_bytes = estimated_bytes
        self.estimated_events = estimated_events
        self.bytes_left = bytes_left
        self.events_left = events_left
        self.max_fitting_item_count = max_fitting_item_count
        self.started_item_count = started_item_count
        super().__init__(self._compose_message())
        self.user_action = UserAction(
            kind=UserActionKind.CHANGE_INPUT,
            detail=(
                f"Split the list '{input_list_label}' into lists of at most {max_fitting_item_count:,} items, "
                "each batched by a run of its own, or batch over fewer items."
            ),
        )

    @property
    def is_stopped(self) -> bool:
        """Whether the batch was stopped after some of its items started, rather than refused before the first."""
        return self.started_item_count is not None

    def _compose_message(self) -> str:
        label = self.input_list_label
        footprint = (
            f"about {self.estimated_bytes:,} bytes and {self.estimated_events:,} events into the run's history, "
            f"which has {self.bytes_left:,} bytes and {self.events_left:,} events left for them"
        )
        if self.started_item_count is None:
            outcome = (
                f"PipeBatch '{self.pipe_code}' was refused before any of its {self.item_count:,} items of '{label}' started: "
                f"they would write {footprint}."
            )
        else:
            items_left = self.item_count - self.started_item_count
            outcome = (
                f"PipeBatch '{self.pipe_code}' was stopped after {self.started_item_count:,} of its {self.item_count:,} items "
                f"of '{label}' started: the {items_left:,} items left would write {footprint}."
            )
        return f"{outcome} At most {self.max_fitting_item_count:,} items fit, so batch over a shorter list."

    @override
    def problem_params(self) -> dict[str, Any]:
        return {"input": self.input_list_label, "limit": self.max_fitting_item_count, "size": self.item_count}

    @override
    def problem_location(self) -> ProblemLocation | None:
        return make_location(input_name=self.input_list_label)
