"""Gateway-specific post-processing of OpenAI-SDK error classification.

Gateway LLM models run on the OpenAI workers — the Pipelex Gateway exposes an
OpenAI-compatible API — so a gateway 404 surfaces as an ``openai.NotFoundError``
and the shared ``classify_openai_sdk_error`` maps every 404 to
``LLMModelNotFoundError`` (CONFIGURATION, non-retryable). A freshly-routed
gateway deployment can briefly 404 during propagation: a transient race that
should be retried, not treated as a permanent unknown-model error. This module
demotes that one case, keeping the shared OpenAI classifier gateway-agnostic.
"""

import openai

from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError, LLMModelNotFoundError
from pipelex.cogt.inference.error_classification import (
    UserAction,
    UserActionKind,
    is_deployment_propagation_race_message,
)


def demote_gateway_propagation_race(
    categorized: LLMCompletionError | LLMModelNotFoundError | None,
    sdk_exc: BaseException,
) -> LLMCompletionError | LLMModelNotFoundError | None:
    """Demote a gateway deployment-propagation-race 404 to a retryable transient error.

    Returns ``categorized`` unchanged unless it is an ``LLMModelNotFoundError`` raised from
    an ``openai.NotFoundError`` whose body carries the propagation-race phrase — in which
    case it becomes a ``TRANSIENT`` ``LLMCompletionError`` so retry treats it as retryable,
    matching the gateway image-gen worker. A genuine unknown-model 404 is left untouched as
    the non-retryable ``LLMModelNotFoundError``.
    """
    if not isinstance(categorized, LLMModelNotFoundError):
        return categorized
    if not isinstance(sdk_exc, openai.NotFoundError):
        return categorized
    if not is_deployment_propagation_race_message(str(sdk_exc)):
        return categorized
    msg = f"Gateway deployment still propagating for model '{categorized.model_handle}': {sdk_exc}"
    return LLMCompletionError(
        msg,
        error_category=InferenceErrorCategory.TRANSIENT,
        user_action=UserAction(
            kind=UserActionKind.WAIT_AND_RETRY,
            detail="The gateway deployment is still propagating — the system will retry automatically",
        ),
        provider_metadata=categorized.provider_metadata,
    )
