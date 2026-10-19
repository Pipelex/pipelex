"""The sweep that fails a test during which a problem or an item was built lacking a parameter its code requires.

Whatever a test makes the runtime or the runner answer, a refusal, an item of a verdict or a run's failure, is built by
`make_problem` or `make_problem_item`, which log each required parameter a raise site did not give
(`pipelex.errors.problem.missing_required_params`). The library's unit tests and the API server's run every test under
this sweep, from an autouse fixture of their `conftest.py` that spies before the test and asserts after it, so a raise
site any test reaches cannot answer less than its code promises. A test that builds such a problem on purpose, to check
something its parameters do not decide, or that reaches a raise site which cannot know a fact, says so with the marker
`REQUIRED_PARAMS_OPT_OUT_MARKER` and its reason.
"""

from collections.abc import Mapping
from typing import Any

from pytest_mock import MockerFixture, MockType

from pipelex.errors import problem as problem_module
from pipelex.errors.problem import MISSING_REQUIRED_PARAMS_MESSAGE

# The marker a test carries, with a `reason`, when it builds a problem lacking a required parameter on purpose.
REQUIRED_PARAMS_OPT_OUT_MARKER = "builds_problems_without_required_params"


def spy_on_problem_warnings(*, mocker: MockerFixture) -> MockType:
    """Spy, for the test's duration, on the warnings the problem builders log, before the test runs.

    Args:
        mocker: The test's mocker, which removes the spy when the test ends.
    """
    return mocker.spy(problem_module, "_warn")


def assert_problems_carried_required_params(*, warn_spy: MockType, keywords: Mapping[str, Any]) -> None:
    """Fail the test when a problem or an item built during it lacked a required parameter, unless the test opts out.

    Args:
        warn_spy: The spy `spy_on_problem_warnings` set before the test ran.
        keywords: The test's keywords, where a marker on the test, its class or its module appears by name.
    """
    if REQUIRED_PARAMS_OPT_OUT_MARKER in keywords:
        return
    lacking = [call.kwargs["fields"] for call in warn_spy.call_args_list if call.kwargs.get("message") == MISSING_REQUIRED_PARAMS_MESSAGE]
    assert not lacking, f"A problem or an item was built without a parameter its code requires: {lacking}"
