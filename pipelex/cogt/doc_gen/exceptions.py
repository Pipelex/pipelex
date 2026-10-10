from enum import StrEnum

from pipelex.base_exceptions import ErrorDomain, PipelexError
from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource, doc_gen_choice_key

# The package whose engines print what open Pipelex does not: a PDF from a template, Excel, Word and PowerPoint.
DOC_GEN_PLUGIN_PACKAGE = "pipelex-doc-gen"
# The sdk of the engine built into open Pipelex, `reportlab-pdf`; every other doc gen sdk is the plugin's.
BUILT_IN_DOC_GEN_SDK = "reportlab"
# The engine built into open Pipelex, declared in the kit's `internal.toml`, which `pipelex update` refreshes.
BUILT_IN_DOC_GEN_MODEL = "reportlab-pdf"
# The one format and source the built-in engine prints, keyed as the model deck keys its defaults: the kit's deck
# declares its default, and the plugin declares every other one.
BUILT_IN_DOC_GEN_CHOICE_KEY = doc_gen_choice_key(doc_gen_format=DocGenFormat.PDF, source=DocGenSource.LAYOUT)
# The engines the plugin declares when it loads, by the model names a step may use. Core knows them only to say
# where a missing one comes from.
DOC_GEN_PLUGIN_MODEL_NAMES: frozenset[str] = frozenset({"pipelex-pdf", "pipelex-xlsx", "pipelex-docx", "pipelex-pptx"})
# Every engine name whose absence is refused naming its remedy, rather than as an unknown model.
KNOWN_DOC_GEN_MODEL_NAMES: frozenset[str] = DOC_GEN_PLUGIN_MODEL_NAMES | {BUILT_IN_DOC_GEN_MODEL}


class DocGenEngineGap(StrEnum):
    """What is missing when a `PipeDocGen` step's engine is not available, which decides the remedy its refusal names."""

    NO_DEFAULT = "no_default"
    """The step names no engine, and the model deck names no default for its format and source."""

    NOT_DECLARED = "not_declared"
    """The step's engine is the built-in one or one of the plugin's, and this installation does not declare its model."""

    NOT_REGISTERED = "not_registered"
    """The engine's model is declared, and no installed plugin registers a worker for its sdk."""


def _step_label(*, pipe_code: str | None) -> str:
    return f"PipeDocGen '{pipe_code}'" if pipe_code else "A PipeDocGen step"


class DocGenEngineMissingError(PipelexError):
    """The document engine a `PipeDocGen` step prints with is not available in this runtime.

    `gap` says what is missing, and the message names its remedy. The deck may name no engine for the step's format
    and source, which the kit's deck does only for a `pdf` from the auto-layout: every other default comes with the
    Pipelex document generation plugin. The engine's model may not be declared here: open Pipelex declares
    `reportlab-pdf` in the kit's `internal.toml`, which `pipelex update` refreshes, and the plugin declares its own
    engines when it loads. Or the model may be declared with no worker registered for it: open Pipelex registers
    `reportlab-pdf`'s, and the plugin registers the rest. Raised when the method loads, before a run spends
    anything, and again by the print stage should the engine have gone since. A runtime that disables the built-in
    plugin and installs no other refuses every `PipeDocGen` step this way. Its message names only the step, the
    format, the source, the engine and the plugin, so it is kept verbatim for the caller.
    """

    error_domain = ErrorDomain.INPUT
    _authors_caller_facing_message = True

    def __init__(
        self,
        *,
        gap: DocGenEngineGap,
        doc_gen_format: DocGenFormat,
        source: DocGenSource,
        model: str | None,
        sdk: str | None,
        pipe_code: str | None = None,
    ):
        self.gap = gap
        self.doc_gen_format = doc_gen_format
        self.source = source
        self.model = model
        self.sdk = sdk
        self.pipe_code = pipe_code
        asks = f"{_step_label(pipe_code=pipe_code)} asks for {doc_gen_format.with_article} {source.desc}"
        comes_with_the_plugin = f"It comes with the Pipelex document generation plugin, {DOC_GEN_PLUGIN_PACKAGE}."
        message: str
        match gap:
            case DocGenEngineGap.NO_DEFAULT:
                if doc_gen_choice_key(doc_gen_format=doc_gen_format, source=source) == BUILT_IN_DOC_GEN_CHOICE_KEY:
                    message = (
                        f"{asks}, and the model deck names no document engine for it. Name one with the step's 'model', "
                        "or run `pipelex update` to get the kit's document generation deck."
                    )
                else:
                    message = f"{asks}, and no document engine for it is installed in this runtime. {comes_with_the_plugin}"
            case DocGenEngineGap.NOT_DECLARED:
                if model == BUILT_IN_DOC_GEN_MODEL:
                    message = (
                        f"{asks}, on the engine '{model}', which is built into Pipelex and not declared in this installation's "
                        "inference backends. Run `pipelex update` to refresh backends/internal.toml from the kit."
                    )
                else:
                    message = f"{asks}, on the engine '{model}', which is not installed in this runtime. {comes_with_the_plugin}"
            case DocGenEngineGap.NOT_REGISTERED:
                if sdk == BUILT_IN_DOC_GEN_SDK:
                    message = f"{asks}, on the engine '{model}', which is built into Pipelex and disabled in this runtime."
                else:
                    message = f"{asks}, on the engine '{model}', which is not installed in this runtime. {comes_with_the_plugin}"
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


class MarkdownFormattingBudgetError(PipelexError):
    """Formatting a Markdown text outside any template render would spend more than the budget it gets of its own.

    `format_markdown` (`formatted_markdown.py`) raises it when an engine converts a value from its own code, as an
    Excel fill does, and the text, its tables or what they format into is too large; inside a template render, the
    render's own `RenderBudgetExceededError` is raised instead. The Markdown is the run's input, so the fault is the
    caller's, and the message names only the text's length and the budget, never the text. It is part of the document
    engine contract (`pipelex/plugins/contract.py`): an engine reports it as its own fill error, naming where the value
    goes.
    """

    error_domain = ErrorDomain.INPUT
    _authors_caller_facing_message = True
    _declared_title = "Markdown formatting budget exceeded"
