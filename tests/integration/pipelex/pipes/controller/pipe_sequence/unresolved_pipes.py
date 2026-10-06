"""Make a pipe look unresolved to a sequence's static analyses while the run still finds it.

A pipe a sequence's step names may not resolve at validation, as a dependency's pipe the library has not loaded yet, and the
sequence then assumes it delivers: the typed flow cannot type what it stores, so a binding reading it is derived when it runs.
A bundle loaded whole always resolves its pipes, so the tests reach that state by hiding the pipe from the lookups of the
typed flow and of the sequence's own analyses, while the run resolves it as usual.
"""

from pytest_mock import MockerFixture

from pipelex.interpreter_hub import get_optional_pipe
from pipelex.pipe_controllers.sequence import pipe_sequence as sequence_module
from pipelex.pipe_controllers.sequence import sequence_typed_flow as typed_flow_module
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract


def hide_pipe_from_sequence_analyses(*, mocker: MockerFixture, pipe_code: str) -> None:
    """Have the typed flow and the sequence's static analyses find no pipe named `pipe_code`, whatever its domain."""
    hidden_pipe_code = pipe_code

    def get_optional_pipe_but_hidden(*, pipe_code: str) -> PipeAbstract | None:
        if pipe_code.rsplit(".", maxsplit=1)[-1] == hidden_pipe_code:
            return None
        return get_optional_pipe(pipe_code=pipe_code)

    mocker.patch.object(typed_flow_module, "get_optional_pipe", side_effect=get_optional_pipe_but_hidden)
    mocker.patch.object(sequence_module, "get_optional_pipe", side_effect=get_optional_pipe_but_hidden)
