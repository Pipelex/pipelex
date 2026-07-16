from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.inference_backend_registry import InferenceFamily
from pipelex.plugins.registrar import PluginRegistrar
from pipelex.plugins.sdk_client_registry import SdkClientRegistry
from pipelex.reporting.reporting_protocol import ReportingProtocol


def _make_pypdfium2_extract_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,
    sdk_clients: SdkClientRegistry,  # noqa: ARG001 - stateless worker, no SDK-client caching
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    from pipelex.plugins.pypdfium2.pypdfium2_worker import Pypdfium2Worker  # noqa: PLC0415

    return Pypdfium2Worker(
        extra_config=backend.extra_config,
        inference_model=inference_model,
        reporting_delegate=reporting_delegate,
    )


class Pypdfium2Plugin:
    """Built-in driver for local PDF text extraction via pypdfium2 (stateless, no remote SDK)."""

    name = "pypdfium2"
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_inference_backend(family=InferenceFamily.EXTRACT, sdk="pypdfium2", make_worker=_make_pypdfium2_extract_worker)
