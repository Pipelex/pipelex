from pipelex.tools.typing.strenum import StrEnum


class LLMPromptingTarget(StrEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    MISTRAL = "mistral"
    GEMINI = "gemini"
