"""The invocation path: the name of one run of one pipe inside a run.

The hosted progress contract (`conformance/specs/pipelex-platform-api.md`, "Invocation paths") names every invocation
of a run by its path: the run's entry pipe's `pipe_ref`, then one segment per controller level down to the invocation,
such as `filings.review_filings/step_3/item_2/step_1`. A path holds no counter, no run-scoped id and no engine's name,
so the same invocation has the same path in every run of the same method, on every engine, live or dry.

The segments, under the controller that adds each:

- `step_<n>` under a `PipeSequence`: its step `n`, numbered from 1 as the author wrote the steps, binding steps
  included. A binding step runs no pipe, so no invocation has its path.
- `branch_<n>` under a `PipeParallel`: its branch `n`, numbered from 1 in declaration order.
- `item_<n>` under a `PipeBatch`: the branch pipe run for item `n` of the list, numbered from 1.
- `outcome_<key>` under a `PipeCondition`: the pipe of one outcome group, named by the first key of the outcome map
  that runs it, percent-encoded.
- `default` under a `PipeCondition`: the pipe of its default outcome, when no key of its outcome map runs that pipe.

A step or a branch that batches runs as the `PipeBatch` the runtime makes for it, which is the invocation at the step's
or the branch's segment, its items under it.
"""

from urllib.parse import quote

from pipelex.system.exceptions import InvocationPathError

PATH_SEPARATOR = "/"
DEFAULT_OUTCOME_SEGMENT = "default"


def _ordinal(*, segment_kind: str, number: int) -> int:
    """The number of a segment, which counts from 1.

    Raises:
        InvocationPathError: The number is below 1.
    """
    if number < 1:
        msg = f"An invocation path's '{segment_kind}' segment counts from 1, and was given {number}."
        raise InvocationPathError(msg)
    return number


def step_segment(*, step_number: int) -> str:
    """The segment of the pipe a sequence's step runs, its number counting from 1 as the author wrote the steps."""
    return f"step_{_ordinal(segment_kind='step', number=step_number)}"


def branch_segment(*, branch_number: int) -> str:
    """The segment of the pipe of a parallel's branch, numbered from 1 in the order the parallel declares them."""
    return f"branch_{_ordinal(segment_kind='branch', number=branch_number)}"


def item_segment(*, item_number: int) -> str:
    """The segment of a batch's branch pipe run for one item of its list: the item at index 0 is `item_1`."""
    return f"item_{_ordinal(segment_kind='item', number=item_number)}"


def outcome_segment(*, outcome_key: str) -> str:
    """The segment of a condition's outcome group, named by a key of its outcome map.

    Every byte of the key's UTF-8 form outside the unreserved set (letters, digits, `-`, `.`, `_` and `~`) is written as
    `%` and two upper-case hexadecimal digits, so `high risk` gives `outcome_high%20risk` and a key holding a `/` cannot
    split a segment.
    """
    return f"outcome_{quote(outcome_key, safe='')}"


def child_path(*, parent_path: str, segment: str) -> str:
    """The path of the invocation a controller runs at `segment`, under its own path."""
    return f"{parent_path}{PATH_SEPARATOR}{segment}"
