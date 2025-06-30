from typing import Optional

from pipelex.cogt.exceptions import MissingDependencyError
from pipelex.cogt.ocr.ocr_engine import OcrEngine
from pipelex.cogt.ocr.ocr_platform import OcrPlatform
from pipelex.cogt.ocr.ocr_worker_abstract import OcrWorkerAbstract
from pipelex.hub import get_plugin_manager
from pipelex.plugins.plugin_sdk_registry import PluginSdkHandle
from pipelex.reporting.reporting_protocol import ReportingProtocol


class OcrWorkerFactory:
    def make_ocr_worker(
        self,
        ocr_engine: OcrEngine,
        reporting_delegate: Optional[ReportingProtocol] = None,
    ) -> OcrWorkerAbstract:
        ocr_sdk_handle = PluginSdkHandle.get_for_ocr_engine(ocr_platform=ocr_engine.ocr_platform)
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

                ocr_sdk_instance = plugin_sdk_registry.get_ocr_sdk_instance(
                    ocr_sdk_handle=ocr_sdk_handle
                ) or plugin_sdk_registry.set_ocr_sdk_instance(
                    ocr_sdk_handle=ocr_sdk_handle,
                    ocr_sdk_instance=MistralFactory.make_mistral_client(),
                )

                ocr_worker = MistralOcrWorker(
                    sdk_instance=ocr_sdk_instance,
                    ocr_engine=ocr_engine,
                    reporting_delegate=reporting_delegate,
                )

        return ocr_worker
