from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.inference_backend_registry import InferenceFamily, require_sdk
from pipelex.plugins.model_handle import ModelHandle
from pipelex.plugins.registrar import PluginRegistrar
from pipelex.plugins.sdk_client_registry import SdkClientRegistry
from pipelex.reporting.reporting_protocol import ReportingProtocol

_TYPESAFE_MISSING_MSG = "The typesafe-sdk package is required in order to use TypeSafe judgment models."


def _make_typesafe_judgment_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,
    sdk_clients: SdkClientRegistry,
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    require_sdk(spec="typesafe_sdk", extra="typesafe", msg=_TYPESAFE_MISSING_MSG)

    from pipelex.providers.typesafe.typesafe_client_factory import make_typesafe_client  # ruff: ignore[import-outside-top-level]
    from pipelex.providers.typesafe.typesafe_judgment_worker import TypesafeJudgmentWorker  # ruff: ignore[import-outside-top-level]

    model_handle = ModelHandle.make_for_inference_model(inference_model=inference_model)
    sdk_instance = sdk_clients.get_or_create(
        handle=model_handle,
        build=lambda: make_typesafe_client(backend=backend),
    )
    return TypesafeJudgmentWorker(
        sdk_instance=sdk_instance,
        inference_model=inference_model,
        reporting_delegate=reporting_delegate,
    )


class TypesafePlugin:
    """Built-in driver for TypeSafe, the judgment family's first backend, via the typesafe-sdk package."""

    name = "typesafe"
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_inference_backend(family=InferenceFamily.JUDGMENT, sdk="typesafe", make_worker=_make_typesafe_judgment_worker)
