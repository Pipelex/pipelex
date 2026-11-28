"""A bundle's `main_pipe` naming no pipe it defines is refused through `validate_bundle` as `method.pipe_unresolved`.

The verdict's one item names the missing pipe and the `main_pipe` declaration, and the Markdown a host attaches to the
verdict says so, where it used to be a `method.schema_violation` naming nothing to fix.
"""

import pytest
from mthds.protocol.problem.registry import CoreCode

from pipelex.errors.problem import ProblemView
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.pipeline.validation_render import render_invalid_verdict_markdown

_SOURCE = "hello.mthds"

_MISSING_MAIN_PIPE_MTHDS = """
domain = "hello"
description = "Greet the visitor"
main_pipe = "say_goodbye"

[pipe.say_hello]
type = "PipeLLM"
description = "Say hello"
output = "Text"
prompt = "Say hello to the visitor"
"""


@pytest.mark.asyncio(loop_scope="class")
class TestMainPipeUnresolvedValidation:
    async def test_the_verdict_names_the_missing_pipe_and_the_main_pipe_declaration(self) -> None:
        with pytest.raises(ValidateBundleError) as raised:
            await validate_bundle(mthds_contents=[_MISSING_MAIN_PIPE_MTHDS], mthds_sources=[_SOURCE])

        problem = raised.value.to_problem(view=ProblemView.CALLER)
        assert problem.code == CoreCode.METHOD_INVALID
        assert problem.errors is not None
        [item] = problem.errors
        assert item.code == CoreCode.METHOD_PIPE_UNRESOLVED
        assert item.params is not None
        assert item.params.as_wire() == {"pipe": "main_pipe", "missing": "say_goodbye", "candidates": ["hello.say_hello"]}
        assert item.location is not None
        assert item.location.as_wire() == {"field": "main_pipe", "file": _SOURCE}
        markdown = render_invalid_verdict_markdown(items=problem.errors, message=problem.detail)
        assert "1. **The method names a pipe that does not exist** (`method.pipe_unresolved`)" in markdown
        assert "   - Pipe 'main_pipe' names the pipe 'say_goodbye', which does not exist." in markdown
