
import pytest

from pipelex.cogt.llm.llm_job_components import LLMJobParams
from pipelex.plugins.plugin_sdk_registry import Plugin


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
        # "o1",
        # "gpt-4o",
        # "gpt-4o-mini",
        # "gpt-4-5-preview",
        # "o1-mini",
        # "o3-mini",
        # "gpt-5-mini", # TODO: fix this
        # "gpt-5-nano", # TODO: fix this
        # "claude-3-haiku",
        # "claude-3-5-sonnet",
        # "claude-3-7-sonnet",
        # "mistral-large",
        # "ministral-3b",
        # "ministral-8b",
        # "mistral-medium",
        # "mistral-medium-2508",
        # "pixtral-12b",
        # "pixtral-large",
        # "bedrock-mistral-large",
        # "bedrock-claude-3-7-sonnet",
        # "bedrock-meta-llama-3-3-70b-instruct",
        # "bedrock-nova-pro",
        # "sonar",
        # "pipelex/gpt-4o-mini",
        # "pipelex/claude-3.7-sonnet",
        # "pipelex/gemini-2.0-flash-vertex",
        # "pipelex/gemini-2.0-flash",
        # "llm_to_engineer",
        # "gpt-5-nano",
        # "gpt-4o-mini",
        # "gpt-5-mini",
        # "gpt-5-chat",
        "claude-4-sonnet",
        # "claude-4.1-opus",
        # "claude-3.5-sonnet",
        # "claude-3.5-sonnet-v2"
        # "claude-3.7-sonnet",
        # "grok-3",
        # "grok-3-mini",
        # "base-claude",
        # "gemini-2.5-flash-lite",
        # "gemini-2.5-flash",
        # "gemini-2.5-pro",
    ],
)
def llm_handle(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    return request.param


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
    return request.param


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
    return request.param


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


@pytest.fixture(
    params=[
        # "flux-pro",
        "flux-pro/v1.1",
        # "flux-pro/v1.1-ultra",
        "fast-lightning-sdxl",
        "gpt-image-1",
    ],
)
def img_gen_handle(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    return request.param


@pytest.fixture(
    params=[
        "pypdfium2-extract-text",
        "mistral-ocr",
    ],
)
def ocr_handle(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    return request.param


@pytest.fixture(
    params=[
        "mistral-ocr",
    ],
)
def ocr_handle_from_image(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    return request.param


@pytest.fixture(
    params=[
        "base_ocr_mistral",
    ],
)
def ocr_choice_for_pdf(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    return request.param


@pytest.fixture(
    params=[
        "base_ocr_mistral",
    ],
)
def ocr_choice_for_image(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    return request.param
