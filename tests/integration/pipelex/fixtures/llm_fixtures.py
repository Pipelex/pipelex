"""LLM-related test fixtures."""

import pytest

from pipelex.cogt.llm.llm_job_components import LLMJobParams
from pipelex.hub import get_model_deck


def is_llm_handle_supported(llm_handle: str) -> bool:
    """Check if an LLM handle is available in the current model deck."""
    model_deck = get_model_deck()
    return model_deck.is_handle_defined(llm_handle)


@pytest.fixture(
    params=[
        # "llm_for_testing_gen_text",
        # "llm_for_testing_gen_object",
        "llm_for_creative_writing",
    ],
)
def llm_preset_id(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    return request.param


@pytest.fixture(
    params=[
        # "gpt-4o",
        "gpt-4o-mini",
        # "gpt-4-5-preview",
        # "o1",
        # "o1-mini",
        # "o3",
        # "o3-mini",
        # "gpt-5-mini",
        # "gpt-5-nano",
        # "gpt-5-chat",
        # "gpt-5",
        # "mistral-large",
        # "ministral-3b",
        # "ministral-8b",
        # "mistral-medium",
        # "mistral-medium-2508",
        # "bedrock-mistral-large",
        # "bedrock-claude-3-7-sonnet",
        # "bedrock-meta-llama-3-3-70b-instruct",
        # "bedrock-nova-pro",
        # "pipelex/gpt-4o-mini",
        # "pipelex/claude-3.7-sonnet",
        # "pipelex/gemini-2.0-flash-vertex",
        # "pipelex/gemini-2.0-flash",
        # "claude-4.5-sonnet",
        # "claude-4.1-opus",
        # "claude-4.5-haiku",
        # "claude-4.5-sonnet",
        # "grok-3",
        # "grok-3-mini",
        # "gemini-2.5-flash-lite",
        # "gemini-2.5-flash",
        # "gemini-2.5-pro",
        # "openai/gpt-oss-120b",
        # "meta-llama/llama-4-scout-17b-16e-instruct",
        # "meta-llama/llama-4-maverick-17b-128e-instruct",
        # "moonshotai/kimi-k2-instruct-0905",
    ],
)
def llm_handle(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    llm_handle_param = request.param
    if not is_llm_handle_supported(llm_handle_param):
        pytest.skip(f"LLM handle '{llm_handle_param}' not available on the active routing profile")
    return llm_handle_param


@pytest.fixture(
    params=[
        # "o1",
        # "o3-mini",
        # "gpt-4o",
        # "gpt-4o-mini",
        # "gpt-5-mini",
        # "gpt-5-nano",
        # "gpt-5-chat",
        # "gpt-4-5-preview",
        # "claude-3-haiku",
        # "claude-3.5-sonnet",
        # "claude-3.7-sonnet",
        # "claude-4.1-opus",
        # "pixtral-12b",
        # "pixtral-large",
        # "gemini-2.5-pro",
        # "gemini-2.5-flash",
        # "mistral-small3.1",
        # "mistral-medium",
        # "mistral-medium-2508",
        "gemini-2.5-flash-lite",
        # "gemini-2.5-flash",
        # "gemini-2.5-pro",
        # "qwen3:8b",
    ],
)
def llm_handle_for_vision(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    llm_handle_param = request.param
    if not is_llm_handle_supported(llm_handle_param):
        pytest.skip(f"LLM handle '{llm_handle_param}' not available on the active routing profile")
    return llm_handle_param


@pytest.fixture(
    params=[
        "gpt-5-mini-2025-08-07",
        # "gpt-5-nano-2025-08-07",
        # "gpt-5-chat-2025-08-07",
        # "gpt-5-mini",
        # "gpt-5-nano",
        # "gpt-5-chat-latest",
        # "gpt-5",
        "gpt-4o-mini",
        # "open-mixtral-8x7b",
        # "google/gemini-2.0-flash",
        # "google/gemini-2.5-pro-preview-05-06",
        # "google/gemini-2.5-pro-preview-06-05",  # not yet on VertexAI
        # "google/gemini-2.5-flash-preview-04-17",
        # "google/gemini-2.5-flash-preview-05-20",
        # "o1",
        # "o4-mini",
        # "bedrock-mistral-large",
        # "sonar",
        # "claude-3-7-sonnet-20250219",
        # "claude-sonnet-4-20250514",
        # "claude-opus-4-20250514",
        # "claude-opus-4-1-20250805",
        # "us.anthropic.claude-sonnet-4-20250514-v1:0",
        # "us.anthropic.claude-opus-4-20250514-v1:0",
        # "us.anthropic.claude-opus-4-1-20250805-v1:0",
        # "sonar",
        # "sonar-pro",
        # "gemma3:4b",
        # "llama4:scout",
        # "mistral-small3.1:24b",
        # "qwen3:8b",
        # "blackboxai/openai/gpt-4o-mini",
        # "pipelex/openai/gpt-4o-mini",
        # "openai/gpt-4o-mini",
        # "grok-3",
        # "grok-3-mini",
        # "pipelex/gpt-4o-mini",
        # "pipelex/claude-3.7-sonnet",
        # "vertex_ai/gemini-2.0-flash",
    ],
)
def llm_id(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    llm_handle_param = request.param
    if not is_llm_handle_supported(llm_handle_param):
        pytest.skip(f"LLM handle '{llm_handle_param}' not available on the active routing profile")
    return llm_handle_param


@pytest.fixture(
    params=[
        LLMJobParams(
            temperature=0.5,
            max_tokens=None,
            seed=None,
        ),
    ],
)
def llm_job_params(request: pytest.FixtureRequest) -> LLMJobParams:
    assert isinstance(request.param, LLMJobParams)
    return request.param
