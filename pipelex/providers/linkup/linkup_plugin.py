from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.inference_backend_registry import InferenceFamily, require_sdk
from pipelex.plugins.registrar import PluginRegistrar
from pipelex.plugins.sdk_client_registry import SdkClientRegistry
from pipelex.reporting.reporting_protocol import ReportingProtocol

_LINKUP_MISSING_MSG = "The linkup SDK is required in order to use Linkup Fetch extraction models."
_LINKUP_SEARCH_MISSING_MSG = "The linkup SDK is required in order to use Linkup search models."


def _make_linkup_extract_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,
    sdk_clients: SdkClientRegistry,  # noqa: ARG001 - stateless worker, no SDK-client caching
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    require_sdk(spec="linkup", extra="linkup", msg=_LINKUP_MISSING_MSG)

    from pipelex.providers.linkup.linkup_extract_worker import LinkupExtractWorker  # noqa: PLC0415

    return LinkupExtractWorker(
        extra_config=backend.extra_config,
        inference_model=inference_model,
        reporting_delegate=reporting_delegate,
    )


def _make_linkup_search_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,  # noqa: ARG001 - uniform MakeWorkerFn signature; the search worker builds its own client
    sdk_clients: SdkClientRegistry,  # noqa: ARG001 - stateless worker, no SDK-client caching
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    require_sdk(spec="linkup", extra="linkup", msg=_LINKUP_SEARCH_MISSING_MSG)

    from pipelex.providers.linkup.linkup_search_worker import LinkupSearchWorker  # noqa: PLC0415

    return LinkupSearchWorker(
        inference_model=inference_model,
        reporting_delegate=reporting_delegate,
    )


class LinkupPlugin:
    """Built-in driver for Linkup, serving both the Extract (fetch) and Search families via the linkup SDK."""

    name = "linkup"
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_inference_backend(family=InferenceFamily.EXTRACT, sdk="linkup_fetch", make_worker=_make_linkup_extract_worker)
        registrar.add_inference_backend(family=InferenceFamily.SEARCH, sdk="linkup", make_worker=_make_linkup_search_worker)
