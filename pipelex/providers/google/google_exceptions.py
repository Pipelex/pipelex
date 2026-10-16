from mthds.protocol.problem.registry import CoreCode

from pipelex.cogt.exceptions import CogtError


class GoogleLLMWorkerError(CogtError):
    """A Gemini structured answer whose parsed result is not of the schema's type."""

    error_code = CoreCode.MODEL_OUTPUT_SCHEMA_MISMATCH
