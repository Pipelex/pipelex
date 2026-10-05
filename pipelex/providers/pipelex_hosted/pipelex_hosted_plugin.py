"""The hosted sdk set, registered.

One registration per ``(family, sdk)`` the Pipelex service serves. The pairing worth
noticing is ``(IMG_GEN, manifold_completions)``: some image models answer on the Chat Completions
shape rather than on the Images API, and the catalog says which by giving them ``model_type =
"img_gen"`` while leaving them on the default completions sdk — so the same sdk name is registered
under two families, served by two different workers.

Claude reaches the Pipelex service on ``manifold_anthropic``: the open Anthropic worker, built with
the package's extras factory so that every call carries the metadata header, and a client that
authenticates on whichever header the backend names. A catalog entry left on the plain ``anthropic``
sdk would still answer, without the header.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.inference_backend_registry import InferenceFamily, require_sdk
from pipelex.plugins.model_handle import ModelHandle
from pipelex.providers.pipelex_hosted.pipelex_hosted_constants import PipelexHostedSdk
from pipelex.providers.pipelex_hosted.pipelex_hosted_error_codes import PIPELEX_HOSTED_SERVICE_ERROR_CODES

if TYPE_CHECKING:
    from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
    from pipelex.cogt.model_backends.backend import InferenceBackend
    from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
    from pipelex.plugins.registrar import PluginRegistrar
    from pipelex.plugins.sdk_client_registry import SdkClientRegistry
    from pipelex.reporting.reporting_protocol import ReportingProtocol


def _make_pipelex_hosted_anthropic_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,
    sdk_clients: SdkClientRegistry,
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    require_sdk(spec="anthropic", extra="anthropic", msg="The anthropic SDK is required to reach Claude through this backend.")

    from pipelex.providers.anthropic.anthropic_factory import AnthropicFactory, AnthropicSdkVariant  # ruff: ignore[import-outside-top-level]
    from pipelex.providers.anthropic.anthropic_llm_worker import AnthropicLLMWorker  # ruff: ignore[import-outside-top-level]
    from pipelex.providers.pipelex_hosted.pipelex_hosted_anthropic_extras import (  # ruff: ignore[import-outside-top-level]
        PipelexHostedAnthropicExtrasFactory,
    )

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
        extras_factory=PipelexHostedAnthropicExtrasFactory(),
    )


def _make_pipelex_hosted_completions_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,
    sdk_clients: SdkClientRegistry,
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    from pipelex.providers.openai.openai_completions_llm_worker import OpenAICompletionsLLMWorker  # ruff: ignore[import-outside-top-level]
    from pipelex.providers.pipelex_hosted.pipelex_hosted_completions_factory import (  # ruff: ignore[import-outside-top-level]
        PipelexHostedCompletionsFactory,
    )

    model_handle = ModelHandle.make_for_inference_model(inference_model=inference_model)
    sdk_instance = sdk_clients.get_or_create(
        handle=model_handle,
        build=lambda: PipelexHostedCompletionsFactory.make_openai_client_for_completions(model_handle=model_handle, backend=backend),
    )
    return OpenAICompletionsLLMWorker(
        openai_completions_factory=PipelexHostedCompletionsFactory(is_http_url_enabled=False),
        sdk_instance=sdk_instance,
        inference_model=inference_model,
        reporting_delegate=reporting_delegate,
    )


def _make_pipelex_hosted_responses_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,
    sdk_clients: SdkClientRegistry,
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    from pipelex.providers.openai.openai_responses_llm_worker import OpenAIResponsesLLMWorker  # ruff: ignore[import-outside-top-level]
    from pipelex.providers.pipelex_hosted.pipelex_hosted_responses_factory import (  # ruff: ignore[import-outside-top-level]
        PipelexHostedResponsesFactory,
    )

    model_handle = ModelHandle.make_for_inference_model(inference_model=inference_model)
    sdk_instance = sdk_clients.get_or_create(
        handle=model_handle,
        build=lambda: PipelexHostedResponsesFactory.make_openai_client_for_responses(model_handle=model_handle, backend=backend),
    )
    return OpenAIResponsesLLMWorker(
        openai_responses_factory=PipelexHostedResponsesFactory(is_http_url_enabled=False),
        sdk_instance=sdk_instance,
        inference_model=inference_model,
        reporting_delegate=reporting_delegate,
    )


def _make_pipelex_hosted_completions_img_gen_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,
    sdk_clients: SdkClientRegistry,
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    from pipelex.providers.openai.openai_completions_img_gen_worker import OpenAICompletionsImgGenWorker  # ruff: ignore[import-outside-top-level]
    from pipelex.providers.pipelex_hosted.pipelex_hosted_completions_factory import (  # ruff: ignore[import-outside-top-level]
        PipelexHostedCompletionsFactory,
    )
    from pipelex.tools.misc.image_utils import ImageFormat  # ruff: ignore[import-outside-top-level]

    model_handle = ModelHandle.make_for_inference_model(inference_model=inference_model)
    sdk_instance = sdk_clients.get_or_create(
        handle=model_handle,
        build=lambda: PipelexHostedCompletionsFactory.make_openai_client_for_completions(model_handle=model_handle, backend=backend),
    )
    return OpenAICompletionsImgGenWorker(
        openai_completions_factory=PipelexHostedCompletionsFactory(is_http_url_enabled=False),
        sdk_instance=sdk_instance,
        inference_model=inference_model,
        reporting_delegate=reporting_delegate,
        fixed_output_format=ImageFormat.PNG,
    )


def _make_pipelex_hosted_img_gen_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,
    sdk_clients: SdkClientRegistry,
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    from pipelex.providers.pipelex_hosted.pipelex_hosted_factory import PipelexHostedFactory  # ruff: ignore[import-outside-top-level]
    from pipelex.providers.pipelex_hosted.pipelex_hosted_img_gen_worker import PipelexHostedImgGenWorker  # ruff: ignore[import-outside-top-level]

    model_handle = ModelHandle.make_for_inference_model(inference_model=inference_model)
    sdk_instance = sdk_clients.get_or_create(
        handle=model_handle,
        build=lambda: PipelexHostedFactory.make_portkey_client(backend=backend),
    )
    return PipelexHostedImgGenWorker(
        sdk_instance=sdk_instance,
        inference_model=inference_model,
        reporting_delegate=reporting_delegate,
    )


def _make_pipelex_hosted_extract_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,
    sdk_clients: SdkClientRegistry,
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    from pipelex.providers.pipelex_hosted.pipelex_hosted_extract_worker import PipelexHostedExtractWorker  # ruff: ignore[import-outside-top-level]
    from pipelex.providers.pipelex_hosted.pipelex_hosted_native_client import PipelexHostedNativeClient  # ruff: ignore[import-outside-top-level]

    model_handle = ModelHandle.make_for_inference_model(inference_model=inference_model)
    sdk_instance = sdk_clients.get_or_create(handle=model_handle, build=lambda: PipelexHostedNativeClient(backend=backend))
    return PipelexHostedExtractWorker(
        sdk_instance=sdk_instance,
        extra_config=backend.extra_config,
        inference_model=inference_model,
        reporting_delegate=reporting_delegate,
    )


def _make_pipelex_hosted_search_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,
    sdk_clients: SdkClientRegistry,
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    from pipelex.providers.pipelex_hosted.pipelex_hosted_native_client import PipelexHostedNativeClient  # ruff: ignore[import-outside-top-level]
    from pipelex.providers.pipelex_hosted.pipelex_hosted_search_worker import PipelexHostedSearchWorker  # ruff: ignore[import-outside-top-level]

    model_handle = ModelHandle.make_for_inference_model(inference_model=inference_model)
    sdk_instance = sdk_clients.get_or_create(handle=model_handle, build=lambda: PipelexHostedNativeClient(backend=backend))
    return PipelexHostedSearchWorker(
        sdk_instance=sdk_instance,
        inference_model=inference_model,
        reporting_delegate=reporting_delegate,
    )


class PipelexHostedPlugin:
    """Built-in driver for the Pipelex service, serving all inference families."""

    name = "manifold"
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_service_error_codes(codes=PIPELEX_HOSTED_SERVICE_ERROR_CODES)
        registrar.add_inference_backend(family=InferenceFamily.LLM, sdk=PipelexHostedSdk.ANTHROPIC, make_worker=_make_pipelex_hosted_anthropic_worker)
        registrar.add_inference_backend(
            family=InferenceFamily.LLM, sdk=PipelexHostedSdk.COMPLETIONS, make_worker=_make_pipelex_hosted_completions_worker
        )
        registrar.add_inference_backend(family=InferenceFamily.LLM, sdk=PipelexHostedSdk.RESPONSES, make_worker=_make_pipelex_hosted_responses_worker)
        registrar.add_inference_backend(family=InferenceFamily.IMG_GEN, sdk=PipelexHostedSdk.IMG_GEN, make_worker=_make_pipelex_hosted_img_gen_worker)
        registrar.add_inference_backend(
            family=InferenceFamily.IMG_GEN, sdk=PipelexHostedSdk.COMPLETIONS, make_worker=_make_pipelex_hosted_completions_img_gen_worker
        )
        registrar.add_inference_backend(family=InferenceFamily.EXTRACT, sdk=PipelexHostedSdk.EXTRACT, make_worker=_make_pipelex_hosted_extract_worker)
        registrar.add_inference_backend(family=InferenceFamily.SEARCH, sdk=PipelexHostedSdk.SEARCH, make_worker=_make_pipelex_hosted_search_worker)
