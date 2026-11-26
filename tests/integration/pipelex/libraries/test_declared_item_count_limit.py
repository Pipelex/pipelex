from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.config import get_config
from pipelex.core.pipes.declared_item_count_scope import scoped_max_declared_item_count
from pipelex.errors.problem import ProblemView
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_in_process import validate_bundles_in_process
from pipelex.system.exceptions import RunParameterError
from tests.integration.pipelex.libraries.test_data import DeclaredItemCountCases


def _refusal_params(*, exc: ValidateBundleError) -> list[dict[str, Any]]:
    """The parameters set on every item the verdict carries under the declared-count code."""
    problem = exc.to_problem(view=ProblemView.OPERATOR)
    refusals = [item for item in problem.errors or [] if item.code == PipelexErrorCode.DEPLOYMENT_DECLARED_COUNT_OVER_LIMIT]
    return [item.params.model_dump(exclude_none=True) if item.params is not None else {} for item in refusals]


@pytest.mark.asyncio(loop_scope="class")
class TestDeclaredItemCountLimit:
    @pytest.mark.parametrize(
        ("topic", "mthds_for_count", "slot"),
        DeclaredItemCountCases.SPELLINGS,
    )
    async def test_the_default_maximum_accepts_1000_and_refuses_1001(self, topic: str, mthds_for_count: Any, slot: str) -> None:
        """Each spelling of a declared count is held to the deployment's maximum of 1,000 at load."""
        report = await validate_bundles_in_process(mthds_contents=[mthds_for_count(1000)])
        assert report is not None, topic

        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundles_in_process(mthds_contents=[mthds_for_count(1001)])

        assert _refusal_params(exc=exc_info.value) == [{"slot": slot, "count": 1001, "limit": 1000}], topic

    @pytest.mark.parametrize(
        ("topic", "mthds_for_count", "slot"),
        DeclaredItemCountCases.SPELLINGS,
    )
    async def test_a_request_maximum_raises_the_deployments_and_never_lowers_it(
        self, mocker: MockerFixture, topic: str, mthds_for_count: Any, slot: str
    ) -> None:
        """The request's own maximum raises the deployment's, only up to the deployment's ceiling; a lower one changes nothing."""
        mocker.patch.object(get_config().interpreter.method_limits, "max_declared_item_count_ceiling", 2000)
        report = await validate_bundles_in_process(mthds_contents=[mthds_for_count(1500)], max_declared_item_count=2000)
        assert report is not None, topic

        report = await validate_bundles_in_process(mthds_contents=[mthds_for_count(5)], max_declared_item_count=4)
        assert report is not None, topic

        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundles_in_process(mthds_contents=[mthds_for_count(1500)], max_declared_item_count=1200)

        assert _refusal_params(exc=exc_info.value) == [{"slot": slot, "count": 1500, "limit": 1200}], topic

    async def test_a_scope_the_caller_opened_is_the_maximum_when_the_request_states_none(self) -> None:
        """`None` keeps the maximum already in force, a scope the host opened around the validation."""
        mthds = DeclaredItemCountCases.SPELLINGS[0][1](1500)
        with scoped_max_declared_item_count(maximum=1200), pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundles_in_process(mthds_contents=[mthds])

        assert [params["limit"] for params in _refusal_params(exc=exc_info.value)] == [1200]

    @pytest.mark.parametrize("maximum", [0, -1, 1_000_000_000, 1001])
    async def test_a_maximum_no_runtime_may_set_is_the_hosts_bug(self, maximum: int) -> None:
        """A maximum outside 1..999,999,999, or past the deployment's ceiling, is refused before any work, never read as a verdict."""
        with pytest.raises(RunParameterError, match=r"max_declared_item_count|maximum declared item count"):
            await validate_bundles_in_process(mthds_contents=[DeclaredItemCountCases.SPELLINGS[0][1](3)], max_declared_item_count=maximum)

    @pytest.mark.parametrize(
        ("topic", "mthds_for_count", "message"),
        DeclaredItemCountCases.PAST_ANY_RUNTIME,
    )
    async def test_a_count_past_every_runtimes_bound_is_an_invalid_verdict(self, topic: str, mthds_for_count: Any, message: str) -> None:
        """A count no maximum could allow is refused by the parser, whatever the request's maximum."""
        with pytest.raises(ValidateBundleError, match=message) as exc_info:
            await validate_bundles_in_process(mthds_contents=[mthds_for_count(10**12)])

        assert exc_info.value.validation_error_items(), topic

    @pytest.mark.parametrize("maximum", [1, 2])
    async def test_a_method_declaring_no_count_is_valid_under_a_maximum_below_the_dry_runs_default_lengths(
        self, mocker: MockerFixture, maximum: int
    ) -> None:
        """A variable list's dry-run length, three by default, is the dry run's own choice, shortened to the maximum."""
        mocker.patch.object(get_config().interpreter.method_limits, "max_declared_item_count", maximum)
        report = await validate_bundles_in_process(mthds_contents=[DeclaredItemCountCases.DECLARING_NO_COUNT])
        assert report is not None

    async def test_a_dry_run_building_more_mock_items_in_all_than_the_budget_is_an_invalid_verdict(self, mocker: MockerFixture) -> None:
        """Each slot of a batch over `Text[10]` whose branches output `Text[5]` is small; the validation's one budget counts them all."""
        mthds = DeclaredItemCountCases.BATCHING_LISTS(5)
        mocker.patch.object(get_config().interpreter.method_limits, "max_dry_run_mock_items", 1000)
        assert await validate_bundles_in_process(mthds_contents=[mthds]) is not None

        mocker.patch.object(get_config().interpreter.method_limits, "max_dry_run_mock_items", 40)
        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundles_in_process(mthds_contents=[mthds])

        problem = exc_info.value.to_problem(view=ProblemView.OPERATOR)
        budget_items = [item for item in problem.errors or [] if item.code == PipelexErrorCode.DEPLOYMENT_DRY_RUN_MOCK_BUDGET_EXCEEDED]
        assert budget_items
        assert all(item.params is not None and item.params.model_dump(exclude_none=True)["budget"] == 40 for item in budget_items)
