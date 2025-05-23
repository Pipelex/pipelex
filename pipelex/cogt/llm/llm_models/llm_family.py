# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from enum import StrEnum

from pipelex.cogt.llm.llm_models.llm_platform import LLMPlatform
from pipelex.cogt.llm.llm_models.llm_prompting_target import LLMPromptingTarget


class LLMCreator(StrEnum):
    AMAZON = "Amazon"
    ANTHROPIC = "Anthropic"
    DEEPSEEK = "DeepSeek"
    GOOGLE = "Google"
    OPENAI = "OpenAI"
    META = "Meta"
    MISTRAL = "Mistral"
    PERPLEXITY = "Perplexity"

    @property
    def prompting_target(self) -> LLMPromptingTarget:
        match self:
            case LLMCreator.OPENAI:
                return LLMPromptingTarget.OPENAI
            case LLMCreator.ANTHROPIC:
                return LLMPromptingTarget.ANTHROPIC
            case LLMCreator.MISTRAL:
                return LLMPromptingTarget.MISTRAL
            case LLMCreator.GOOGLE:
                return LLMPromptingTarget.GEMINI
            case LLMCreator.AMAZON | LLMCreator.PERPLEXITY | LLMCreator.META | LLMCreator.DEEPSEEK:
                return LLMPromptingTarget.OPENAI

    @property
    def console_color(self) -> str:
        match self:
            case LLMCreator.OPENAI:
                return LLMPlatform.OPENAI.console_color
            case LLMCreator.ANTHROPIC:
                return LLMPlatform.ANTHROPIC.console_color
            case LLMCreator.MISTRAL:
                return LLMPlatform.MISTRAL.console_color
            case LLMCreator.META:
                return "dodger_blue2"
            case LLMCreator.GOOGLE:
                return "blue"
            case LLMCreator.AMAZON:
                return "orange"
            case LLMCreator.PERPLEXITY:
                return "purple"
            case LLMCreator.DEEPSEEK:
                return "red"


class LLMFamily(StrEnum):
    GPT_4 = "gpt-4"
    GPT_3_5 = "gpt-3.5"
    GPT_3 = "gpt-3"
    GPT_4_5 = "gpt-4.5"
    GPT_4_1 = "gpt-4.1"
    GPT_4O = "gpt-4o"
    O_SERIES = "o"
    CLAUDE_3 = "claude-3"
    CLAUDE_3_5 = "claude-3.5"
    CLAUDE_3_7 = "claude-3.7"
    CLAUDE_2 = "claude-2"
    CLAUDE_INSTANT = "claude-instant"
    MISTRAL_7B = "mistral-7b"
    MISTRAL_8X7B = "mistral-8x7b"
    MISTRAL_LARGE = "mistral-large"
    MISTRAL_SMALL = "mistral-small"
    MISTRAL_CODESTRAL = "mistral-codestral"
    MINISTRAL = "ministral"
    PIXTRAL = "pixtral"
    LLAMA_3 = "llama-3"
    LLAMA_3_1 = "llama-3.1"
    GEMINI = "gemini"
    BEDROCK_MISTRAL_LARGE = "bedrock-mistral-large"
    BEDROCK_ANTHROPIC_CLAUDE = "bedrock-anthropic-claude"
    BEDROCK_META_LLAMA_3 = "bedrock-meta-llama-3"
    BEDROCK_AMAZON_NOVA = "bedrock-amazon-nova"

    PERPLEXITY_SEARCH = "perplexity-search"
    PERPLEXITY_RESEARCH = "perplexity-research"
    PERPLEXITY_REASONING = "perplexity-reasoning"
    PERPLEXITY_DEEPSEEK = "perplexity-deepseek"

    @property
    def creator(self) -> LLMCreator:
        match self:
            case (
                LLMFamily.GPT_4
                | LLMFamily.GPT_3_5
                | LLMFamily.GPT_3
                | LLMFamily.O_SERIES
                | LLMFamily.GPT_4_5
                | LLMFamily.GPT_4_1
                | LLMFamily.GPT_4O
            ):
                return LLMCreator.OPENAI
            case LLMFamily.CLAUDE_3 | LLMFamily.CLAUDE_3_5 | LLMFamily.CLAUDE_2 | LLMFamily.CLAUDE_INSTANT | LLMFamily.CLAUDE_3_7:
                return LLMCreator.ANTHROPIC
            case LLMFamily.BEDROCK_ANTHROPIC_CLAUDE:
                return LLMCreator.ANTHROPIC
            case (
                LLMFamily.MISTRAL_7B
                | LLMFamily.MISTRAL_8X7B
                | LLMFamily.MISTRAL_LARGE
                | LLMFamily.MISTRAL_SMALL
                | LLMFamily.MISTRAL_CODESTRAL
                | LLMFamily.MINISTRAL
                | LLMFamily.PIXTRAL
            ):
                return LLMCreator.MISTRAL
            case LLMFamily.BEDROCK_MISTRAL_LARGE:
                return LLMCreator.MISTRAL
            case LLMFamily.LLAMA_3 | LLMFamily.LLAMA_3_1:
                return LLMCreator.META
            case LLMFamily.BEDROCK_META_LLAMA_3:
                return LLMCreator.META
            case LLMFamily.GEMINI:
                return LLMCreator.GOOGLE
            case LLMFamily.BEDROCK_AMAZON_NOVA:
                return LLMCreator.AMAZON
            case LLMFamily.PERPLEXITY_SEARCH | LLMFamily.PERPLEXITY_REASONING | LLMFamily.PERPLEXITY_RESEARCH:
                return LLMCreator.PERPLEXITY
            case LLMFamily.PERPLEXITY_DEEPSEEK:
                return LLMCreator.DEEPSEEK

    @property
    def prompting_target(self) -> LLMPromptingTarget:
        return self.creator.prompting_target
