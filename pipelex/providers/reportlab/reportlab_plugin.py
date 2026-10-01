from pipelex.cogt.doc_gen.exceptions import BUILT_IN_DOC_GEN_SDK
from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.inference_backend_registry import InferenceFamily
from pipelex.plugins.registrar import PluginRegistrar
from pipelex.plugins.sdk_client_registry import SdkClientRegistry
from pipelex.reporting.reporting_protocol import ReportingProtocol


def _make_reportlab_pdf_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,  # ruff: ignore[unused-function-argument] - a local engine, with no backend settings
    sdk_clients: SdkClientRegistry,  # ruff: ignore[unused-function-argument] - stateless worker, no SDK-client caching
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    from pipelex.providers.reportlab.reportlab_pdf_renderer import ReportlabPdfWorker  # ruff: ignore[import-outside-top-level]

    return ReportlabPdfWorker(inference_model=inference_model, reporting_delegate=reporting_delegate)


class ReportlabDocGenPlugin:
    """Built-in document engine `reportlab-pdf`: it prints a `pdf` from the auto-layout of a `PipeDocGen` step's inputs.

    Registering imports nothing of ReportLab: the factory imports the worker's module, which imports ReportLab, the
    first time a document is printed with it, and the worker registers the bundled fonts once per process.
    """

    name = "reportlab"
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_inference_backend(family=InferenceFamily.DOC_GEN, sdk=BUILT_IN_DOC_GEN_SDK, make_worker=_make_reportlab_pdf_worker)
