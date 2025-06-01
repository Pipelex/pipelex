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
