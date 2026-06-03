from typing import cast

from pipelex.core.pipes.pipe_abstract import PipeAbstract

# Resolve the property descriptors directly via __dict__ so mypy doesn't lose the
# `property` type the way it does through attribute access on a `BaseModel` subclass.
_IS_SIGNATURE_DESCRIPTOR: property = PipeAbstract.__dict__["is_signature"]
_PIPE_DEPENDENCIES_FN = PipeAbstract.__dict__["pipe_dependencies"]


class _StubPipe:
    """Minimal stand-in exposing only `pipe_category`, used to exercise descriptors on `PipeAbstract`.

    Constructing a real `PipeAbstract` subclass requires a fully-formed `StuffSpec` and
    `Concept`, which would couple this unit test to unrelated machinery. The
    descriptor-on-stub pattern keeps the test focused on the surface under exam.
    """

    def __init__(self, pipe_category: str) -> None:
        self.pipe_category = pipe_category


def _is_signature_of(stub: _StubPipe) -> bool:
    fget = _IS_SIGNATURE_DESCRIPTOR.fget
    assert fget is not None
    return bool(fget(cast("PipeAbstract", stub)))


class TestPipeAbstractSignatureSurface:
    def test_is_signature_false_for_operator(self) -> None:
        stub = _StubPipe(pipe_category="PipeOperator")
        assert _is_signature_of(stub) is False

    def test_is_signature_false_for_controller(self) -> None:
        stub = _StubPipe(pipe_category="PipeController")
        assert _is_signature_of(stub) is False

    def test_is_signature_true_for_signature_category(self) -> None:
        stub = _StubPipe(pipe_category="PipeSignature")
        assert _is_signature_of(stub) is True

    def test_pipe_dependencies_default_returns_empty_set(self) -> None:
        stub = _StubPipe(pipe_category="PipeOperator")
        assert _PIPE_DEPENDENCIES_FN(cast("PipeAbstract", stub)) == set()
