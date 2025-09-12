import pytest

from pipelex.cogt.imgg.imgg_handle import ImggHandle
from pipelex.cogt.llm.llm_job_components import LLMJobParams
from pipelex.cogt.llm.llm_models.llm_family import LLMCreator, LLMFamily
from pipelex.cogt.llm.llm_models.llm_platform import LLMPlatform


@pytest.fixture(
    params=[
        "llm_for_testing_gen_text",
        "llm_for_testing_gen_object",
        "llm_for_creative_writing",
    ]
)
def llm_preset_id(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    return request.param


# TODO: make it efficient to also test multiple platforms like openai/azure and mistral/anthropic/bedrock
@pytest.fixture(
    params=[
        # "o1",
        # "gpt-4o",
        # "gpt-4o-mini",
        # "gpt-4-5-preview",
        # "o1-mini",
        # "o3-mini",
        # "gpt-5-mini", # TODO: fix this
        # "gpt-5-nano", # TODO: fix this
        # "best-gpt",
        # "claude-3-haiku",
        # "claude-3-5-sonnet",
        # "claude-3-7-sonnet",
        # "best-claude",
        # "mistral-large",
        # "ministral-3b",
        # "ministral-8b",
        # "pixtral-12b",
        # "pixtral-large",
        # "gemini-1-5-pro",
        # "gemini-1-5-flash",
        # "gemini-2-flash",
        # "gemini-2-pro",
        # "gemini-2-5-flash",
        # "gemini-2-5-pro",
        # "bedrock-mistral-large",
        # "bedrock-claude-3-7-sonnet",
        # "bedrock-meta-llama-3-3-70b-instruct",
        # "bedrock-nova-pro",
        # "sonar",
        # "pipelex/gpt-4o-mini",
        # "pipelex/claude-3.7-sonnet",
        # "pipelex/gemini-2.0-flash-vertex",
        "pipelex/gemini-2.0-flash",
    ]
)
def llm_handle(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    return request.param


@pytest.fixture(
    params=[
        # "o1",
        # "o3-mini",
        # "gpt-4o",
        "gpt-4o-mini",
        # "gpt-5-mini",
        # "gpt-5-nano",
        # "gpt-5-chat",
        # "gpt-4-5-preview",
        # "claude-3-haiku",
        # "claude-3-5-sonnet",
        # "claude-3-7-sonnet",
        # "claude-4-1-opus",
        # "pixtral-12b",
        # "pixtral-large",
        # "gemini-1-5-pro",
        # "gemini-1-5-flash",
        # "gemini-2-flash",
        # "gemini-2-pro",
        # "gemini-2-5-pro",
        # "gemini-2-5-flash",
        # "mistral-small3.1",
        # "qwen3:8b",
    ]
)
def llm_handle_for_vision(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    return request.param


@pytest.fixture(
    params=[
        # LLMFamily.GPT_4,
        # LLMFamily.GPT_4O,
        LLMFamily.GPT_5,
        # LLMFamily.GPT_4_5,
        # LLMFamily.GPT_4_1,
        # LLMFamily.O_SERIES,
        # LLMFamily.CLAUDE_3_7,
        # LLMFamily.CLAUDE_4,
        # LLMFamily.CLAUDE_4_1,
        # LLMFamily.PERPLEXITY_SEARCH,
        # LLMFamily.PERPLEXITY_REASONING,
        # LLMFamily.PERPLEXITY_RESEARCH,
        # LLMFamily.PERPLEXITY_DEEPSEEK,
        # LLMFamily.GEMINI,
        # LLMFamily.GEMMA,
        # LLMFamily.CUSTOM_BLACKBOXAI,
    ]
)
def llm_family(request: pytest.FixtureRequest) -> LLMFamily:
    assert isinstance(request.param, LLMFamily)
    return request.param


@pytest.fixture(
    params=[
        # LLMCreator.ALIBABA,
        # LLMCreator.AMAZON,
        # LLMCreator.ANTHROPIC,
        # LLMCreator.DEEPSEEK,
        # LLMCreator.GOOGLE,
        LLMCreator.OPENAI,
        # LLMCreator.META,
        # LLMCreator.MISTRAL,
        # LLMCreator.PERPLEXITY,
    ]
)
def llm_creator(request: pytest.FixtureRequest) -> LLMCreator:
    assert isinstance(request.param, LLMCreator)
    return request.param


# TODO: build llm_id/platform combos dynalically from config data
@pytest.fixture(
    params=[
        # LLMPlatform.ANTHROPIC,
        # LLMPlatform.AZURE_OPENAI,
        # LLMPlatform.BEDROCK,
        # LLMPlatform.BEDROCK_ANTHROPIC,
        # LLMPlatform.MISTRAL,
        LLMPlatform.OPENAI,
        # LLMPlatform.PERPLEXITY,
        # LLMPlatform.VERTEXAI,
        # LLMPlatform.XAI,
        # LLMPlatform.CUSTOM_LLM,
    ]
)
def llm_platform(request: pytest.FixtureRequest) -> LLMPlatform:
    assert isinstance(request.param, LLMPlatform)
    return request.param


@pytest.fixture(
    params=[
        # "gpt-5-mini-2025-08-07",
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
    ]
)
def llm_id(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    return request.param


@pytest.fixture(
    params=[
        LLMJobParams(
            temperature=0.5,
            max_tokens=None,
            seed=None,
        ),
    ]
)
def llm_job_params(request: pytest.FixtureRequest) -> LLMJobParams:
    assert isinstance(request.param, LLMJobParams)
    return request.param


@pytest.fixture(
    params=[
        # ImggHandle.FLUX_1_PRO_LEGACY,
        # ImggHandle.FLUX_1_1_PRO,
        # ImggHandle.FLUX_1_1_ULTRA,
        ImggHandle.SDXL_LIGHTNING,
        # ImggHandle.OPENAI_GPT_IMAGE_1,
    ]
)
def imgg_handle(request: pytest.FixtureRequest) -> ImggHandle:
    assert isinstance(request.param, ImggHandle)
    return request.param
