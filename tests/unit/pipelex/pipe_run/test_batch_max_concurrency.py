"""`batch_max_concurrency`: required, resolved from config once at run-params construction, then frozen.

The bound is PipeBatch's fan-out chunk size. Read live at fan-out time it would let a config
redeploy reshape an in-flight run's dispatch grouping; carried in the payload it cannot. These
tests pin the resolution table, the write-once discipline, and the no-default rule. (The field is
`frozen=True`, so a post-construction write is a *type* error — no runtime test needed for what the
checkers block.)
"""

from typing import Literal

import pytest
from pydantic import ValidationError

from pipelex.config import get_config
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory, resolve_batch_max_concurrency
from pipelex.system.pipe_run_mode import PipeRunMode


class TestBatchMaxConcurrency:
    @pytest.mark.parametrize(
        ("max_concurrency_setting", "expected_bound"),
        [
            ("unbounded", None),
            (1, 1),
            (8, 8),
            (100, 100),
        ],
    )
    def test_setting_translates_to_gather_bounded_argument(
        self,
        max_concurrency_setting: int | Literal["unbounded"],
        expected_bound: int | None,
    ) -> None:
        """The literal "unbounded" config maps to None (gather_bounded's no-bound sentinel); an int passes through.

        Guards the PipeBatch fan-out wiring against regressing to passing the raw "unbounded"
        string straight into gather_bounded, which would raise TypeError on its `max_concurrency < 1` check.
        """
        assert resolve_batch_max_concurrency(max_concurrency_setting) == expected_bound

    def test_omitting_the_bound_fails_loud_on_the_constructor(self) -> None:
        """No default: `None` also means an authored `max_concurrency = "unbounded"`, so a defaulted
        field would make "never written" indistinguishable from "authored unbounded" — and would
        point the omission at the dangerous direction (every branch at once). Same discipline as
        `run_mode` and `pipe_stack_limit`, which are required for the same reason.
        """
        with pytest.raises(ValidationError, match="batch_max_concurrency"):
            PipeRunParams(run_mode=PipeRunMode.DRY, pipe_stack_limit=20)  # type: ignore[call-arg] # pyright: ignore[reportCallIssue] # the static error is the runtime contract under test

    def test_omitting_the_bound_fails_loud_on_a_decoded_payload(self) -> None:
        """The wire boundary too: `PipeRunParams` rides a distributed backend's payloads, so a
        decode that drops the key must raise rather than silently resume unbounded.
        """
        with pytest.raises(ValidationError, match="batch_max_concurrency"):
            PipeRunParams.model_validate({"run_mode": PipeRunMode.DRY, "pipe_stack_limit": 20})

    def test_factory_freezes_the_live_config_value(self) -> None:
        execution_config = get_config().pipelex.pipeline_execution_config
        expected = resolve_batch_max_concurrency(execution_config.max_concurrency)

        run_params = PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY)

        assert run_params.batch_max_concurrency == expected

    def test_later_config_change_does_not_reach_existing_run_params(self) -> None:
        """The whole point: params built before a config edit keep the bound they were born with."""
        execution_config = get_config().pipelex.pipeline_execution_config
        original_setting = execution_config.max_concurrency
        try:
            execution_config.max_concurrency = 3
            run_params = PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY)
            assert run_params.batch_max_concurrency == 3

            execution_config.max_concurrency = 7
            assert run_params.batch_max_concurrency == 3
        finally:
            execution_config.max_concurrency = original_setting
