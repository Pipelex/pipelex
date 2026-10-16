from pipelex.cogt.exceptions import CogtError
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode


class HuggingFaceProviderUnknownError(CogtError):
    """A Hugging Face model handle whose variant names an inference provider the Hugging Face client does not know.

    The variant is the model spec's, so the deployment's configuration is what names it.
    """

    error_code = PipelexErrorCode.CONFIG_INVALID
