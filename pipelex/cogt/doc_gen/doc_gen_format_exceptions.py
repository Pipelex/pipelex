from pipelex.base_exceptions import PipelexError
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode


class DocGenChoiceKeyError(PipelexError, ValueError):
    """A key of the model deck's doc-gen defaults that names no step: not '<format>.<source>', or a pair no step composes.

    The deck and the plugins declaring defaults are the deployment's, so the key is its configuration. A ``ValueError``
    too, because the deck's field validator raises it and pydantic wraps only a ``ValueError`` into its validation error.
    Its own module because ``doc_gen/exceptions.py`` imports ``doc_gen_format``, which raises it.
    """

    error_code = PipelexErrorCode.CONFIG_INVALID
