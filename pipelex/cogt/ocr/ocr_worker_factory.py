from typing import Optional

from pipelex.cogt.exceptions import MissingDependencyError
from pipelex.cogt.ocr.ocr_engine import OcrEngine
from pipelex.cogt.ocr.ocr_platform import OcrPlatform
from pipelex.cogt.ocr.ocr_worker_abstract import OcrWorkerAbstract
from pipelex.hub import get_models_manager, get_plugin_manager
from pipelex.plugins.plugin_sdk_registry import Plugin
from pipelex.reporting.reporting_protocol import ReportingProtocol


class OcrWorkerFactory:
    def make_ocr_worker(
        self,
        ocr_engine: OcrEngine,
        reporting_delegate: Optional[ReportingProtocol] = None,
    ) -> OcrWorkerAbstract:
        backend = get_models_manager().get_required_inference_backend("mistral")
        ocr_plugin = Plugin.make_for_ocr_engine(ocr_platform=ocr_engine.ocr_platform)
        plugin_sdk_registry = get_plugin_manager().plugin_sdk_registry
        ocr_worker: OcrWorkerAbstract
        match ocr_engine.ocr_platform:
            case OcrPlatform.MISTRAL:
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

                ocr_sdk_instance = plugin_sdk_registry.get_sdk_instance(plugin=ocr_plugin) or plugin_sdk_registry.set_sdk_instance(
                    plugin=ocr_plugin,
                    sdk_instance=MistralFactory.make_mistral_client(backend=backend),
                )

                ocr_worker = MistralOcrWorker(
                    sdk_instance=ocr_sdk_instance,
                    ocr_engine=ocr_engine,
                    reporting_delegate=reporting_delegate,
                )
            case OcrPlatform.BASIC:
                from pipelex.plugins.pypdfium2.pypdfium2_worker import Pypdfium2Worker

                ocr_worker = Pypdfium2Worker(
                    sdk_instance=None,
                    ocr_engine=ocr_engine,
                    reporting_delegate=reporting_delegate,
                )

        return ocr_worker
