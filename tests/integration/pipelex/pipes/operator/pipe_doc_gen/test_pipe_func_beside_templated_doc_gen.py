import asyncio
import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pipelex.config import get_config
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.method_trees.tree_files import write_call_files
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_library_manager, scoped_current_library
from pipelex.libraries.pipe_func_call_files import read_pipe_func_call_files
from pipelex.pipe_operators.func import pipe_func_transported_entrypoint
from pipelex.pipe_operators.func.direct_pipe_func_executor import TRANSPORTED_LIBRARY_ID
from pipelex.pipe_operators.func.pipe_func_execution_dtos import PipeFuncExecutionRequest, PipeFuncExecutionResponse
from pipelex.pipe_operators.func.pipe_func_execution_transport import build_pipe_func_execution_request
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipelex import Pipelex
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from tests.integration.pipelex.pipes.operator.pipe_doc_gen.doc_gen_helpers import StubEngines, stub_engines_installed

_REPORT_MTHDS = """\
domain = "report_demo"
description = "Compute figures in code, then print them on the firm's HTML template"
main_pipe = "prepare_report"

[pipe.prepare_report]
type = "PipeSequence"
description = "Compute the figures, then print them"
inputs = { figures = "Text" }
output = "Document"
steps = [
  { pipe = "compute_figures", result = "summary" },
  { pipe = "print_report", result = "report" },
]

[pipe.compute_figures]
type = "PipeFunc"
description = "Compute the figures in code"
inputs = { figures = "Text" }
output = "Text"
function_name = "report_funcs.figures.compute_figures"

[pipe.print_report]
type = "PipeDocGen"
description = "Print the summary on the firm's template"
inputs = { summary = "Text" }
output = "Document"
format = "pdf"
template_file = "templates/report.html"
"""

_REPORT_TEMPLATE = "<html><body><h1>Report</h1><p>{{ summary }}</p></body></html>\n"

_FIGURES_FUNC = """\
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.system.registries.func_registry import pipe_func


@pipe_func()
def compute_figures(working_memory: WorkingMemory) -> TextContent:
    figures = working_memory.get_stuff_as_text(name="figures").require_text()
    total = sum(int(figure) for figure in figures.split(","))
    return TextContent(text=f"total={total}")
"""


@contextmanager
def _report_request(*, tmp_path: Path) -> Generator[PipeFuncExecutionRequest, None, None]:
    """The request a sandbox-hosted deployment builds for the PipeFunc step, built where a document engine prints the template.

    The library is loaded and validated with the stub document generation plugin installed, as the runner and the worker
    have the real one; the request is then handed over with the booted runtime back, which prints no HTML template.
    """
    method_dir = tmp_path / "report_method"
    (method_dir / "report_funcs").mkdir(parents=True)
    (method_dir / "templates").mkdir()
    (method_dir / "report.mthds").write_text(_REPORT_MTHDS, encoding="utf-8")
    (method_dir / "report_funcs" / "figures.py").write_text(_FIGURES_FUNC, encoding="utf-8")
    (method_dir / "templates" / "report.html").write_text(_REPORT_TEMPLATE, encoding="utf-8")

    pipe_func_config = get_config().interpreter.pipe_func
    previous_mode = pipe_func_config.execution_mode
    pipe_func_config.execution_mode = "local_sandbox"
    library_manager = get_library_manager()
    try:
        build_library_id, _ = library_manager.open_library()
        try:
            with scoped_current_library(library_id=build_library_id):
                with stub_engines_installed(engines=StubEngines()):
                    library_manager.load_libraries(library_id=build_library_id, library_dirs=[method_dir])
                figures_stuff = StuffFactory.make_stuff(
                    concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
                    content=TextContent(text="12,30"),
                    name="figures",
                )
                yield build_pipe_func_execution_request(
                    job_metadata=JobMetadata(
                        run_metadata=RunMetadata(storage_scope="org_abc/mt_1/run_1", read_scope="org_abc", user_id="user", pipeline_run_id="run")
                    ),
                    pipe_code="report_demo.compute_figures",
                    function_name="report_funcs.figures.compute_figures",
                    working_memory=WorkingMemoryFactory.make_from_single_stuff(figures_stuff),
                    pipe_run_params=PipeRunParams(run_mode=PipeRunMode.LIVE, pipe_stack_limit=10, batch_max_concurrency=None),
                )
        finally:
            library_manager.teardown(library_id=build_library_id)
    finally:
        pipe_func_config.execution_mode = previous_mode


@pytest.mark.usefixtures("no_engines")
class TestPipeFuncBesideTemplatedDocGen:
    def test_a_sandbox_without_the_document_engine_runs_the_function_of_a_method_printing_a_template(
        self, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        """The sandbox builds only the step it calls, so a sibling PipeDocGen no engine of the sandbox prints does not stop it."""
        with _report_request(tmp_path=tmp_path) as request:
            # The crate the sandbox receives holds the PipeDocGen step beside the PipeFunc.
            assert "report_demo.print_report" in request.crate.pipes
            request_path = tmp_path / "request.json"
            result_path = tmp_path / "result.json"
            tree_root = tmp_path / "tree"
            tree_root.mkdir()
            request_path.write_text(request.model_dump_json(), encoding="utf-8")
            assert request.tree_digest is not None
            call_files = asyncio.run(read_pipe_func_call_files(tree_digest=request.tree_digest, read_scope=None))
            write_call_files(files=call_files, destination=tree_root)

        # The sandbox runs the entrypoint with no document engine at all and no library of the run.
        mocker.patch.object(sys, "argv", ["pipe_func_transported_entrypoint", str(request_path), str(result_path), str(tree_root)])
        mocker.patch.object(Pipelex, "make")
        mocker.patch.object(Pipelex, "teardown_if_needed")
        with scoped_current_library(library_id=TRANSPORTED_LIBRARY_ID):
            try:
                pipe_func_transported_entrypoint.main()
                transported_pipes = get_library_manager().get_library(library_id=TRANSPORTED_LIBRARY_ID).pipe_library.root
                assert set(transported_pipes) == {"report_demo.compute_figures"}
            finally:
                get_library_manager().teardown(library_id=TRANSPORTED_LIBRARY_ID)

        response = PipeFuncExecutionResponse.model_validate_json(result_path.read_text(encoding="utf-8"))
        assert response.output_memory_raw["root"]["main_stuff"]["content"] == {"text": "total=42"}
