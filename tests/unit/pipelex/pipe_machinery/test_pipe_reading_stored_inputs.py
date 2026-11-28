from typing import Any, cast

import pytest
from pytest_mock import MockerFixture

from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipe_controllers.pipe_controller import PipeController
from pipelex.pipe_machinery import pipe_reading_stored_inputs
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipe_machinery.pipe_reading_stored_inputs import PipeReadingStoredInputs
from pipelex.pipe_operators.pipe_operator import PipeOperator
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipe_signature.pipe_signature import PipeSignature
from pipelex.system.job_metadata import JobMetadata, RunMetadata

_LOADER_NAME = "_load_stored_input_values"


class TestPipeReadingStoredInputs:
    @pytest.mark.parametrize("pipe_class", [PipeOperator, PipeController, PipeSignature], ids=["operator", "controller", "signature"])
    def test_every_running_pipe_shares_the_one_loader(self, pipe_class: type[PipeAbstract]) -> None:
        """Operators, controllers and signatures inherit the one implementation, which the fail-closed base does not hold."""
        shared_loader = vars(PipeReadingStoredInputs)[_LOADER_NAME]
        assert issubclass(pipe_class, PipeReadingStoredInputs)
        assert all(_LOADER_NAME not in vars(klass) for klass in pipe_class.__mro__[: pipe_class.__mro__.index(PipeReadingStoredInputs)])
        assert vars(PipeAbstract)[_LOADER_NAME] is not shared_loader

    @pytest.mark.asyncio
    async def test_loads_every_stored_value_under_the_roots_through_the_leaf(self, mocker: MockerFixture) -> None:
        """The gate's roots are handed to the leaf loader whole, with no read paths, under the run's execution mode."""
        loader = mocker.patch.object(pipe_reading_stored_inputs, "load_stored_values_through_leaf", new=mocker.AsyncMock(return_value=1))
        roots: dict[str, Any] = {"title": TextContent(url="pipelex-storage://org/title.txt", size=9, mime_type="text/plain", preview="Big")}
        job_metadata = JobMetadata(run_metadata=RunMetadata(storage_scope="test/scope", read_scope=None, user_id="test-user", pipeline_run_id="run"))
        pipe_run_params = PipeRunParamsFactory.make_run_params()

        loader_function = vars(PipeReadingStoredInputs)[_LOADER_NAME]
        await loader_function(cast("PipeReadingStoredInputs", None), roots=roots, job_metadata=job_metadata, pipe_run_params=pipe_run_params)

        loader.assert_awaited_once_with(roots=roots, read_paths=None, job_metadata=job_metadata, cogt_run_params=pipe_run_params.cogt_run_params)
