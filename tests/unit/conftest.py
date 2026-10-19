from collections.abc import Generator

import pytest
from pytest import FixtureRequest
from pytest_mock import MockerFixture

from pipelex.test_extras.required_params_sweep import assert_problems_carried_required_params, spy_on_problem_warnings


@pytest.fixture(autouse=True)
def problems_carry_their_required_params_fixture(request: FixtureRequest, mocker: MockerFixture) -> Generator[None, None, None]:
    """Fail a unit test during which a problem or an item was built without a parameter its code requires.

    The API server's unit tests run the same sweep (`pipelex.test_extras.required_params_sweep`): a test that builds
    such a problem on purpose says so with the `builds_problems_without_required_params` marker and its reason.
    """
    warn_spy = spy_on_problem_warnings(mocker=mocker)
    yield
    assert_problems_carried_required_params(warn_spy=warn_spy, keywords=request.keywords)
