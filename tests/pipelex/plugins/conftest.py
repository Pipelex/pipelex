import pytest

from pipelex.cogt.llm.llm_models.llm_platform import LLMPlatform


@pytest.fixture(params=LLMPlatform.list_openai_related())
def llm_platform_for_openai_sdk(request: pytest.FixtureRequest) -> LLMPlatform:
    assert isinstance(request.param, LLMPlatform)
    return request.param


@pytest.fixture(params=LLMPlatform.list_anthropic_related())
def llm_platform_for_anthropic_sdk(request: pytest.FixtureRequest) -> LLMPlatform:
    assert isinstance(request.param, LLMPlatform)
    return request.param


@pytest.fixture(params=["anthropic", "mistral", "meta", "amazon"])
def bedrock_provider(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    return request.param


@pytest.fixture(params=["us-east-1", "us-west-2"])
def bedrock_region_name(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    return request.param
