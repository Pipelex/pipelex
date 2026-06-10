"""Pin the run-mode ownership on ``PipeRunParams`` and the derived ``CogtRunParams`` carrier.

``run_mode`` / ``is_mock_usage`` are direct fields of ``PipeRunParams`` (single stored copy); the
``cogt_run_params`` property mints the cogt-tier carrier from them on demand. The factory is the
single writer, and a stale ``cogt_run_params=`` kwarg must fail loudly instead of silently building
a LIVE-mode instance.
"""

import pytest
from pydantic import ValidationError
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory


class TestCogtRunParamsCarrier:
    def test_cogt_run_params_derives_from_run_mode_fields(self) -> None:
        """The carrier is minted from the stored fields — one copy of the facts."""
        run_params = PipeRunParams(run_mode=PipeRunMode.DRY, is_mock_usage=True, pipe_stack_limit=20)

        cogt_run_params = run_params.cogt_run_params
        assert cogt_run_params.run_mode.is_dry
        assert cogt_run_params.is_mock_usage
        assert cogt_run_params.run_mode is run_params.run_mode

    def test_factory_is_single_writer(self) -> None:
        """make_run_params resolves pipe_run_mode into the run_mode field."""
        run_params = PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY)

        assert run_params.run_mode.is_dry
        assert run_params.cogt_run_params.run_mode.is_dry

    def test_forced_dry_coerces_live_and_warns(self, mocker: MockerFixture) -> None:
        """Keyless boot: a LIVE request is coerced to DRY with a warning."""
        mocker.patch("pipelex.pipe_run.pipe_run_params_factory.is_dry_run_forced", return_value=True)
        warning_spy = mocker.patch("pipelex.pipe_run.pipe_run_params_factory.log.warning")

        run_params = PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.LIVE)

        assert run_params.run_mode.is_dry
        warning_spy.assert_called_once()

    def test_forced_dry_does_not_mask_mock_usage_violation(self, mocker: MockerFixture) -> None:
        """Keyless boot: LIVE + is_mock_usage still fails loud — the factory validates the REQUESTED
        mode first, so the coercion cannot silently turn an illegal request into a reportable dry run.
        """
        mocker.patch("pipelex.pipe_run.pipe_run_params_factory.is_dry_run_forced", return_value=True)

        with pytest.raises(ValueError, match="is_mock_usage"):
            PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.LIVE, is_mock_usage=True)

    def test_forced_dry_keeps_mock_usage_on_dry_request(self, mocker: MockerFixture) -> None:
        """Keyless boot: an explicit DRY + is_mock_usage request is legal and passes through untouched."""
        mocker.patch("pipelex.pipe_run.pipe_run_params_factory.is_dry_run_forced", return_value=True)

        run_params = PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY, is_mock_usage=True)

        assert run_params.run_mode.is_dry
        assert run_params.is_mock_usage

    def test_stale_cogt_run_params_kwarg_fails_loudly(self) -> None:
        """cogt_run_params is a derived property, not a field: passing it as a kwarg must raise.

        run_mode is supplied so the ONLY thing that can raise is the forbidden extra — without
        it the test would pass on the missing-required-field error even if extra="forbid" were
        dropped.
        """
        with pytest.raises(ValidationError, match="cogt_run_params"):
            PipeRunParams(
                run_mode=PipeRunMode.DRY,
                cogt_run_params=CogtRunParams(run_mode=PipeRunMode.DRY),  # type: ignore[call-arg] # pyright: ignore[reportCallIssue]
                pipe_stack_limit=20,
            )

    def test_run_mode_fields_are_frozen(self) -> None:
        """A post-construction DRY→LIVE flip (or mock-usage flip) must raise — it would bypass
        the construction validator and flow into real provider spend via the derived carrier.
        """
        run_params = PipeRunParams(run_mode=PipeRunMode.DRY, pipe_stack_limit=20)

        with pytest.raises(ValidationError, match="frozen"):
            run_params.run_mode = PipeRunMode.LIVE  # type: ignore[misc]  # the static read-only error is the runtime contract under test
        with pytest.raises(ValidationError, match="frozen"):
            run_params.is_mock_usage = True  # type: ignore[misc]  # the static read-only error is the runtime contract under test

    def test_mock_usage_requires_dry_on_pipe_run_params(self) -> None:
        """is_mock_usage is a sub-flag of DRY: setting it on a LIVE PipeRunParams is a contract violation."""
        with pytest.raises(ValidationError, match="is_mock_usage"):
            PipeRunParams(run_mode=PipeRunMode.LIVE, is_mock_usage=True, pipe_stack_limit=20)

    def test_mock_usage_requires_dry_on_carrier(self) -> None:
        """The wire carrier enforces the same rule at its own boundary (assignments cross the wire)."""
        with pytest.raises(ValidationError, match="is_mock_usage"):
            CogtRunParams(run_mode=PipeRunMode.LIVE, is_mock_usage=True)

    def test_mock_usage_rides_dry_run_mode(self) -> None:
        """The legal combination: DRY + is_mock_usage builds fine on both models."""
        cogt_run_params = CogtRunParams(run_mode=PipeRunMode.DRY, is_mock_usage=True)

        assert cogt_run_params.run_mode.is_dry
        assert cogt_run_params.is_mock_usage
