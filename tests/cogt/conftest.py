# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.


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
        "gpt-4o-mini",
        # "gpt-4-5-preview",
        # "o1-mini",
        # "o3-mini",
        # "claude-3-haiku",
        # "claude-3-5-sonnet",
        # "claude-3-7-sonnet",
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
        # "gpt-4-5-preview",
        # "claude-3-haiku",
        # "claude-3-5-sonnet",
        # "claude-3-7-sonnet",
        # "pixtral-12b",
        # "pixtral-large",
        # "gemini-1-5-pro",
        # "gemini-1-5-flash",
        # "gemini-2-flash",
        # "gemini-2-pro",
        # "gemini-2-5-pro",
        # "gemini-2-5-flash",
    ]
)
def llm_handle_for_vision(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    return request.param


@pytest.fixture(
    params=[
        # LLMFamily.GPT_4,
        # LLMFamily.GPT_4_1,
        LLMFamily.GPT_4O,
        # LLMFamily.GPT_4_5,
        # LLMFamily.O_SERIES,
        # LLMFamily.PERPLEXITY_SEARCH,
        # LLMFamily.PERPLEXITY_REASONING,
        # LLMFamily.PERPLEXITY_RESEARCH,
        # LLMFamily.PERPLEXITY_DEEPSEEK,
        # LLMFamily.GEMINI,
        # LLMFamily.GEMMA,
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


@pytest.fixture(
    params=[
        # LLMPlatform.ANTHROPIC,
        LLMPlatform.AZURE_OPENAI,
        # LLMPlatform.BEDROCK,
        # LLMPlatform.BEDROCK_ANTHROPIC,
        # LLMPlatform.MISTRAL,
        # LLMPlatform.OPENAI,
        # LLMPlatform.PERPLEXITY,
        # LLMPlatform.VERTEXAI_OPENAI,
    ]
)
def llm_platform(request: pytest.FixtureRequest) -> LLMPlatform:
    assert isinstance(request.param, LLMPlatform)
    return request.param


@pytest.fixture(
    params=[
        "gpt-4o-mini",
        # "open-mixtral-8x7b",
        # "google/gemini-2.0-flash",
        # "google/gemini-2.5-pro-exp-03-25",
        # "o1",
        # "o4-mini",
        # "bedrock-mistral-large",
        # "sonar",
        # "claude-3-7-sonnet",
    ]
)
def llm_id(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    return request.param


@pytest.fixture(
    params=[
        # ImggHandle.FLUX_1_PRO_LEGACY,
        # ImggHandle.FLUX_1_1_PRO,
        # ImggHandle.FLUX_1_1_ULTRA,
        ImggHandle.SDXL_LIGHTNING,
    ]
)
def imgg_handle(request: pytest.FixtureRequest) -> ImggHandle:
    assert isinstance(request.param, ImggHandle)
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
