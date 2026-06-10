"""Pin the ``CogtRunParams`` carrier shape on ``PipeRunParams`` (eng review D2).

``run_mode`` lives ONLY inside the nested ``cogt_run_params`` — ``PipeRunParams.run_mode`` is a
read-only delegating property, the factory is the single writer, and a stale ``run_mode=`` kwarg
must fail loudly instead of silently building a LIVE-mode instance.
"""

import pytest
from pydantic import ValidationError
from pytest_mock import MockerFixture

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

    def test_forced_dry_coerces_live_and_warns(self, mocker: MockerFixture) -> None:
        """Keyless boot: a LIVE request is coerced to DRY with a warning; the mock-usage flag survives."""
        mocker.patch("pipelex.pipe_run.pipe_run_params_factory.is_dry_run_forced", return_value=True)
        warning_spy = mocker.patch("pipelex.pipe_run.pipe_run_params_factory.log.warning")

        run_params = PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.LIVE, is_mock_usage=True)

        assert run_params.run_mode.is_dry
        assert run_params.cogt_run_params.is_mock_usage
        warning_spy.assert_called_once()

    def test_stale_run_mode_kwarg_fails_loudly(self) -> None:
        """run_mode is a property, not a field: passing it as a kwarg must raise, not silently default to LIVE."""
        with pytest.raises(ValidationError):
            PipeRunParams(run_mode=PipeRunMode.DRY, pipe_stack_limit=20)  # type: ignore[call-arg] # pyright: ignore[reportCallIssue]

    def test_mock_usage_requires_dry_run_mode(self) -> None:
        """is_mock_usage is a sub-flag of DRY: setting it on a LIVE carrier is a contract violation."""
        with pytest.raises(ValidationError, match="is_mock_usage"):
            CogtRunParams(run_mode=PipeRunMode.LIVE, is_mock_usage=True)

    def test_mock_usage_rides_dry_run_mode(self) -> None:
        """The legal combination: DRY + is_mock_usage builds fine."""
        cogt_run_params = CogtRunParams(run_mode=PipeRunMode.DRY, is_mock_usage=True)

        assert cogt_run_params.run_mode.is_dry
        assert cogt_run_params.is_mock_usage
