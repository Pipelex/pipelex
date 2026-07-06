from enum import StrEnum


class PromptingTarget(StrEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    MISTRAL = "mistral"
    GEMINI = "gemini"
    FAL = "fal"
