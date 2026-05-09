"""Pipe classification helpers used by host-runtime routers.

Framework-agnostic — answers the single question "should this pipe be
dispatched as a child workflow (controller) or as an activity (leaf)?".
Both ``pipelex.temporal`` and ``pipelex_mistralai_workflows.primitives``
use these to make that branching decision.
"""

from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.pipe_controllers.pipe_controller import PipeController


def is_controller_pipe(pipe: PipeAbstract) -> bool:
    """Return True if ``pipe`` is a controller (PipeSequence, PipeBatch, …).

    Controllers iterate over sub-pipes and are the right unit to dispatch as
    a child workflow under per-step decomposition modes (e.g. MISTRAL_NATIVE).
    Leaf / operator pipes (PipeLLM, PipeImg, PipePython, …) should run inside
    activities, not workflows, because the controller boundary is exactly
    where signals / timers / cancellation / per-step retry need to attach.
    """
    return isinstance(pipe, PipeController)


def is_leaf_pipe(pipe: PipeAbstract) -> bool:
    """Return True if ``pipe`` is a leaf operator (PipeLLM, PipeImg, …).

    Convenience inverse of ``is_controller_pipe``. A leaf pipe maps to a
    single I/O burst that fits inside one activity invocation.
    """
    return not is_controller_pipe(pipe)
