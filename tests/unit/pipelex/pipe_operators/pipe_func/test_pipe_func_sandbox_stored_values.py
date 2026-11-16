import asyncio
import json
import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from pytest_mock import MockerFixture

from pipelex.config import get_config
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.method_trees.tree_files import write_call_files
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_library_manager, scoped_current_library
from pipelex.libraries.concepts_libraries import typed_by_crate_concepts
from pipelex.libraries.pipe_func_call_files import read_pipe_func_call_files
from pipelex.pipe_operators.func import pipe_func_transported_entrypoint
from pipelex.pipe_operators.func.direct_pipe_func_executor import TRANSPORTED_LIBRARY_ID
from pipelex.pipe_operators.func.pipe_func_execution_dtos import PipeFuncExecutionRequest, PipeFuncExecutionResponse
from pipelex.pipe_operators.func.pipe_func_execution_transport import (
    build_pipe_func_execution_request,
    inline_stored_values_for_sandbox,
    pipe_func_execution_result_from_response,
    store_large_values_of_sandbox_response,
)
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipelex import Pipelex
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider

READ_SCOPE = "org_abc"
STORAGE_SCOPE = "org_abc/mt_1/run_1"
STORAGE_URI_SCHEME = "pipelex-storage://"
# Past the default inline threshold of 4096 bytes, whatever the test configuration sets it to.
NOTES_TEXT = "A long note the caller stored, one line after another.\n" * 120
SUMMARY_PREFIX = "Summary of the notes: "

_NOTES_MTHDS = """\
domain = "notes_demo"
description = "A step whose function reads a long note"

[pipe.summarize_notes]
type = "PipeFunc"
description = "Summarize the notes through customer code"
inputs = { notes = "Text" }
output = "Text"
function_name = "notes_funcs.summary.summarize_notes"
"""

_NOTES_FUNC = f"""\
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.system.registries.func_registry import pipe_func


@pipe_func()
async def summarize_notes(working_memory: WorkingMemory) -> TextContent:
    notes = working_memory.get_stuff_as_text(name="notes").require_text()
    return TextContent(text="{SUMMARY_PREFIX}" + notes.upper())
"""


@contextmanager
def _notes_request(*, tmp_path: Path, notes_url: str) -> Generator[PipeFuncExecutionRequest, None, None]:
    """The request a sandbox-hosted deployment builds for the step, its notes a stored text, its library open while the call runs."""
    method_dir = tmp_path / "notes_method"
    (method_dir / "notes_funcs").mkdir(parents=True)
    (method_dir / "notes.mthds").write_text(_NOTES_MTHDS, encoding="utf-8")
    (method_dir / "notes_funcs" / "summary.py").write_text(_NOTES_FUNC, encoding="utf-8")

    pipe_func_config = get_config().interpreter.pipe_func
    previous_mode = pipe_func_config.execution_mode
    pipe_func_config.execution_mode = "local_sandbox"
    library_manager = get_library_manager()
    try:
        build_library_id, _ = library_manager.open_library()
        try:
            with scoped_current_library(library_id=build_library_id):
                library_manager.load_libraries(library_id=build_library_id, library_dirs=[method_dir])
                notes_stuff = StuffFactory.make_stuff(
                    concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
                    content=TextContent(url=notes_url),
                    name="notes",
                )
                yield build_pipe_func_execution_request(
                    job_metadata=JobMetadata(
                        run_metadata=RunMetadata(storage_scope=STORAGE_SCOPE, read_scope=READ_SCOPE, user_id="user", pipeline_run_id="run")
                    ),
                    pipe_code="notes_demo.summarize_notes",
                    function_name="notes_funcs.summary.summarize_notes",
                    working_memory=WorkingMemoryFactory.make_from_single_stuff(notes_stuff),
                    pipe_run_params=PipeRunParams(run_mode=PipeRunMode.LIVE, pipe_stack_limit=10, batch_max_concurrency=None),
                )
        finally:
            library_manager.teardown(library_id=build_library_id)
    finally:
        pipe_func_config.execution_mode = previous_mode


def _run_in_sandbox(*, mocker: MockerFixture, request: PipeFuncExecutionRequest, work_dir: Path) -> PipeFuncExecutionResponse:
    """Run the entrypoint as a sandbox runs it, with no storage provider at all, and read its response back."""
    request_path = work_dir / "request.json"
    result_path = work_dir / "result.json"
    tree_root = work_dir / "tree"
    tree_root.mkdir()
    request_path.write_text(request.model_dump_json(), encoding="utf-8")
    assert request.tree_digest is not None
    call_files = asyncio.run(read_pipe_func_call_files(tree_digest=request.tree_digest, read_scope=None))
    write_call_files(files=call_files, destination=tree_root)
    mocker.patch.object(sys, "argv", ["pipe_func_transported_entrypoint", str(request_path), str(result_path), str(tree_root)])
    mocker.patch.object(Pipelex, "make")
    mocker.patch.object(Pipelex, "teardown_if_needed")
    with scoped_current_library(library_id=TRANSPORTED_LIBRARY_ID):
        try:
            pipe_func_transported_entrypoint.main()
        finally:
            get_library_manager().teardown(library_id=TRANSPORTED_LIBRARY_ID)
    return PipeFuncExecutionResponse.model_validate_json(result_path.read_text(encoding="utf-8"))


class TestPipeFuncSandboxStoredValues:
    def test_a_sandboxed_function_reads_a_stored_input_and_its_large_output_is_stored_on_the_host(
        self, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        """The host inlines the stored notes before the sandbox runs, and stores the function's large output once it returns."""
        storage = InMemoryStorageProvider()
        mocker.patch("pipelex.pipe_operators.func.pipe_func_execution_transport.get_storage_provider", return_value=storage)
        notes_url = asyncio.run(
            storage.store(data=NOTES_TEXT.encode("utf-8"), key=f"{READ_SCOPE}/uploads/{uuid4().hex}/notes.txt", content_type="text/plain")
        )
        expected_output = SUMMARY_PREFIX + NOTES_TEXT.upper()

        with _notes_request(tmp_path=tmp_path, notes_url=notes_url) as request:
            # The request a workflow builds carries the notes as their reference alone.
            assert json.dumps(NOTES_TEXT)[1:-1] not in request.model_dump_json()
            # The host holds the run's library here, as in a local run.
            inline_request = asyncio.run(inline_stored_values_for_sandbox(request=request))
            assert notes_url not in inline_request.model_dump_json()
            assert inline_request.working_memory_raw["root"]["notes"]["content"] == {"text": NOTES_TEXT}
            sandbox_response = _run_in_sandbox(mocker=mocker, request=inline_request, work_dir=tmp_path)

        # The sandbox reached no storage, so the output came back inline, beside the notes it received.
        sandbox_root = sandbox_response.output_memory_raw["root"]
        assert sandbox_root["main_stuff"]["content"] == {"text": expected_output}
        assert sandbox_root["notes"]["content"] == {"text": NOTES_TEXT}
        # Here the host holds no library of the run, as an activity on a worker: the crate's concepts type the output.
        stored_response = asyncio.run(store_large_values_of_sandbox_response(request=request, response=sandbox_response))

        # The response keeps the output alone, as its reference: neither the output nor the notes cross inline.
        stored_json = stored_response.model_dump_json()
        assert json.dumps(expected_output)[1:-1] not in stored_json
        assert json.dumps(NOTES_TEXT)[1:-1] not in stored_json
        assert set(stored_response.output_memory_raw["root"]) == {"main_stuff"}
        with typed_by_crate_concepts(crate=request.crate):
            output_content = pipe_func_execution_result_from_response(stored_response).content
        assert isinstance(output_content, TextContent)
        assert output_content.url is not None
        output_key = output_content.url.removeprefix(STORAGE_URI_SCHEME)
        assert output_key.startswith(f"{STORAGE_SCOPE}/generated/")
        assert storage.root[output_key] == expected_output.encode("utf-8")

    def test_a_request_holding_no_stored_value_is_handed_over_as_it_is(self, tmp_path: Path, mocker: MockerFixture) -> None:
        storage = InMemoryStorageProvider()
        mocker.patch("pipelex.pipe_operators.func.pipe_func_execution_transport.get_storage_provider", return_value=storage)
        notes_url = asyncio.run(
            storage.store(data=NOTES_TEXT.encode("utf-8"), key=f"{READ_SCOPE}/uploads/{uuid4().hex}/notes.txt", content_type="text/plain")
        )
        with _notes_request(tmp_path=tmp_path, notes_url=notes_url) as request:
            inline_request = asyncio.run(inline_stored_values_for_sandbox(request=request))
            assert asyncio.run(inline_stored_values_for_sandbox(request=inline_request)) is inline_request
