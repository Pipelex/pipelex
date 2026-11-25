from pathlib import Path

import pytest

from pipelex.errors.problem import ProblemView
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.pipeline.validate_in_process import validate_bundles_in_process
from pipelex.system.pipe_run_mode import PipeRunMode

# A host library pipe declaring five texts, more than the caller's own maximum below.
_HOST_BUNDLE = """
domain      = "host_brainstorm"
description = "The host's own brainstorming methods"

[pipe.five_ideas]
type        = "PipeLLM"
description = "Make five ideas"
inputs      = { topic = "Text" }
output      = "Text[5]"
prompt      = "Five ideas about $topic"
"""

# The caller's own bundle, declaring no count.
_CALLER_BUNDLE = """
domain      = "caller_greeting"
description = "Greet someone"
main_pipe   = "greet"

[pipe.greet]
type        = "PipeCompose"
description = "Greet someone by name"
inputs      = { name = "Text" }
output      = "Text"
template    = "Hello $name"
"""

# The caller's own bundle declaring as many as the host's pipe.
_CALLER_DECLARING_BUNDLE = (
    _CALLER_BUNDLE.replace('output      = "Text"', 'output      = "Text[5]"')
    .replace('type        = "PipeCompose"', 'type        = "PipeLLM"')
    .replace('template    = "Hello $name"', 'prompt      = "Hello $name"')
)


def _host_library_dir(*, directory: Path) -> Path:
    library_dir = directory / "host_library"
    library_dir.mkdir()
    (library_dir / "brainstorm.mthds").write_text(_HOST_BUNDLE, encoding="utf-8")
    return library_dir


@pytest.mark.asyncio(loop_scope="class")
class TestHostLibraryDeclaredItemCount:
    async def test_a_host_library_loads_under_the_deployments_maximum_whatever_the_request_states(self, tmp_path: Path) -> None:
        """A caller lowering its own maximum below what a host pipe declares neither refuses its request nor faults the host."""
        library_dir = _host_library_dir(directory=tmp_path)

        report = await validate_bundles_in_process(mthds_contents=[_CALLER_BUNDLE], library_dirs=[library_dir], max_declared_item_count=4)
        assert report is not None

        response = await PipelexMTHDSProtocol(library_dirs=[str(library_dir)], pipe_run_mode=PipeRunMode.DRY, max_declared_item_count=4).execute(
            pipe_code="greet", mthds_contents=[_CALLER_BUNDLE], inputs={"name": "Ada"}
        )
        assert response.pipe_output is not None

    async def test_the_callers_own_contents_stay_held_to_the_requests_maximum(self, tmp_path: Path) -> None:
        library_dir = _host_library_dir(directory=tmp_path)

        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundles_in_process(mthds_contents=[_CALLER_DECLARING_BUNDLE], library_dirs=[library_dir], max_declared_item_count=4)

        problem = exc_info.value.to_problem(view=ProblemView.OPERATOR)
        refusals = [item for item in problem.errors or [] if item.code == PipelexErrorCode.DEPLOYMENT_DECLARED_COUNT_OVER_LIMIT]
        assert [item.params.model_dump(exclude_none=True) if item.params is not None else {} for item in refusals] == [
            {"slot": "the output of the pipe 'greet'", "count": 5, "limit": 4}
        ]
