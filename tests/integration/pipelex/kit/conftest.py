import pytest


@pytest.fixture(params=["pipelex_language", "coding_standards"])
def agent_set(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    return request.param
