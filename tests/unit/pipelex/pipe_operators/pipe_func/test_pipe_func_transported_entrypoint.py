import asyncio
import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from mthds.protocol.problem.registry import CoreCode, ProblemDomain
from pydantic import ValidationError
from pytest_mock import MockerFixture

from pipelex.base_exceptions import PipelexError
from pipelex.config import get_config
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.method_trees.tree_files import write_call_files
from pipelex.errors.problem import MAX_PROBLEM_TEXT_LENGTH, ProblemDiagnostics, ProblemView, make_problem
from pipelex.interpreter_hub import get_library_manager, scoped_current_library
from pipelex.libraries.pipe_func_call_files import read_pipe_func_call_files
from pipelex.pipe_operators.func import pipe_func_transported_entrypoint
from pipelex.pipe_operators.func.direct_pipe_func_executor import TRANSPORTED_LIBRARY_ID, DirectPipeFuncExecutor
from pipelex.pipe_operators.func.exceptions import PipeFuncRaisedError
from pipelex.pipe_operators.func.pipe_func_execution_dtos import PipeFuncExecutionRequest, PipeFuncExecutionResponse, PipeFuncRaisedReport
from pipelex.pipe_operators.func.pipe_func_execution_transport import (
    build_pipe_func_execution_request,
    pipe_func_raised_report,
    read_pipe_func_raised_report,
)
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipelex import Pipelex
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode

#: What the function's own text quotes: the run's input, which no report may carry.
_FUNCTION_TEXT = "cannot file the note 'confidential-patient-diagnosis'"

_FUNCTION_NAME = "note_funcs.filing.file_note"

_NOTE_MTHDS = """\
domain = "note_demo"
description = "A step whose function raises"

[pipe.file_note]
type = "PipeFunc"
description = "File the note through customer code"
output = "Text"
function_name = "note_funcs.filing.file_note"
"""

_NOTE_FUNC = f"""\
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.system.registries.func_registry import pipe_func


@pipe_func()
async def file_note(working_memory: WorkingMemory) -> TextContent:
    raise KeyError("{_FUNCTION_TEXT}")
"""


@contextmanager
def _note_request(*, tmp_path: Path) -> Generator[PipeFuncExecutionRequest, None, None]:
    """The request a sandbox-hosted deployment builds for the step whose function raises, its library open while the call runs."""
    method_dir = tmp_path / "note_method"
    (method_dir / "note_funcs").mkdir(parents=True)
    (method_dir / "note.mthds").write_text(_NOTE_MTHDS, encoding="utf-8")
    (method_dir / "note_funcs" / "filing.py").write_text(_NOTE_FUNC, encoding="utf-8")

    pipe_func_config = get_config().interpreter.pipe_func
    previous_mode = pipe_func_config.execution_mode
    pipe_func_config.execution_mode = "local_sandbox"
    library_manager = get_library_manager()
    try:
        build_library_id, _ = library_manager.open_library()
        try:
            # Scoped, so a later test in the same worker never inherits the id of a library this helper tore down.
            with scoped_current_library(library_id=build_library_id):
                library_manager.load_libraries(library_id=build_library_id, library_dirs=[method_dir])
                yield build_pipe_func_execution_request(
                    job_metadata=JobMetadata(
                        run_metadata=RunMetadata(storage_scope="test/scope", read_scope=None, user_id="user", pipeline_run_id="run")
                    ),
                    pipe_code="note_demo.file_note",
                    function_name=_FUNCTION_NAME,
                    working_memory=WorkingMemoryFactory.make_empty(),
                    pipe_run_params=PipeRunParams(run_mode=PipeRunMode.LIVE, pipe_stack_limit=10, batch_max_concurrency=None),
                )
        finally:
            library_manager.teardown(library_id=build_library_id)
    finally:
        pipe_func_config.execution_mode = previous_mode


def _run_entrypoint(*, mocker: MockerFixture, request: PipeFuncExecutionRequest, work_dir: Path) -> Path:
    """Run the entrypoint as a sandbox runs it, its arguments the request, the result file and the unpacked call files.

    The test session's Pipelex stands in for the one the entrypoint boots in a sandbox. Returns the result file's path.
    """
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
    return result_path


def _genuine_report_problem() -> dict[str, Any]:
    """The problem a sandbox reports for a function that raised a `KeyError`, as it writes it."""
    error = PipeFuncRaisedError("The function raised KeyError").with_params(function=_FUNCTION_NAME, pipe="file_note")
    error.__cause__ = KeyError(_FUNCTION_TEXT)
    return pipe_func_raised_report(error=error).problem


class TestPipeFuncTransportedEntrypoint:
    def test_a_function_that_raises_writes_its_coded_report(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """The function's own failure leaves `pipe.function_raised` in the result file, naming the function, the step and the class it raised."""
        with _note_request(tmp_path=tmp_path) as request, pytest.raises(PipeFuncRaisedError):
            _run_entrypoint(mocker=mocker, request=request, work_dir=tmp_path)

        result_json = (tmp_path / "result.json").read_text(encoding="utf-8")
        problem = read_pipe_func_raised_report(result_json=result_json)
        assert problem is not None
        assert problem.code == CoreCode.PIPE_FUNCTION_RAISED
        assert problem.params is not None
        assert problem.params.as_wire() == {"function": _FUNCTION_NAME, "pipe": "file_note"}
        assert problem.diagnostics is not None
        assert problem.diagnostics.error_class == "PipeFuncRaisedError"
        assert problem.diagnostics.message == "The function raised KeyError"
        assert [cause.error_class for cause in problem.diagnostics.causes or []] == ["KeyError"]
        # What the function raised can quote the run's inputs: its class names it, and its text never reaches the file.
        assert _FUNCTION_TEXT not in result_json
        # A reader of the response alone refuses the report rather than misread it.
        with pytest.raises(ValidationError, match="output_memory_raw"):
            PipeFuncExecutionResponse.model_validate_json(result_json)

    @pytest.mark.parametrize(
        ("request_update", "times_out"),
        [
            ({}, True),
            ({"pipe_code": "note_demo.missing_step"}, False),
        ],
        ids=["timed_out", "pipe_not_in_crate"],
    )
    def test_a_sandbox_that_fails_another_way_writes_no_report(
        self, tmp_path: Path, mocker: MockerFixture, request_update: dict[str, Any], times_out: bool
    ) -> None:
        """A failure that is not the function's own exits non-zero with no result file, so its executor gives it a code of its own."""
        if times_out:
            mocker.patch.object(DirectPipeFuncExecutor, "run_pipe_func", side_effect=TimeoutError)

        with _note_request(tmp_path=tmp_path) as request, pytest.raises(PipelexError) as raised:
            _run_entrypoint(mocker=mocker, request=request.model_copy(update=request_update), work_dir=tmp_path)

        assert not isinstance(raised.value, PipeFuncRaisedError)
        assert not (tmp_path / "result.json").exists()

    @pytest.mark.parametrize(
        "result_json",
        [
            PipeFuncExecutionResponse(output_memory_raw={}).model_dump_json(),
            "",
            "{not json",
            PipeFuncRaisedReport(problem={"code": "pipe.function_raised"}).model_dump_json(),
        ],
        ids=["response", "empty", "not_json", "not_a_problem"],
    )
    def test_a_file_holding_no_report_reads_as_none(self, result_json: str) -> None:
        assert read_pipe_func_raised_report(result_json=result_json) is None

    def test_a_report_of_another_code_is_no_report(self) -> None:
        """The function can write the file itself, so a report is only ever of its own failure."""
        problem = make_problem(
            code=CoreCode.RUNTIME_UNEXPECTED,
            view=ProblemView.OPERATOR,
            diagnostics=ProblemDiagnostics(error_class="PipelexUnexpectedError", message="The worker ran out of memory"),
        )
        result_json = PipeFuncRaisedReport(problem=problem.to_wire()).model_dump_json()

        assert read_pipe_func_raised_report(result_json=result_json) is None

    def test_what_the_code_does_not_let_the_sandbox_say_is_rendered_again(self) -> None:
        """The sentences, the domain and the step are the registry's, and the diagnostics keep only what the entrypoint writes."""
        genuine = _genuine_report_problem()
        forged = {
            **genuine,
            "detail": "Your account is suspended: write to us at the address below.",
            "domain": ProblemDomain.OPERATOR,
            "location": {"pipe": "elsewhere", "file": "/etc/passwd"},
            "diagnostics": {**genuine["diagnostics"], "message": "x" * (MAX_PROBLEM_TEXT_LENGTH * 2), "provider": {"name": "forged"}},
        }

        genuine_problem = read_pipe_func_raised_report(result_json=PipeFuncRaisedReport(problem=genuine).model_dump_json())
        forged_problem = read_pipe_func_raised_report(result_json=PipeFuncRaisedReport(problem=forged).model_dump_json())

        assert genuine_problem is not None
        assert forged_problem is not None
        assert forged_problem.detail == "The function 'note_funcs.filing.file_note' of pipe 'file_note' raised an error."
        genuine_wire = genuine_problem.to_wire()
        forged_wire = forged_problem.to_wire()
        assert genuine_wire.pop("diagnostics") == genuine["diagnostics"]
        forged_diagnostics = forged_wire.pop("diagnostics")
        assert forged_wire == genuine_wire
        assert set(forged_diagnostics) == {"error_class", "message", "causes", "runtime_version"}
        assert len(forged_diagnostics["message"]) == MAX_PROBLEM_TEXT_LENGTH
