from typing_extensions import override

from pipelex.cogt.exceptions import LLMCompletionError, LLMModelNotFoundError
from pipelex.plugins.gateway.gateway_llm_error import demote_gateway_propagation_race
from pipelex.plugins.openai.openai_responses_llm_worker import OpenAIResponsesLLMWorker


class GatewayResponsesLLMWorker(OpenAIResponsesLLMWorker):
    """OpenAI Responses LLM worker specialized for the Pipelex Gateway.

    Identical to ``OpenAIResponsesLLMWorker`` except that a transient gateway
    deployment-propagation-race 404 is demoted from the permanent
    ``LLMModelNotFoundError`` to a retryable error — matching the gateway
    image-gen worker, and unlike a genuine unknown-model 404 which stays permanent.
    """

    @override
    def _classify_sdk_error(self, sdk_exc: BaseException) -> LLMCompletionError | LLMModelNotFoundError | None:
        return demote_gateway_propagation_race(
            categorized=super()._classify_sdk_error(sdk_exc=sdk_exc),
            sdk_exc=sdk_exc,
        )
