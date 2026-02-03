import pytest


@pytest.fixture(params=["all"])
def agent_set(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    return request.param
