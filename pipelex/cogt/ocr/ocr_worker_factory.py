from typing import Optional

from pipelex.cogt.exceptions import MissingDependencyError
from pipelex.cogt.inference.inference_report_delegate import InferenceReportDelegate
from pipelex.cogt.ocr.ocr_engine import OcrEngine
from pipelex.cogt.ocr.ocr_platform import OcrPlatform
from pipelex.cogt.ocr.ocr_worker_abstract import OcrWorkerAbstract
from pipelex.cogt.plugin_manager import PluginHandle
from pipelex.hub import get_plugin_manager


class OcrWorkerFactory:
    def make_ocr_worker(
        self,
        ocr_engine: OcrEngine,
        report_delegate: Optional[InferenceReportDelegate] = None,
    ) -> OcrWorkerAbstract:
        ocr_sdk_handle = PluginHandle.get_for_ocr_engine(ocr_platform=ocr_engine.ocr_platform)
        plugin_manager = get_plugin_manager()
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

                ocr_sdk_instance = plugin_manager.get_ocr_sdk_instance(ocr_sdk_handle=ocr_sdk_handle) or plugin_manager.set_ocr_sdk_instance(
                    ocr_sdk_handle=ocr_sdk_handle,
                    ocr_sdk_instance=MistralFactory.make_mistral_client(),
                )

                ocr_worker = MistralOcrWorker(
                    sdk_instance=ocr_sdk_instance,
                    ocr_engine=ocr_engine,
                    report_delegate=report_delegate,
                )

        return ocr_worker
