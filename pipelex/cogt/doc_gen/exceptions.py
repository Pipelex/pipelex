from pipelex.base_exceptions import ErrorDomain, PipelexError
from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource

# The package whose engines print what open Pipelex does not: a PDF from a template, Excel, Word and PowerPoint.
DOC_GEN_PLUGIN_PACKAGE = "pipelex-doc-gen"


class DocGenEngineMissingError(PipelexError):
    """No document engine installed in this runtime prints the format a `PipeDocGen` step asks for, from its source.

    Raised when the method loads, before a run spends anything, and again by the print stage should the engine
    have gone since. Open Pipelex prints a `pdf` laid out without a template; a `pdf` from a template, `xlsx`,
    `docx` and `pptx` are printed by the Pipelex document generation plugin. A runtime that disables the
    built-in engine and installs no plugin refuses every `PipeDocGen` step this way. Its message names only the
    format, the source and the plugin, so it is kept verbatim for the caller.
    """

    error_domain = ErrorDomain.INPUT
    _authors_caller_facing_message = True

    def __init__(self, *, doc_gen_format: DocGenFormat, source: DocGenSource, pipe_code: str | None = None):
        self.doc_gen_format = doc_gen_format
        self.source = source
        self.pipe_code = pipe_code
        step = f"PipeDocGen '{pipe_code}'" if pipe_code else "A PipeDocGen step"
        if doc_gen_format == DocGenFormat.PDF and source == DocGenSource.LAYOUT:
            where = "Open Pipelex prints it with its built-in engine, which this runtime has disabled."
        else:
            where = f"The engines for it come with the Pipelex document generation plugin, {DOC_GEN_PLUGIN_PACKAGE}, which is not installed here."
        message = f"{step} asks for a {doc_gen_format} {source.desc}, and no document engine installed in this runtime prints it. {where}"
        super().__init__(message)


class DocGenRenderError(PipelexError):
    """A document engine could not print a render job.

    Engines raise it for what they cannot lay out, such as a table cell taller than a page, and the print stage
    raises it for an engine failure it did not expect. Engines outside Pipelex raise it too: it is part of the
    render contract (`render_job.py`).
    """

    error_domain = ErrorDomain.RUNTIME
