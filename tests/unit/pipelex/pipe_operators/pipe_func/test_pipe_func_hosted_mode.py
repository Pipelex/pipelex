from collections.abc import Iterator
from typing import Callable

import pytest
from pydantic import ValidationError
from pytest_mock import MockerFixture

from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.method_trees.method_file_store import LOCAL_METHOD_FILES, HeldFile
from pipelex.core.method_trees.tree_bundle import TreeBundle, TreeBundleRef
from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.core.stuffs.list_content import ListContent
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.func import pipe_func as pipe_func_module
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


_HOLDER = "test_pipe_func_hosted_mode"


@pytest.fixture
def submit_files() -> Iterator[Callable[[dict[str, str] | None], PipeFunc]]:
    """Build the step as the library manager builds one parsed from a content string, with these files submitted beside it."""

    def _submit(files: dict[str, str] | None) -> PipeFunc:
        pipe_func = _make_pipe_func()
        if files is not None:
            tree = LOCAL_METHOD_FILES.hold_files(
                holder=_HOLDER, files={tree_path: HeldFile.of_bytes(data=source.encode("utf-8")) for tree_path, source in files.items()}
            )
            pipe_func.place_in_tree(tree_bundle=TreeBundle(tree=tree, tree_path=None))
        return pipe_func

    yield _submit
    LOCAL_METHOD_FILES.release(holder=_HOLDER)


class TestPipeFuncHostedMode:
    def test_a_flat_function_name_is_refused_in_every_mode(self, mocker: MockerFixture):
        """A flat name, the key of the retired registry, is refused as the blueprint is read, naming the migration."""
        for is_hosted in (False, True):
            mocker.patch("pipelex.pipe_operators.func.pipe_func.is_pipe_func_sandbox_hosted", return_value=is_hosted)
            with pytest.raises(ValidationError, match="pipelex fix function-names"):
                PipeFuncBlueprint(description="A flat name", inputs={}, output="native.Text", function_name="compute_totals")

    def test_hosted_validation_reads_the_submitted_files(
        self, load_empty_library: Callable[[], str], submit_files: Callable[[dict[str, str] | None], PipeFunc], mocker: MockerFixture
    ):
        """In sandbox-hosted mode a step parsed from a string is validated from the files submitted with it, never imported."""
        load_empty_library()
        mocker.patch("pipelex.pipe_operators.func.pipe_func.is_pipe_func_sandbox_hosted", return_value=True)

        submit_files({"sandbox_funcs/totals.py": _SANDBOX_MODULE}).validate_output_with_library()

    def test_a_step_built_from_a_crate_is_not_checked_again(self, load_empty_library: Callable[[], str], mocker: MockerFixture):
        """Its tree is named by digest only: the process that assembled the crate proved the function, and this one reads nothing."""
        load_empty_library()
        mocker.patch("pipelex.pipe_operators.func.pipe_func.is_pipe_func_sandbox_hosted", return_value=True)
        locate_spy = mocker.spy(pipe_func_module, "locate_in_files")
        pipe_func = _make_pipe_func()
        pipe_func.place_in_tree(tree_bundle=TreeBundleRef(tree_digest="sha256:" + "d" * 64, tree_path="main.mthds"))

        pipe_func.validate_output_with_library()

        assert locate_spy.call_count == 0

    def test_a_step_proves_its_function_once_however_often_it_is_validated(
        self, load_empty_library: Callable[[], str], submit_files: Callable[[dict[str, str] | None], PipeFunc], mocker: MockerFixture
    ):
        """A dependency package's step is validated as it is built and again with its consumer's library: it reads its module once."""
        load_empty_library()
        mocker.patch("pipelex.pipe_operators.func.pipe_func.is_pipe_func_sandbox_hosted", return_value=True)
        locate_spy = mocker.spy(pipe_func_module, "locate_in_files")
        pipe_func = submit_files({"sandbox_funcs/totals.py": _SANDBOX_MODULE})

        pipe_func.validate_once_built()
        pipe_func.validate_with_libraries()

        assert locate_spy.call_count == 1

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
        files: dict[str, str] | None,
        expected_message: str,
        load_empty_library: Callable[[], str],
        submit_files: Callable[[dict[str, str] | None], PipeFunc],
        mocker: MockerFixture,
    ):
        """A missing module, an unmarked function or a shadowing module is refused at validation, naming the step."""
        load_empty_library()
        mocker.patch("pipelex.pipe_operators.func.pipe_func.is_pipe_func_sandbox_hosted", return_value=True)
        pipe_func = submit_files(files)

        with pytest.raises(PipeValidationError) as raised:
            pipe_func.validate_output_with_library()

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
