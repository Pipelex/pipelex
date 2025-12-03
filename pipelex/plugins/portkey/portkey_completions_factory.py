from __future__ import annotations

from typing import TYPE_CHECKING, Any

import openai
from portkey_ai import (
    createHeaders,  # type: ignore[reportUnknownVariableType]
)
from typing_extensions import override

from pipelex import log
from pipelex.plugins.openai.openai_completions_factory import OpenAICompletionsFactory
from pipelex.plugins.portkey.portkey_constants import PortkeyOpenAISdkVariant
from pipelex.plugins.portkey.portkey_exceptions import PortkeyFactoryError
from pipelex.plugins.portkey.portkey_factory import PortkeyFactory

if TYPE_CHECKING:
    from pipelex.cogt.llm.llm_job import LLMJob
    from pipelex.cogt.model_backends.backend import InferenceBackend
    from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
    from pipelex.plugins.plugin_sdk_registry import Plugin


class PortkeyCompletionsFactory(OpenAICompletionsFactory):
    @classmethod
    def make_portkey_openai_client_for_completions(
        cls,
        plugin: Plugin,
        backend: InferenceBackend,
    ) -> openai.AsyncOpenAI:
        is_debug_enabled = PortkeyFactory.is_debug_enabled(backend=backend)
        endpoint = PortkeyFactory.get_endpoint(backend=backend)
        api_key = PortkeyFactory.get_api_key(backend=backend)
        log.verbose(f"Making AsyncOpenAI client with endpoint: {endpoint}, debug: {is_debug_enabled}")

        if not PortkeyOpenAISdkVariant.is_completions(plugin.sdk):
            msg = f"Plugin '{plugin}' is not supported by '{cls.__name__}'"
            raise PortkeyFactoryError(msg)

        return openai.AsyncOpenAI(
            base_url=endpoint,
            api_key="",
            default_headers=createHeaders(
                api_key=api_key,
                strict_open_ai_compliance=False,
                debug=is_debug_enabled,
            ),  # type: ignore[call-overload]
        )

    @override
    def make_extras(self, inference_model: InferenceModelSpec, llm_job: LLMJob, output_desc: str) -> tuple[dict[str, str], dict[str, Any]]:
        return PortkeyFactory.make_extras(inference_model=inference_model, llm_job=llm_job, output_desc=output_desc)
