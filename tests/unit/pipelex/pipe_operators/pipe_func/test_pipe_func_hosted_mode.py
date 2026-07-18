from typing import Callable

import pytest
from pydantic import ValidationError
from pytest_mock import MockerFixture

from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.core.stuffs.list_content import ListContent
from pipelex.pipe_operators.func.pipe_func import PipeFunc
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipeline.job_metadata import JobMetadata

_UNREGISTERED = PipeFuncBlueprint(
    description="Hosted-mode case: function lives only in the sandbox, never in this process.",
    inputs={},
    output="native.Text",
    function_name="a_function_that_is_not_registered_here",
)


def _make_pipe_func() -> PipeFunc:
    return PipeFactory[PipeFunc].make_from_blueprint(
        domain_code="hosted_test",
        pipe_code="hosted_pipe",
        blueprint=_UNREGISTERED,
    )


class TestPipeFuncHostedMode:
    """In sandbox-hosted mode the PipeFunc validators accept a function that is absent from this
    process's func_registry; in local/direct mode the same input still raises.
    """

    def test_local_mode_rejects_unregistered_function(self, load_empty_library: Callable[[], str]):
        """Default (local) mode is unchanged: an unregistered function_name fails construction."""
        load_empty_library()
        with pytest.raises(ValidationError, match="not found in registry"):
            _make_pipe_func()

    def test_hosted_mode_accepts_unregistered_function_name(
        self,
        load_empty_library: Callable[[], str],
        mocker: MockerFixture,
    ):
        """Hosted mode skips the func_registry lookup, so the declared name is accepted verbatim."""
        load_empty_library()
        mocker.patch("pipelex.pipe_operators.func.pipe_func.is_pipe_func_sandbox_hosted", return_value=True)

        pipe_func = _make_pipe_func()

        assert pipe_func.function_name == "a_function_that_is_not_registered_here"

    def test_hosted_mode_skips_output_validation(
        self,
        load_empty_library: Callable[[], str],
        mocker: MockerFixture,
    ):
        """validate_output_with_library is a no-op in hosted mode (the sandbox validates for real)."""
        load_empty_library()
        mocker.patch("pipelex.pipe_operators.func.pipe_func.is_pipe_func_sandbox_hosted", return_value=True)

        pipe_func = _make_pipe_func()
        # Must not raise even though the function is not registered and its return type is unknown here.
        pipe_func.validate_output_with_library()

    @pytest.mark.asyncio
    async def test_hosted_dry_run_honors_output_multiplicity(
        self,
        load_empty_library: Callable[[], str],
        mocker: MockerFixture,
    ):
        """Hosted dry run must mock a list-shaped output for a multiplicity output like `Text[]`."""
        load_empty_library()
        mocker.patch("pipelex.pipe_operators.func.pipe_func.is_pipe_func_sandbox_hosted", return_value=True)
        blueprint = PipeFuncBlueprint(
            description="Hosted-mode multiplicity case: the mock output must be a list, not a scalar.",
            inputs={},
            output="native.Text[]",
            function_name="a_function_that_is_not_registered_here",
        )
        pipe_func = PipeFactory[PipeFunc].make_from_blueprint(
            domain_code="hosted_test",
            pipe_code="hosted_multiplicity_pipe",
            blueprint=blueprint,
        )

        pipe_output = await pipe_func._dry_run_operator_pipe(  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
            job_metadata=JobMetadata(user_id="user", pipeline_run_id="run"),
            working_memory=WorkingMemoryFactory.make_empty(),
            pipe_run_params=PipeRunParams(run_mode=PipeRunMode.DRY, pipe_stack_limit=10),
        )

        content = pipe_output.working_memory.get_main_stuff().content
        assert isinstance(content, ListContent)
