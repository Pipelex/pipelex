"""Pipe classification helpers for per-step-decomposition host runtimes.

Framework-agnostic — answers the single question "should this pipe be
dispatched as a child workflow (controller) or as an activity (leaf)?".
This is bridge-side plumbing for the ``"mistralai-workflows"`` mode: the
``pipelex_mistralai_workflows`` host package is the intended consumer of
this controller/leaf split. There is no in-tree caller yet — the Temporal
path makes the same decision elsewhere (``temporal_pipe_router``) — so the
helpers live here, framework-agnostic, ready to be shared once the Mistral
host integration lands.
"""

from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.pipe_controllers.pipe_controller import PipeController


def is_controller_pipe(pipe: PipeAbstract) -> bool:
    """Return True if ``pipe`` is a controller (PipeSequence, PipeBatch, …).

    Controllers iterate over sub-pipes and are the right unit to dispatch as
    a child workflow under per-step decomposition modes (e.g. the
    ``"mistralai-workflows"`` mode).
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
