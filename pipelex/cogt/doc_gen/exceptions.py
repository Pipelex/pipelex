from pipelex.base_exceptions import ErrorDomain, PipelexError
from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource

# The package whose engines print what open Pipelex does not: a PDF from a template, Excel, Word and PowerPoint.
DOC_GEN_PLUGIN_PACKAGE = "pipelex-doc-gen"
# The sdk of the engine built into open Pipelex, `reportlab-pdf`; every other doc gen sdk is the plugin's.
BUILT_IN_DOC_GEN_SDK = "reportlab"


def _step_label(*, pipe_code: str | None) -> str:
    return f"PipeDocGen '{pipe_code}'" if pipe_code else "A PipeDocGen step"


class DocGenEngineMissingError(PipelexError):
    """The document engine a `PipeDocGen` step prints with is not available in this runtime.

    Either the model deck names no engine for the step's format and source and the step names none, or the
    engine's model has no worker registered here: open Pipelex registers `reportlab-pdf`'s, and the Pipelex
    document generation plugin registers the rest. Raised when the method loads, before a run spends anything,
    and again by the print stage should the engine have gone since. A runtime that disables the built-in plugin
    and installs no other refuses every `PipeDocGen` step this way. Its message names only the step, the format,
    the source, the engine and the plugin, so it is kept verbatim for the caller.
    """

    error_domain = ErrorDomain.INPUT
    _authors_caller_facing_message = True

    def __init__(
        self,
        *,
        doc_gen_format: DocGenFormat,
        source: DocGenSource,
        model: str | None,
        sdk: str | None,
        pipe_code: str | None = None,
    ):
        self.doc_gen_format = doc_gen_format
        self.source = source
        self.model = model
        self.sdk = sdk
        self.pipe_code = pipe_code
        asks = f"{_step_label(pipe_code=pipe_code)} asks for {doc_gen_format.with_article} {source.desc}"
        if model is None:
            message = (
                f"{asks}, and the model deck names no document engine for it. Name one with the step's 'model', "
                "or run `pipelex update` to get the kit's document generation deck."
            )
        elif sdk == BUILT_IN_DOC_GEN_SDK:
            message = f"{asks}, on the engine '{model}', which is built into Pipelex and disabled in this runtime."
        else:
            message = (
                f"{asks}, on the engine '{model}', which is not installed in this runtime. It comes with the Pipelex "
                f"document generation plugin, {DOC_GEN_PLUGIN_PACKAGE}."
            )
        super().__init__(message)


class DocGenModelCapabilityError(PipelexError):
    """The document engine a `PipeDocGen` step names does not print the step's format from its source.

    A `doc_gen` model lists the sources it prints from as its `inputs` and its format as its `outputs`, and a step
    that names one outside them is refused when the method loads.
    """

    error_domain = ErrorDomain.INPUT
    _authors_caller_facing_message = True

    def __init__(self, *, doc_gen_format: DocGenFormat, source: DocGenSource, model: str, pipe_code: str | None = None):
        self.doc_gen_format = doc_gen_format
        self.source = source
        self.model = model
        self.pipe_code = pipe_code
        message = (
            f"{_step_label(pipe_code=pipe_code)} asks the engine '{model}' for {doc_gen_format.with_article} {source.desc}, which it does not print. "
            "Name an engine that does in the step's 'model', or leave 'model' out for the model deck's default."
        )
        super().__init__(message)


class DocGenRenderError(PipelexError):
    """A document engine could not print a render job.

    Engines raise it for what they cannot lay out, such as a table cell taller than a page, and the print stage
    raises it for an engine failure it did not expect. Engines outside Pipelex raise it too: it is part of the
    render contract (`render_job.py`).
    """

    error_domain = ErrorDomain.RUNTIME
