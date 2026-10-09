from abc import abstractmethod

from typing_extensions import override

from pipelex.cogt.doc_gen.render_job import RenderedDocument, RenderJob, RenderResources
from pipelex.cogt.doc_gen.template_check import TemplateCheckRequest, TemplateFinding
from pipelex.cogt.inference.inference_call_summary import InferenceCallSummary, InferenceOperation
from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.reporting.reporting_protocol import ReportingProtocol


class DocGenWorkerAbstract(InferenceWorkerAbstract):
    """A document engine: the worker of a `doc_gen` model, which prints a render job, synchronously.

    It is part of the plugin contract. An engine registers a factory for its worker with
    `registrar.add_inference_backend(family=InferenceFamily.DOC_GEN, sdk=…)`, and the kit's `internal.toml`
    declares its model, with the sources it prints from as `inputs` and its format as `outputs`. Open Pipelex
    registers `reportlab`; the Pipelex document generation plugin registers the rest from outside this repository.

    A worker is made for each print, and `render` runs on a thread of the print pool, never on the event loop, so
    an engine loads its library once per process, in the module that holds its worker, rather than per worker.
    """

    def __init__(self, *, inference_model: InferenceModelSpec, reporting_delegate: ReportingProtocol | None = None):
        super().__init__(reporting_delegate=reporting_delegate)
        self.inference_model = inference_model

    @property
    @override
    def desc(self) -> str:
        return f"Document generation using {self.inference_model.desc}"

    def print_document(self, *, job: RenderJob, resources: RenderResources) -> RenderedDocument:
        """Print the job with `render`, ending the call with the summary event every inference call ends with.

        This is how Pipelex prints, and an engine overrides `render` alone. A document engine reports no usage, so the
        event carries no tokens and no cost, never a zero standing for either.

        Raises:
            DocGenRenderError: the engine cannot print this job.
        """
        with InferenceCallSummary(operation=InferenceOperation.DOC_GEN, inference_model=self.inference_model, read_tokens_usage=None):
            return self.render(job=job, resources=resources)

    @abstractmethod
    def render(self, *, job: RenderJob, resources: RenderResources) -> RenderedDocument:
        """Print the job, reading every file its document names through `resources`.

        Raises:
            DocGenRenderError: the engine cannot print this job, such as a table cell taller than a page.
        """

    def check_template(self, *, request: TemplateCheckRequest) -> list[TemplateFinding]:
        """Compare a template file with the inputs it is filled with, for the dry run and so `pipelex validate`.

        An office template names its fields in its own way, which only its engine can read, so an engine that fills
        template files overrides this. The default finds nothing: the built-in PDF engine takes no template, and
        Pipelex checks HTML templates itself. An error finding fails the step, and a warning is logged. It raises
        only for a fault of its own: a template it cannot read at all is an error finding.
        """
        _ = request
        return []
