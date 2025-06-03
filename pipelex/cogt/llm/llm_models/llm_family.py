from pipelex.cogt.llm.llm_models.llm_platform import LLMPlatform
from pipelex.cogt.llm.llm_models.llm_prompting_target import LLMPromptingTarget
from pipelex.types import StrEnum


class LLMCreator(StrEnum):
    AMAZON = "Amazon"
    ANTHROPIC = "Anthropic"
    DEEPSEEK = "DeepSeek"
    GOOGLE = "Google"
    OPENAI = "OpenAI"
    META = "Meta"
    MISTRAL = "Mistral"
    PERPLEXITY = "Perplexity"
    XAI = "XAI"
    ALIBABA = "Alibaba"

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
            case LLMCreator.AMAZON | LLMCreator.PERPLEXITY | LLMCreator.META | LLMCreator.DEEPSEEK | LLMCreator.XAI | LLMCreator.ALIBABA:
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
            case LLMCreator.XAI:
                return "green"
            case LLMCreator.ALIBABA:
                return "yellow"


class LLMFamily(StrEnum):
    GPT_3 = "gpt-3"
    GPT_3_5 = "gpt-3.5"
    GPT_4 = "gpt-4"
    GPT_4O = "gpt-4o"
    GPT_4_5 = "gpt-4.5"
    GPT_4_1 = "gpt-4.1"
    O_SERIES = "o"

    CLAUDE_3 = "claude-3"
    CLAUDE_3_5 = "claude-3.5"
    CLAUDE_3_7 = "claude-3.7"
    CLAUDE_4 = "claude-4"

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

    GROK_3 = "grok-3"

    CUSTOM_LLAMA_4 = "custom-llama-4"
    CUSTOM_GEMMA_3 = "custom-gemma-3"
    CUSTOM_MISTRAL_SMALL_3_1 = "custom-mistral-small3.1"
    CUSTOM_QWEN_3 = "custom-qwen3"

    @property
    def creator(self) -> LLMCreator:
        match self:
            case (
                LLMFamily.GPT_4 | LLMFamily.GPT_3_5 | LLMFamily.GPT_3 | LLMFamily.O_SERIES | LLMFamily.GPT_4_5 | LLMFamily.GPT_4_1 | LLMFamily.GPT_4O
            ):
                return LLMCreator.OPENAI
            case LLMFamily.CLAUDE_3 | LLMFamily.CLAUDE_3_5 | LLMFamily.CLAUDE_3_7 | LLMFamily.CLAUDE_4:
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
                | LLMFamily.CUSTOM_MISTRAL_SMALL_3_1
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
            case LLMFamily.GROK_3:
                return LLMCreator.XAI
            case LLMFamily.CUSTOM_LLAMA_4 | LLMFamily.CUSTOM_GEMMA_3:
                return LLMCreator.META
            case LLMFamily.CUSTOM_QWEN_3:
                return LLMCreator.ALIBABA

    @property
    def prompting_target(self) -> LLMPromptingTarget:
        return self.creator.prompting_target
