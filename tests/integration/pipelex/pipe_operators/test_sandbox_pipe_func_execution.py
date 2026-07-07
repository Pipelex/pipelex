import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest

from pipelex.config import get_config
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.hub import get_library_manager, get_pipe_router, scoped_pipe_func_executor, set_current_library
from pipelex.pipe_operators.func.sandbox.local_subprocess_sandbox_client import LocalSubprocessSandboxClient
from pipelex.pipe_operators.func.sandbox.sandbox_pipe_func_executor import SandboxPipeFuncExecutor
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.system.registries.func_registry import func_registry

SHOUT_MTHDS = """\
domain = "sandbox_demo"
description = "Sandbox PipeFunc demo"

[pipe.shout]
type = "PipeFunc"
description = "Uppercase the input text using customer code that runs in a sandbox"
inputs = { message = "Text" }
output = "Text"
function_name = "shout_it"
"""

# Customer code — imported ONLY inside the sandbox subprocess, never in the test process.
CUSTOMER_FUNC_PY = """\
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.system.registries.func_registry import pipe_func


@pipe_func(name="shout_it")
async def shout_it(working_memory: WorkingMemory) -> TextContent:
    message = working_memory.get_stuff_as_str("message")
    return TextContent(text=message.upper() + " (from the sandbox)")
"""


@pytest.fixture
def sandbox_hosted_mode() -> Generator[None, None, None]:
    pipe_func_config = get_config().pipelex.pipe_func_config
    previous = pipe_func_config.is_sandbox_hosted
    pipe_func_config.is_sandbox_hosted = True
    try:
        yield
    finally:
        pipe_func_config.is_sandbox_hosted = previous


@pytest.mark.asyncio(loop_scope="class")
class TestSandboxPipeFuncExecution:
    """End-to-end WITHOUT Temporal: a hosted-mode PipeFunc run executes the customer .py in a
    subprocess via the sandbox executor and the output comes back correct — while the function is
    NEVER registered in this process.
    """

    @pytest.mark.usefixtures("sandbox_hosted_mode")
    async def test_pipe_func_runs_in_subprocess(self, job_metadata: JobMetadata):
        function_name = "shout_it"
        assert func_registry.get_function(function_name) is None  # precondition: absent here

        library_manager = get_library_manager()
        with tempfile.TemporaryDirectory() as tmp_dir:
            library_dir = Path(tmp_dir)
            (library_dir / "shout.mthds").write_text(SHOUT_MTHDS, encoding="utf-8")
            (library_dir / "customer_func.py").write_text(CUSTOMER_FUNC_PY, encoding="utf-8")

            library_id, _ = library_manager.open_library()
            set_current_library(library_id=library_id)
            try:
                # Hosted load: captures the .py onto the crate, does NOT register the function here.
                library_manager.load_libraries(library_id=library_id, library_dirs=[library_dir])
                assert func_registry.get_function(function_name) is None

                shout_pipe = library_manager.get_library(library_id=library_id).pipe_library.get_required_pipe(pipe_code="shout")

                message_stuff = StuffFactory.make_stuff(
                    name="message",
                    concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
                    content=TextContent(text="hello world"),
                )
                working_memory = WorkingMemoryFactory.make_from_single_stuff(stuff=message_stuff)

                pipe_job = PipeJobFactory.make_pipe_job(
                    pipe=shout_pipe,
                    pipe_run_params=PipeRunParamsFactory.make_run_params(),
                    job_metadata=job_metadata,
                    working_memory=working_memory,
                )

                executor = SandboxPipeFuncExecutor(sandbox_client=LocalSubprocessSandboxClient())
                with scoped_pipe_func_executor(executor):
                    pipe_output = await get_pipe_router().run(pipe_job=pipe_job)

                assert pipe_output.main_stuff_as_text.text == "HELLO WORLD (from the sandbox)"
                # Still never registered locally — the code only ran in the subprocess.
                assert func_registry.get_function(function_name) is None
            finally:
                library_manager.teardown(library_id=library_id)
