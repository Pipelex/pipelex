import pytest


@pytest.fixture(params=["anthropic", "mistral", "meta", "amazon"])
def bedrock_provider(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    return request.param


@pytest.fixture(params=["us-east-1", "us-west-2"])
def bedrock_region_name(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    return request.param
