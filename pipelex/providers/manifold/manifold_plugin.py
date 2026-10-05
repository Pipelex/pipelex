"""The manifold sdk set, registered.

One registration per ``(family, sdk)`` the Pipelex Manifold service serves. The pairing worth
noticing is ``(IMG_GEN, manifold_completions)``: some image models answer on the Chat Completions
shape rather than on the Images API, and the catalog says which by giving them ``model_type =
"img_gen"`` while leaving them on the default completions sdk — so the same sdk name is registered
under two families, served by two different workers.

Claude reaches the manifold service on ``manifold_anthropic``: the open Anthropic worker, built with
the package's extras factory so that every call carries the metadata header, and a client that
authenticates on whichever header the backend names. A catalog entry left on the plain ``anthropic``
sdk would still answer, without the header.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.inference_backend_registry import InferenceFamily, require_sdk
from pipelex.plugins.model_handle import ModelHandle
from pipelex.providers.manifold.manifold_constants import ManifoldSdk
from pipelex.providers.manifold.manifold_error_codes import MANIFOLD_SERVICE_ERROR_CODES

if TYPE_CHECKING:
    from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
    from pipelex.cogt.model_backends.backend import InferenceBackend
    from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
    from pipelex.plugins.registrar import PluginRegistrar
    from pipelex.plugins.sdk_client_registry import SdkClientRegistry
    from pipelex.reporting.reporting_protocol import ReportingProtocol


def _make_manifold_anthropic_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,
    sdk_clients: SdkClientRegistry,
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    require_sdk(spec="anthropic", extra="anthropic", msg="The anthropic SDK is required to reach Claude through this backend.")

    from pipelex.providers.anthropic.anthropic_factory import AnthropicFactory, AnthropicSdkVariant  # ruff: ignore[import-outside-top-level]
    from pipelex.providers.anthropic.anthropic_llm_worker import AnthropicLLMWorker  # ruff: ignore[import-outside-top-level]
    from pipelex.providers.manifold.manifold_anthropic_extras import ManifoldAnthropicExtrasFactory  # ruff: ignore[import-outside-top-level]

    model_handle = ModelHandle.make_for_inference_model(inference_model=inference_model)
    sdk_instance = sdk_clients.get_or_create(
        handle=model_handle,
        build=lambda: AnthropicFactory.make_anthropic_client(model_handle=model_handle, backend=backend, sdk_variant=AnthropicSdkVariant.ANTHROPIC),
    )
    return AnthropicLLMWorker(
        sdk_instance=sdk_instance,
        extra_config=backend.extra_config,
        inference_model=inference_model,
        reporting_delegate=reporting_delegate,
        extras_factory=ManifoldAnthropicExtrasFactory(),
    )


def _make_manifold_completions_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,
    sdk_clients: SdkClientRegistry,
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    from pipelex.providers.manifold.manifold_completions_factory import ManifoldCompletionsFactory  # ruff: ignore[import-outside-top-level]
    from pipelex.providers.openai.openai_completions_llm_worker import OpenAICompletionsLLMWorker  # ruff: ignore[import-outside-top-level]

    model_handle = ModelHandle.make_for_inference_model(inference_model=inference_model)
    sdk_instance = sdk_clients.get_or_create(
        handle=model_handle,
        build=lambda: ManifoldCompletionsFactory.make_openai_client_for_completions(model_handle=model_handle, backend=backend),
    )
    return OpenAICompletionsLLMWorker(
        openai_completions_factory=ManifoldCompletionsFactory(is_http_url_enabled=False),
        sdk_instance=sdk_instance,
        inference_model=inference_model,
        reporting_delegate=reporting_delegate,
    )


def _make_manifold_responses_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,
    sdk_clients: SdkClientRegistry,
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    from pipelex.providers.manifold.manifold_responses_factory import ManifoldResponsesFactory  # ruff: ignore[import-outside-top-level]
    from pipelex.providers.openai.openai_responses_llm_worker import OpenAIResponsesLLMWorker  # ruff: ignore[import-outside-top-level]

    model_handle = ModelHandle.make_for_inference_model(inference_model=inference_model)
    sdk_instance = sdk_clients.get_or_create(
        handle=model_handle,
        build=lambda: ManifoldResponsesFactory.make_openai_client_for_responses(model_handle=model_handle, backend=backend),
    )
    return OpenAIResponsesLLMWorker(
        openai_responses_factory=ManifoldResponsesFactory(is_http_url_enabled=False),
        sdk_instance=sdk_instance,
        inference_model=inference_model,
        reporting_delegate=reporting_delegate,
    )


def _make_manifold_completions_img_gen_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,
    sdk_clients: SdkClientRegistry,
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    from pipelex.providers.manifold.manifold_completions_factory import ManifoldCompletionsFactory  # ruff: ignore[import-outside-top-level]
    from pipelex.providers.openai.openai_completions_img_gen_worker import OpenAICompletionsImgGenWorker  # ruff: ignore[import-outside-top-level]
    from pipelex.tools.misc.image_utils import ImageFormat  # ruff: ignore[import-outside-top-level]

    model_handle = ModelHandle.make_for_inference_model(inference_model=inference_model)
    sdk_instance = sdk_clients.get_or_create(
        handle=model_handle,
        build=lambda: ManifoldCompletionsFactory.make_openai_client_for_completions(model_handle=model_handle, backend=backend),
    )
    return OpenAICompletionsImgGenWorker(
        openai_completions_factory=ManifoldCompletionsFactory(is_http_url_enabled=False),
        sdk_instance=sdk_instance,
        inference_model=inference_model,
        reporting_delegate=reporting_delegate,
        fixed_output_format=ImageFormat.PNG,
    )


def _make_manifold_img_gen_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,
    sdk_clients: SdkClientRegistry,
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    from pipelex.providers.manifold.manifold_factory import ManifoldFactory  # ruff: ignore[import-outside-top-level]
    from pipelex.providers.manifold.manifold_img_gen_worker import ManifoldImgGenWorker  # ruff: ignore[import-outside-top-level]

    model_handle = ModelHandle.make_for_inference_model(inference_model=inference_model)
    sdk_instance = sdk_clients.get_or_create(
        handle=model_handle,
        build=lambda: ManifoldFactory.make_portkey_client(backend=backend),
    )
    return ManifoldImgGenWorker(
        sdk_instance=sdk_instance,
        inference_model=inference_model,
        reporting_delegate=reporting_delegate,
    )


def _make_manifold_extract_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,
    sdk_clients: SdkClientRegistry,
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    from pipelex.providers.manifold.manifold_extract_worker import ManifoldExtractWorker  # ruff: ignore[import-outside-top-level]
    from pipelex.providers.manifold.manifold_native_client import ManifoldNativeClient  # ruff: ignore[import-outside-top-level]

    model_handle = ModelHandle.make_for_inference_model(inference_model=inference_model)
    sdk_instance = sdk_clients.get_or_create(handle=model_handle, build=lambda: ManifoldNativeClient(backend=backend))
    return ManifoldExtractWorker(
        sdk_instance=sdk_instance,
        extra_config=backend.extra_config,
        inference_model=inference_model,
        reporting_delegate=reporting_delegate,
    )


def _make_manifold_search_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,
    sdk_clients: SdkClientRegistry,
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    from pipelex.providers.manifold.manifold_native_client import ManifoldNativeClient  # ruff: ignore[import-outside-top-level]
    from pipelex.providers.manifold.manifold_search_worker import ManifoldSearchWorker  # ruff: ignore[import-outside-top-level]

    model_handle = ModelHandle.make_for_inference_model(inference_model=inference_model)
    sdk_instance = sdk_clients.get_or_create(handle=model_handle, build=lambda: ManifoldNativeClient(backend=backend))
    return ManifoldSearchWorker(
        sdk_instance=sdk_instance,
        inference_model=inference_model,
        reporting_delegate=reporting_delegate,
    )


class ManifoldPlugin:
    """Built-in driver for the Pipelex Manifold service, serving all inference families."""

    name = "manifold"
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_service_error_codes(codes=MANIFOLD_SERVICE_ERROR_CODES)
        registrar.add_inference_backend(family=InferenceFamily.LLM, sdk=ManifoldSdk.ANTHROPIC, make_worker=_make_manifold_anthropic_worker)
        registrar.add_inference_backend(family=InferenceFamily.LLM, sdk=ManifoldSdk.COMPLETIONS, make_worker=_make_manifold_completions_worker)
        registrar.add_inference_backend(family=InferenceFamily.LLM, sdk=ManifoldSdk.RESPONSES, make_worker=_make_manifold_responses_worker)
        registrar.add_inference_backend(family=InferenceFamily.IMG_GEN, sdk=ManifoldSdk.IMG_GEN, make_worker=_make_manifold_img_gen_worker)
        registrar.add_inference_backend(
            family=InferenceFamily.IMG_GEN, sdk=ManifoldSdk.COMPLETIONS, make_worker=_make_manifold_completions_img_gen_worker
        )
        registrar.add_inference_backend(family=InferenceFamily.EXTRACT, sdk=ManifoldSdk.EXTRACT, make_worker=_make_manifold_extract_worker)
        registrar.add_inference_backend(family=InferenceFamily.SEARCH, sdk=ManifoldSdk.SEARCH, make_worker=_make_manifold_search_worker)
