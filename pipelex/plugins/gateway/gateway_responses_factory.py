from __future__ import annotations

from typing import TYPE_CHECKING, Any

import openai
from portkey_ai import (
    createHeaders,  # type: ignore[reportUnknownVariableType]
)
from typing_extensions import override

from pipelex.plugins.gateway.gateway_constants import GatewayOpenAISdkVariant
from pipelex.plugins.gateway.gateway_exceptions import GatewayFactoryError
from pipelex.plugins.gateway.gateway_factory import GatewayFactory
from pipelex.plugins.openai.openai_responses_factory import OpenAIResponsesFactory

if TYPE_CHECKING:
    from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract
    from pipelex.cogt.model_backends.backend import InferenceBackend
    from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
    from pipelex.plugins.plugin_sdk_registry import Plugin


class GatewayResponsesFactory(OpenAIResponsesFactory):
    @classmethod
    def make_portkey_openai_client_for_responses(
        cls,
        plugin: Plugin,
        backend: InferenceBackend,
    ) -> openai.AsyncOpenAI:
        is_debug_enabled = GatewayFactory.is_debug_enabled(backend=backend)
        endpoint = GatewayFactory.get_endpoint(backend=backend)
        api_key = GatewayFactory.get_api_key(backend=backend)
        if not GatewayOpenAISdkVariant.is_responses(plugin.sdk):
            msg = f"Plugin '{plugin}' is not supported by '{cls.__name__}'"
            raise GatewayFactoryError(msg)

        return openai.AsyncOpenAI(
            base_url=endpoint,
            api_key="",
            default_headers=createHeaders(
                api_key=api_key,
                debug=is_debug_enabled,
            ),  # type: ignore[call-overload]
        )

    @override
    def make_extras(
        self, inference_model: InferenceModelSpec, inference_job: InferenceJobAbstract, output_desc: str
    ) -> tuple[dict[str, str], dict[str, Any]]:
        return GatewayFactory.make_extras(inference_model=inference_model, inference_job=inference_job, output_desc=output_desc)
