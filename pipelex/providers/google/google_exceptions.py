from pipelex.cogt.exceptions import CogtError


class GoogleLLMWorkerError(CogtError):
    """Base exception for Google LLM Worker errors."""


class GoogleImgGenWorkerError(CogtError):
    """Base exception for Google Image Generation Worker errors."""
