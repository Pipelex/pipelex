from typing import Optional

from pipelex.cogt.exceptions import MissingDependencyError
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.ocr.ocr_worker_abstract import OcrWorkerAbstract
from pipelex.hub import get_models_manager, get_plugin_manager
from pipelex.plugins.plugin_sdk_registry import Plugin
from pipelex.reporting.reporting_protocol import ReportingProtocol


class OcrWorkerFactory:
    def make_ocr_worker(
        self,
        inference_model: InferenceModelSpec,
        reporting_delegate: Optional[ReportingProtocol] = None,
    ) -> OcrWorkerAbstract:
        plugin = Plugin.make_for_inference_model(inference_model=inference_model)
        backend = get_models_manager().get_required_inference_backend(inference_model.backend_name)
        plugin_sdk_registry = get_plugin_manager().plugin_sdk_registry
        ocr_worker: OcrWorkerAbstract
        match plugin.sdk:
            case "mistral":
                try:
                    import mistralai  # noqa: F401
                except ImportError as exc:
                    raise MissingDependencyError(
                        "mistralai",
                        "mistral",
                        "The mistralai SDK is required to use Mistral OCR models through the mistralai client.",
                    ) from exc

                from pipelex.plugins.mistral.mistral_factory import MistralFactory
                from pipelex.plugins.mistral.mistral_ocr_worker import MistralOcrWorker

                ocr_sdk_instance = plugin_sdk_registry.get_sdk_instance(plugin=plugin) or plugin_sdk_registry.set_sdk_instance(
                    plugin=plugin,
                    sdk_instance=MistralFactory.make_mistral_client(backend=backend),
                )

                ocr_worker = MistralOcrWorker(
                    sdk_instance=ocr_sdk_instance,
                    extra_config=backend.extra_config,
                    inference_model=inference_model,
                    reporting_delegate=reporting_delegate,
                )
            case "pypdfium2":
                from pipelex.plugins.pypdfium2.pypdfium2_worker import Pypdfium2Worker

                ocr_worker = Pypdfium2Worker(
                    sdk_instance=None,
                    extra_config=backend.extra_config,
                    inference_model=inference_model,
                    reporting_delegate=reporting_delegate,
                )
            case _:
                raise NotImplementedError(f"Plugin '{plugin}' is not supported")

        return ocr_worker
