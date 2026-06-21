"""Unit tests for ``pipelex.runtime_bridge.primitives.pipe_classification``.

The classifier answers a single question: "should this pipe be dispatched
as a child workflow (controller) or as an activity (leaf)?". Both
``pipelex_temporal`` and ``pipelex_mistralai_workflows.primitives`` rely
on it to make that branching decision (see `wip/mistral-native-plan.md`
§1.2 row classification), so the test pins down all four controllers and
several leaf operators.

We use ``MagicMock(spec=Cls)`` because ``isinstance(mock, AnyBase)``
respects the spec's MRO — that's all the classifier checks. Constructing
the real Pydantic models would require a populated library and
domain/concept resolution that is irrelevant to this unit.
"""

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from pipelex.pipe_controllers.batch.pipe_batch import PipeBatch
from pipelex.pipe_controllers.condition.pipe_condition import PipeCondition
from pipelex.pipe_controllers.parallel.pipe_parallel import PipeParallel
from pipelex.pipe_controllers.sequence.pipe_sequence import PipeSequence
from pipelex.pipe_operators.compose.pipe_compose import PipeCompose
from pipelex.pipe_operators.func.pipe_func import PipeFunc
from pipelex.pipe_operators.img_gen.pipe_img_gen import PipeImgGen
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.runtime_bridge.primitives.pipe_classification import (
    is_controller_pipe,
    is_leaf_pipe,
)

if TYPE_CHECKING:
    from pipelex.core.pipes.pipe_abstract import PipeAbstract


def _spec_pipe(cls: "type[PipeAbstract]") -> "PipeAbstract":
    """Return a MagicMock that ``isinstance``-passes as ``cls``."""
    return MagicMock(spec=cls)


class TestIsControllerPipe:
    def test_pipe_sequence_is_controller(self) -> None:
        pipe = _spec_pipe(PipeSequence)
        assert is_controller_pipe(pipe) is True
        assert is_leaf_pipe(pipe) is False

    def test_pipe_batch_is_controller(self) -> None:
        pipe = _spec_pipe(PipeBatch)
        assert is_controller_pipe(pipe) is True
        assert is_leaf_pipe(pipe) is False

    def test_pipe_condition_is_controller(self) -> None:
        pipe = _spec_pipe(PipeCondition)
        assert is_controller_pipe(pipe) is True
        assert is_leaf_pipe(pipe) is False

    def test_pipe_parallel_is_controller(self) -> None:
        pipe = _spec_pipe(PipeParallel)
        assert is_controller_pipe(pipe) is True
        assert is_leaf_pipe(pipe) is False


class TestIsLeafPipe:
    def test_pipe_llm_is_leaf(self) -> None:
        pipe = _spec_pipe(PipeLLM)
        assert is_leaf_pipe(pipe) is True
        assert is_controller_pipe(pipe) is False

    def test_pipe_compose_is_leaf(self) -> None:
        pipe = _spec_pipe(PipeCompose)
        assert is_leaf_pipe(pipe) is True
        assert is_controller_pipe(pipe) is False

    def test_pipe_func_is_leaf(self) -> None:
        pipe = _spec_pipe(PipeFunc)
        assert is_leaf_pipe(pipe) is True
        assert is_controller_pipe(pipe) is False

    def test_pipe_img_gen_is_leaf(self) -> None:
        pipe = _spec_pipe(PipeImgGen)
        assert is_leaf_pipe(pipe) is True
        assert is_controller_pipe(pipe) is False
