"""Turning a TypeSafe refusal into a verdict, when the HTTP status cannot say what happened.

The shared Classify step reads the status ladder, and for most providers that is enough. It is not
enough here: **every validation failure this API produces is a `400`** — an illegal question, a
state over the context limit and a model name that does not exist all arrive under the same status,
and the ladder reads all three as "the provider rejected your content". The three have nothing in
common: one is our own bug, one is the caller's material, one is the deck.

What separates them is the body. TypeSafe answers with a `detail` that is either an object carrying
an ``error_type`` or a bare sentence, and the Extract step lifts that into ``provider_error_code``.
This module branches on it and hands everything it does not recognise — including every status the
ladder already reads correctly, ``401`` and ``429`` and the 5xx range — straight to the shared
classifier, which stays provider-blind.
"""

from pipelex.cogt.exceptions import InferenceErrorCategory
from pipelex.cogt.inference.error_classification import (
    TYPESAFE_API_USAGE_ERROR_TYPE,
    TYPESAFE_AUTHENTICATION_ERROR_TYPE,
    TYPESAFE_MALFORMED_REQUEST_CODE,
    TYPESAFE_MAX_TOKENS_EXCEEDED_ERROR_TYPE,
    SDKErrorEnvelope,
    UserActionKind,
)
from pipelex.cogt.inference.error_classify import ClassificationResult, classify_inference_error

# What an ``api_usage_error`` says when the model name is the thing that was wrong. The only shape
# of that code seen against the live API, and the one worth naming a verdict for.
_UNKNOWN_MODEL_MARKER = "unknown model"


def classify_typesafe_error(metadata: SDKErrorEnvelope) -> ClassificationResult:
    """Classify a TypeSafe failure, reading the body's ``error_type`` before the status ladder."""
    match metadata.provider_error_code:
        case None:
            return classify_inference_error(metadata)
        case code if code == TYPESAFE_AUTHENTICATION_ERROR_TYPE:
            # Observed on a 401, where the ladder agrees. Named anyway because the code is the
            # contract and the status is not: this API answers 400 for everything else it refuses.
            return ClassificationResult(
                category=InferenceErrorCategory.CONFIGURATION,
                user_action_kind=UserActionKind.CHECK_CREDENTIALS,
            )
        case code if code == TYPESAFE_MAX_TOKENS_EXCEEDED_ERROR_TYPE:
            # The state plus the longest question went over the context limit. The caller's
            # material is what has to shrink, and the ladder's 400 arm happens to agree.
            return ClassificationResult(
                category=InferenceErrorCategory.CONTENT,
                user_action_kind=UserActionKind.CHANGE_INPUT,
            )
        case code if code == TYPESAFE_API_USAGE_ERROR_TYPE:
            if _UNKNOWN_MODEL_MARKER in metadata.message.lower():
                # The deck names a judgment model this API does not serve. Not the caller's
                # content, and the flag is what selects ``JudgmentModelNotFoundError``.
                return ClassificationResult(
                    category=InferenceErrorCategory.CONFIGURATION,
                    user_action_kind=UserActionKind.CHANGE_MODEL,
                    is_model_not_found=True,
                )
            # Some other misuse of the API. It is still not the caller's content — which is all the
            # ladder's 400 arm would have said — but nothing here knows what to tell them to change.
            return ClassificationResult(
                category=InferenceErrorCategory.CONFIGURATION,
                user_action_kind=UserActionKind.CONTACT_SUPPORT,
            )
        case code if code == TYPESAFE_MALFORMED_REQUEST_CODE:
            # A bare-sentence ``detail``: the question itself was illegal — no instructions and no
            # criteria, a rating scale past the vendor's cap. Our own validation is supposed to
            # have refused every one of those before a request was built, so reaching here is a
            # Pipelex defect and not something the caller wrote.
            return ClassificationResult(
                category=InferenceErrorCategory.CONFIGURATION,
                user_action_kind=UserActionKind.CONTACT_SUPPORT,
            )
        case _:
            return classify_inference_error(metadata)
