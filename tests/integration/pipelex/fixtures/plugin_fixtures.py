"""Plugin-related test fixtures."""

import pytest

from pipelex.plugins.plugin_sdk_registry import Plugin


@pytest.fixture(
    params=[
        Plugin(sdk="openai", backend="openai"),
        Plugin(sdk="azure_openai", backend="azure_openai"),
    ],
)
def plugin_for_openai(request: pytest.FixtureRequest) -> Plugin:
    assert isinstance(request.param, Plugin)
    return request.param


@pytest.fixture(
    params=[
        Plugin(sdk="anthropic", backend="anthropic"),
        Plugin(sdk="bedrock_anthropic", backend="bedrock_anthropic"),
    ],
)
def plugin_for_anthropic(request: pytest.FixtureRequest) -> Plugin:
    assert isinstance(request.param, Plugin)
    return request.param


@pytest.fixture(
    params=[
        # None,
        "https://inference.pipelex.com/v1",
    ],
)
def openai_endpoint(request: pytest.FixtureRequest) -> str | None:
    assert isinstance(request.param, str) or request.param is None
    return request.param
