from pipelex.base_exceptions import PipelexError


class GoogleLLMWorkerError(PipelexError):
    """Base exception for Google LLM Worker errors."""


class GoogleImgGenWorkerError(PipelexError):
    """Base exception for Google Image Generation Worker errors."""
