from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.inference_backend_registry import InferenceFamily, require_sdk
from pipelex.plugins.model_handle import ModelHandle
from pipelex.plugins.registrar import PluginRegistrar
from pipelex.plugins.sdk_client_registry import SdkClientRegistry
from pipelex.reporting.reporting_protocol import ReportingProtocol

_DOCLING_MISSING_MSG = "The docling library is required in order to use Docling for PDF and image text extraction."


def _make_docling_extract_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,
    sdk_clients: SdkClientRegistry,
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    require_sdk(spec="docling", extra="docling", msg=_DOCLING_MISSING_MSG)

    from pipelex.providers.docling.docling_extract_worker import DoclingExtractWorker  # ruff: ignore[import-outside-top-level]
    from pipelex.providers.docling.docling_factory import DoclingFactory  # ruff: ignore[import-outside-top-level]

    model_handle = ModelHandle.make_for_inference_model(inference_model=inference_model)
    sdk_instance = sdk_clients.get_or_create(
        handle=model_handle,
        build=DoclingFactory.make_docling_sdk,
    )
    return DoclingExtractWorker(
        sdk_instance=sdk_instance,
        extra_config=backend.extra_config,
        inference_model=inference_model,
        reporting_delegate=reporting_delegate,
    )


class DoclingPlugin:
    """Built-in driver for Docling PDF/image text extraction via the docling library."""

    name = "docling"
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_inference_backend(family=InferenceFamily.EXTRACT, sdk="docling_sdk", make_worker=_make_docling_extract_worker)
