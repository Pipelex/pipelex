"""LLM-related test fixtures."""

import pytest

from pipelex import log
from pipelex.cogt.llm.llm_job_components import LLMJobParams
from pipelex.hub import get_model_deck
from tests.integration.pipelex.fixtures.routing_fixtures import ALL_BACKENDS, check_backend_supports_model


def is_llm_handle_supported(llm_handle: str) -> bool:
    """Check if an LLM handle is available in the current model deck."""
    model_deck = get_model_deck()
    return model_deck.is_handle_defined(llm_handle)


def is_llm_handle_supported_by_enabled_backends(llm_handle: str) -> bool:
    """Check if an LLM handle is supported by at least one enabled backend."""
    return any(check_backend_supports_model(backend, llm_handle) for backend in ALL_BACKENDS)


def is_llm_preset_supported(llm_preset_id: str) -> bool:
    """Check if an LLM preset is supported by at least one enabled backend."""
    llm_setting = get_model_deck().get_llm_setting(llm_choice=llm_preset_id)
    model_handle = llm_setting.model
    model_deck = get_model_deck()
    inference_model = model_deck.get_optional_inference_model(model_handle=model_handle)
    if inference_model is None:
        return False
    log.debug(f"Inference model found!! {inference_model}")
    return True


def is_llm_preset_supported_by_enabled_backends(llm_preset_id: str) -> bool:
    """Check if an LLM preset is supported by at least one enabled backend."""
    llm_setting = get_model_deck().get_llm_setting(llm_choice=llm_preset_id)
    # return is_llm_handle_supported_by_enabled_backends(llm_setting.model)
    return any(check_backend_supports_model(backend, llm_setting.model) for backend in ALL_BACKENDS)


# ================================================================================================
# LLM Handles by Manufacturer
# each can be supported by multiple backends
# ================================================================================================

# --- Amazon Models (Nova) -----------------------------------------------------------------------
AMAZON_MODELS = [
    "bedrock-nova-pro",
    "nova-lite-v1",
    "nova-micro-v1",
]

# --- Anthropic Models (Claude) ------------------------------------------------------------------
ANTHROPIC_MODELS = [
    # "claude-3-haiku",
    # "claude-3-opus",
    # "claude-3.7-sonnet",
    # "claude-4-opus",
    # "claude-4-sonnet",
    # "claude-4.1-opus",
    # "claude-4.5-haiku",
    "claude-4.5-sonnet",
    # "claude-opus-4",
    # "claude-4.5-opus",
]

# --- DeepSeek Models ----------------------------------------------------------------------------
DEEPSEEK_MODELS = [
    "deepseek-chat-free",
    "deepseek-r1-free",
]

# --- Google Models (Gemini) ---------------------------------------------------------------------
GOOGLE_MODELS = [
    # "gemini-2.0-flash",
    "gemini-2.5-flash",
    # "gemini-2.5-flash-lite",
    # "gemini-2.5-pro",
    # "gemini-flash-1.5-8b",
    # "gemini-3.0-pro",
]

# --- Groq Models --------------------------------------------------------------------------------
GROQ_MODELS = [
    "groq/compound",
    "groq/compound-mini",
]

# --- Meta Models (Llama) ------------------------------------------------------------------------
META_MODELS = [
    "bedrock-meta-llama-3-3-70b-instruct",
    "llama-3.1-8b-instant",
    "llama-3.2-11b-vision-instruct",
    "llama-3.3-70b-instruct",
    "llama-3.3-70b-instruct-free",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "meta-llama/llama-guard-4-12b",
]

# --- Mistral Models -----------------------------------------------------------------------------
MISTRAL_MODELS = [
    "bedrock-mistral-large",
    "ministral-3b",
    "ministral-8b",
    "mistral-7b-2312",
    "mistral-8x7b-2312",
    "mistral-codestral-2405",
    "mistral-large",
    "mistral-large-2402",
    "mistral-medium",
    "mistral-medium-2508",
    "mistral-small",
    "mistral-small-2402",
    "pixtral-12b",
    "pixtral-large",
    "pixtral-large-2411",
]

# --- Moonshot AI Models -------------------------------------------------------------------------
MOONSHOT_MODELS = [
    "moonshotai/kimi-k2-instruct-0905",
]

# --- OpenAI Models ------------------------------------------------------------------------------
OPENAI_MODELS = [
    # "gpt-3.5-turbo",
    # "gpt-4",
    # "gpt-4-turbo",
    # "gpt-4.1",
    # "gpt-4.1-mini",
    # "gpt-4.1-nano",
    # "gpt-4o",
    # "gpt-4o-2024-11-20",
    "gpt-4o-mini",
    # "gpt-4o-mini-2024-07-18",
    # "gpt-5",
    # "gpt-5-chat",
    # "gpt-5-mini",
    # "gpt-5-nano",
    # "gpt-5.1",
    # "gpt-5.1-chat",
    # "gpt-5.1-codex",
    # "o1",
    # "o1-mini",
    # "o3",
    # "o3-mini",
    # "o4-mini",
]

# --- OpenAI OSS Models --------------------------------------------------------------------------
OPENAI_OSS_MODELS = [
    # "openai/gpt-oss-120b",
    # "openai/gpt-oss-20b",
    # "openai/gpt-oss-safeguard-20b",
    "gpt-oss-20b",
    "gpt-oss-120b",
]

# --- Qwen Models --------------------------------------------------------------------------------
QWEN_MODELS = [
    "qwen-2.5-72b-instruct",
    "qwen/qwen3-32b",
    "qwen2.5-vl-72b-instruct",
]

# --- XAI Models (Grok) --------------------------------------------------------------------------
XAI_MODELS = [
    # "grok-3",
    # "grok-3-fast",
    # "grok-3-mini",
    # "grok-3-mini-fast",
    # "grok-4",
    "grok-4-fast",
]

# --- All LLM Handles ----------------------------------------------------------------------------
ALL_LLM_HANDLES = [
    # *AMAZON_MODELS,
    # *ANTHROPIC_MODELS,
    # *DEEPSEEK_MODELS,
    # *GOOGLE_MODELS,
    # *GROQ_MODELS,
    # *META_MODELS,
    # *MISTRAL_MODELS,
    # *MOONSHOT_MODELS,
    # *OPENAI_MODELS,
    # *OPENAI_OSS_MODELS,
    # *QWEN_MODELS,
    *XAI_MODELS,
]


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
    params=ALL_LLM_HANDLES,
)
def llm_handle(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    llm_handle_param = request.param
    if not is_llm_handle_supported(llm_handle_param):
        pytest.skip(f"LLM handle '{llm_handle_param}' not available in model deck")
    if not is_llm_handle_supported_by_enabled_backends(llm_handle_param):
        pytest.skip(f"LLM handle '{llm_handle_param}' not supported by any enabled backend")
    return llm_handle_param


@pytest.fixture(
    params=[
        # "llm_for_testing_gen_text",
        # "llm_for_testing_gen_object",
        "llm_for_creative_writing",
    ],
)
def llm_preset_id(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    llm_preset_id_param = request.param
    if not is_llm_preset_supported(llm_preset_id=llm_preset_id_param):
        pytest.skip(f"LLM preset '{llm_preset_id_param}' not supported by any enabled backend")
    # if not is_llm_preset_supported_by_enabled_backends(llm_preset_id=llm_preset_id_param):
    #     pytest.skip(f"LLM preset '{llm_preset_id_param}' not supported by any enabled backend")
    return llm_preset_id_param


@pytest.fixture(
    params=[
        # "gpt-4o",
        # "gpt-4o-mini",
        # "gpt-5-mini",
        # "gpt-5-nano",
        # "gpt-5-chat",
        # "claude-4.5-sonnet",
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
        pytest.skip(f"LLM handle '{llm_handle_param}' not available in model deck")
    if not is_llm_handle_supported_by_enabled_backends(llm_handle_param):
        pytest.skip(f"LLM handle '{llm_handle_param}' not supported by any enabled backend")
    return llm_handle_param
