"""The Responses-API factory for the Pipelex Manifold service.

Thin, unlike its Chat Completions sibling: the Responses shape carries documents as its own input
parts, so there is no gateway-specific message override to copy. All this class supplies is the
client — built under the endpoint rule, authenticated on the service's header — and the per-request
extras.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import openai
from typing_extensions import override

from pipelex.config import get_config
from pipelex.providers.manifold.manifold_constants import ManifoldOpenAISdkVariant
from pipelex.providers.manifold.manifold_exceptions import ManifoldFactoryError
from pipelex.providers.manifold.manifold_factory import ManifoldFactory
from pipelex.providers.openai.openai_responses_factory import OpenAIResponsesFactory

if TYPE_CHECKING:
    from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract
    from pipelex.cogt.model_backends.backend import InferenceBackend
    from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
    from pipelex.plugins.model_handle import ModelHandle


class ManifoldResponsesFactory(OpenAIResponsesFactory):
    @classmethod
    def make_openai_client_for_responses(
        cls,
        model_handle: ModelHandle,
        *,
        backend: InferenceBackend,
    ) -> openai.AsyncOpenAI:
        if not ManifoldOpenAISdkVariant.is_responses(model_handle.sdk):
            msg = f"ModelHandle '{model_handle}' is not supported by '{cls.__name__}'"
            raise ManifoldFactoryError(msg)

        return openai.AsyncOpenAI(
            base_url=ManifoldFactory.get_base_url(backend=backend),
            # Auth travels in the service's own header, not in the OpenAI Authorization one. The SDK
            # has rejected an empty api_key since 2.34.0, so the slot holds a placeholder the
            # gateway never reads.
            api_key="unused-auth-via-manifold-header",
            # Tier 1 transport retry: set explicitly from config rather than inheriting the SDK
            # default, so a transport_max_retries override applies to this path too.
            max_retries=get_config().inference.transport_max_retries,
            default_headers=ManifoldFactory.make_auth_headers(backend=backend),
        )

    @override
    def make_extras(
        self, inference_model: InferenceModelSpec, *, inference_job: InferenceJobAbstract, output_desc: str
    ) -> tuple[dict[str, str], dict[str, Any]]:
        return ManifoldFactory.make_extras(inference_model=inference_model, inference_job=inference_job, output_desc=output_desc)
