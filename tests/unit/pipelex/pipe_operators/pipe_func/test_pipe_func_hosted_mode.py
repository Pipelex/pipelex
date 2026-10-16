from typing import Callable

import pytest
from pydantic import ValidationError
from pytest_mock import MockerFixture

from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.method_trees.tree_files import TreeFileEntry
from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.core.stuffs.list_content import ListContent
from pipelex.interpreter_hub import get_library_manager
from pipelex.libraries.library_crate import SUBMITTED_PYTHON_ROOT_KEY
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.func.pipe_func import PipeFunc
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.validation_error_types import PipeValidationErrorType

_SANDBOX_FUNCTION_NAME = "sandbox_funcs.totals.compute_totals"

_SANDBOX_MODULE = """\
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.system.registries.func_registry import pipe_func


@pipe_func()
def compute_totals(working_memory: WorkingMemory) -> TextContent:
    return TextContent(text="total")
"""


def _make_pipe_func(*, output: str = "native.Text") -> PipeFunc:
    blueprint = PipeFuncBlueprint(
        description="Hosted-mode case: the function lives only in the files a sandbox receives, never in this process.",
        inputs={},
        output=output,
        function_name=_SANDBOX_FUNCTION_NAME,
    )
    return PipeFactory[PipeFunc].make_from_blueprint(domain_code="hosted_test", pipe_code="hosted_pipe", blueprint=blueprint)


def _capture_submitted_files(*, library_id: str, files: dict[str, TreeFileEntry] | None, mocker: MockerFixture) -> None:
    library_manager = get_library_manager()
    original = library_manager.get_pipe_func_files

    def get_pipe_func_files(*, library_id: str, root_key: str) -> dict[str, TreeFileEntry] | None:
        if root_key == SUBMITTED_PYTHON_ROOT_KEY:
            return files
        return original(library_id=library_id, root_key=root_key)

    mocker.patch.object(library_manager, "get_pipe_func_files", side_effect=get_pipe_func_files)
    assert library_id


class TestPipeFuncHostedMode:
    def test_a_flat_function_name_is_refused_in_every_mode(self, mocker: MockerFixture):
        """A flat name, the key of the retired registry, is refused as the blueprint is read, naming the migration."""
        for is_hosted in (False, True):
            mocker.patch("pipelex.pipe_operators.func.pipe_func.is_pipe_func_sandbox_hosted", return_value=is_hosted)
            with pytest.raises(ValidationError, match="pipelex fix function-names"):
                PipeFuncBlueprint(description="A flat name", inputs={}, output="native.Text", function_name="compute_totals")

    def test_hosted_validation_reads_the_submitted_files(self, load_empty_library: Callable[[], str], mocker: MockerFixture):
        """In sandbox-hosted mode a step parsed from a string is validated from the files submitted with it, never imported."""
        library_id = load_empty_library()
        mocker.patch("pipelex.pipe_operators.func.pipe_func.is_pipe_func_sandbox_hosted", return_value=True)
        _capture_submitted_files(library_id=library_id, files={"sandbox_funcs/totals.py": _SANDBOX_MODULE}, mocker=mocker)

        _make_pipe_func().validate_output_with_library()

    @pytest.mark.parametrize(
        ("files", "expected_message"),
        [
            (None, "sandbox_funcs/totals.py"),
            ({"sandbox_funcs/totals.py": _SANDBOX_MODULE.replace("@pipe_func()\n", "")}, "not decorated with @pipe_func()"),
            ({"json.py": "X = 1\n", "sandbox_funcs/totals.py": _SANDBOX_MODULE}, "standard-library module 'json'"),
        ],
        ids=["module_not_submitted", "function_unmarked", "module_shadows_stdlib"],
    )
    def test_hosted_validation_refuses_what_the_submitted_files_cannot_prove(
        self,
        files: dict[str, TreeFileEntry] | None,
        expected_message: str,
        load_empty_library: Callable[[], str],
        mocker: MockerFixture,
    ):
        """A missing module, an unmarked function or a shadowing module is refused at validation, naming the step."""
        library_id = load_empty_library()
        mocker.patch("pipelex.pipe_operators.func.pipe_func.is_pipe_func_sandbox_hosted", return_value=True)
        _capture_submitted_files(library_id=library_id, files=files, mocker=mocker)

        with pytest.raises(PipeValidationError) as raised:
            _make_pipe_func().validate_output_with_library()

        assert raised.value.error_type == PipeValidationErrorType.PIPE_FUNC_FUNCTION_REFUSED
        assert raised.value.pipe_code == "hosted_pipe"
        assert expected_message in str(raised.value)

    @pytest.mark.asyncio
    async def test_hosted_dry_run_honors_output_multiplicity(self, load_empty_library: Callable[[], str], mocker: MockerFixture):
        """Hosted dry run must mock a list-shaped output for a multiplicity output like `Text[]`, without importing the function."""
        load_empty_library()
        mocker.patch("pipelex.pipe_operators.func.pipe_func.is_pipe_func_sandbox_hosted", return_value=True)
        pipe_func = _make_pipe_func(output="native.Text[]")

        pipe_output = await pipe_func._dry_run_operator_pipe(  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]
            job_metadata=JobMetadata(run_metadata=RunMetadata(storage_scope="test/scope", read_scope=None, user_id="user", pipeline_run_id="run")),
            working_memory=WorkingMemoryFactory.make_empty(),
            pipe_run_params=PipeRunParams(run_mode=PipeRunMode.DRY, pipe_stack_limit=10, batch_max_concurrency=None),
        )

        content = pipe_output.working_memory.get_main_stuff().content
        assert isinstance(content, ListContent)
