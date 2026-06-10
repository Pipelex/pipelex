"""Pin the ``CogtRunParams`` carrier shape on ``PipeRunParams`` (eng review D2).

``run_mode`` lives ONLY inside the nested ``cogt_run_params`` — ``PipeRunParams.run_mode`` is a
read-only delegating property, the factory is the single writer, and a stale ``run_mode=`` kwarg
must fail loudly instead of silently building a LIVE-mode instance.
"""

import pytest
from pydantic import ValidationError

from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory


class TestCogtRunParamsCarrier:
    def test_run_mode_property_delegates_to_cogt_run_params(self) -> None:
        """The pipe-tier read goes through the single copy on cogt_run_params."""
        run_params = PipeRunParams(cogt_run_params=CogtRunParams(run_mode=PipeRunMode.DRY), pipe_stack_limit=20)

        assert run_params.run_mode.is_dry
        assert run_params.run_mode is run_params.cogt_run_params.run_mode

    def test_factory_is_single_writer(self) -> None:
        """make_run_params resolves pipe_run_mode into the nested CogtRunParams."""
        run_params = PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY)

        assert run_params.cogt_run_params.run_mode.is_dry

    def test_stale_run_mode_kwarg_fails_loudly(self) -> None:
        """run_mode is a property, not a field: passing it as a kwarg must raise, not silently default to LIVE."""
        with pytest.raises(ValidationError):
            PipeRunParams(run_mode=PipeRunMode.DRY, pipe_stack_limit=20)  # type: ignore[call-arg] # pyright: ignore[reportCallIssue]
