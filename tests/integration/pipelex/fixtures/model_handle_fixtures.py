"""Model-handle test fixtures."""

import pytest

from pipelex.plugins.model_handle import ModelHandle


@pytest.fixture(
    params=[
        ModelHandle(sdk="openai", backend="openai"),
        ModelHandle(sdk="azure_openai", backend="azure_openai"),
    ],
)
def model_handle_for_openai(request: pytest.FixtureRequest) -> ModelHandle:
    assert isinstance(request.param, ModelHandle)
    return request.param


@pytest.fixture(
    params=[
        ModelHandle(sdk="anthropic", backend="anthropic"),
        ModelHandle(sdk="bedrock_anthropic", backend="bedrock_anthropic"),
    ],
)
def model_handle_for_anthropic(request: pytest.FixtureRequest) -> ModelHandle:
    assert isinstance(request.param, ModelHandle)
    return request.param
