from pathlib import Path

import pytest

from pipelex.config import get_config
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.pipeline.validate_in_process import validate_bundles_in_process
from pipelex.system.pipe_run_mode import PipeRunMode

# A host library pipe declaring five texts, more than the caller's own maximum below, within the deployment's.
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

    async def test_a_host_pipe_dry_runs_whatever_the_request_states(self, tmp_path: Path) -> None:
        """A host pipe declaring up to the deployment's maximum is never refused, at its load nor in its dry run, for a lower request maximum."""
        library_dir = _host_library_dir(directory=tmp_path)
        execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(generate_graph=False, mock_inputs=True)
        runner = PipelexMTHDSProtocol(
            library_dirs=[str(library_dir)], pipe_run_mode=PipeRunMode.DRY, execution_config=execution_config, max_declared_item_count=4
        )

        response = await runner.execute(pipe_code="host_brainstorm.five_ideas")

        assert len(response.pipe_output.main_stuff.as_list_of_fixed_content_type(TextContent).items) == 5
