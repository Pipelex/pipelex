from enum import StrEnum
from typing import Any

from mthds.method_tree.vocabulary import TreeRefusalCode
from mthds.protocol.problem.models import ProblemLocation
from mthds.protocol.problem.registry import CoreCode
from typing_extensions import override

from pipelex.base_exceptions import PipelexError
from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource, doc_gen_choice_key
from pipelex.cogt.doc_gen.table_fill import TableFill
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.errors.error_code_declaration import ErrorCodeSet
from pipelex.errors.problem import make_location
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode

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

    @property
    def desc(self) -> str:
        """What is missing, as the operator's step names it after the engine."""
        match self:
            case DocGenEngineGap.NO_DEFAULT:
                return "the model deck names no default engine for the format"
            case DocGenEngineGap.NOT_DECLARED:
                return "its model is not declared in this installation"
            case DocGenEngineGap.NOT_REGISTERED:
                return "no installed plugin registers a worker for it"


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
    plugin and installs no other refuses every `PipeDocGen` step this way. Every remedy it names is the operator's,
    so it is ``pipelex.docgen.engine_unavailable``. Its message names only the step, the format, the source, the
    engine and the plugin, so it is kept verbatim for the caller.
    """

    error_code = PipelexErrorCode.DOCGEN_ENGINE_UNAVAILABLE

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

    @override
    def problem_params(self) -> dict[str, Any]:
        # The engine and the gap are the operator's own facts, operator-only parameters of the code.
        engine = self.model or f"default engine for {self.doc_gen_format.with_article} {self.source.desc}"
        return {"format": self.doc_gen_format, "engine": engine, "gap": self.gap.desc}


class DocGenModelCapabilityError(PipelexError):
    """The document engine a `PipeDocGen` step names does not print the step's format from its source, or does not fill its Tables the step's way.

    A `doc_gen` model lists the sources it prints from as its `inputs` and its format as its `outputs`, and a step
    that names one outside them is refused when the method loads. A fill of a template file's Tables other than
    `replace` is a capability the model lists among its `inputs` too (`TableFill.engine_capability`), and a step asking
    for one its engine does not declare is refused the same way, naming the fill: an engine that predates it would
    replace the Table's rows instead.
    """

    error_code = CoreCode.MODEL_CAPABILITY_UNSUPPORTED

    def __init__(
        self,
        *,
        doc_gen_format: DocGenFormat,
        source: DocGenSource,
        model: str,
        pipe_code: str | None = None,
        table_fill: TableFill | None = None,
    ):
        self.doc_gen_format = doc_gen_format
        self.source = source
        self.model = model
        self.pipe_code = pipe_code
        self.table_fill = table_fill
        message: str
        if table_fill is None:
            message = (
                f"{_step_label(pipe_code=pipe_code)} asks the engine '{model}' for {doc_gen_format.with_article} {source.desc}, "
                "which it does not print. Name an engine that does in the step's 'model', or leave 'model' out for the model deck's default."
            )
        else:
            message = (
                f"{_step_label(pipe_code=pipe_code)} asks the engine '{model}' to {table_fill.desc} (table_fill = \"{table_fill}\"), "
                f"which it does not do. Name an engine that declares '{table_fill.engine_capability}' in the step's 'model', "
                "or fill the template's Tables another way."
            )
        super().__init__(message)

    @override
    def problem_params(self) -> dict[str, Any]:
        capability = f"printing {self.doc_gen_format.with_article} {self.source.desc}"
        if self.table_fill is not None:
            capability = self.table_fill.engine_capability or capability
        return {"model": self.model, "capability": capability}


class DocGenRenderError(PipelexError):
    """A document engine could not print a render job.

    Engines raise it for what they cannot lay out, such as a table cell taller than a page, and the print stage
    raises it for an engine failure it did not expect. Engines outside Pipelex raise it too: it is part of the
    render contract (`render_job.py`).

    Its raise site chooses the code: ``pipelex.docgen.content_unprintable`` for the run's data an engine cannot lay
    out (an element taller than a page, an image that is not one), whose raise site gives the code's ``reason`` and
    ``element`` parameters; ``pipelex.docgen.print_timeout`` for a print stopped at its deadline;
    ``pipelex.docgen.resource_refused`` or ``security.method_url_refused`` for a file the printed document may not
    name; ``pipelex.docgen.template_invalid`` for a method's template file the print cannot read, or one whose
    engine's template check fails; ``pipelex.docgen.template_input_unfit`` for a template a run input supplies whose
    engine's template check fails; and
    ``runtime.unexpected``, the default, for an engine failure or a job an engine was never meant to get,
    since the step's engine was checked to print it before printing.
    """

    error_code = ErrorCodeSet(
        default=CoreCode.RUNTIME_UNEXPECTED,
        others=(
            PipelexErrorCode.DOCGEN_CONTENT_UNPRINTABLE,
            PipelexErrorCode.DOCGEN_PRINT_TIMEOUT,
            PipelexErrorCode.DOCGEN_RESOURCE_REFUSED,
            PipelexErrorCode.DOCGEN_TEMPLATE_INVALID,
            PipelexErrorCode.DOCGEN_TEMPLATE_INPUT_UNFIT,
            CoreCode.SECURITY_METHOD_URL_REFUSED,
        ),
    )


class MarkdownFormattingBudgetError(PipelexError):
    """Formatting a Markdown text outside any template render would spend more than the budget it gets of its own.

    `format_markdown` (`formatted_markdown.py`) raises it when an engine converts a value from its own code, as an
    Excel fill does, and the text, its tables or what they format into is too large; inside a template render, the
    render's own `RenderBudgetExceededError` is raised instead. The Markdown is the run's input, so the fault is the
    caller's, and the message names only the text's length and the budget, never the text. It is part of the document
    engine contract (`pipelex/plugins/contract.py`): an engine reports it as its own fill error, naming where the value
    goes.
    """

    error_code = CoreCode.INPUT_TOO_LARGE


class TemplateUrlRefusedError(PipelexError):
    """A relative URL of an HTML document names no image, stylesheet or font of its template's method tree, so the print reads nothing.

    A relative URL in a `PipeDocGen` step's HTML template, or in a stylesheet of the method tree the template links, names
    a file of the template's method tree, resolved by the MTHDS standard's rules for a relative URL and looked up in the
    tree's listing (`pipelex.cogt.doc_gen.method_file_urls`), never on a disk. The print refuses it when the standard does:
    it is malformed, it is not a tree path, it climbs above the tree's root, or the tree holds no file where it resolves,
    a directory and a file the tree's membership rule keeps out included. It also refuses a file of the tree that is not
    an image, a stylesheet or a font, such as the method's Python, bundles, manifest or data, since a URL may come from a
    run's input and a document can carry what it reads; a URL of a method file in a document with no HTML; and any
    relative URL of a template that belongs to no method tree, such as an inline template of a bundle loaded from a
    content string with no file submitted beside it. `refusal_code` is the standard's code for the refusal, and None for
    these last three, which the standard does not name. A URL the template writes as it is is checked when the method
    loads, so this is raised for one the run's input supplied.

    `RenderResources.load` raises it, and an engine lets it pass, as it lets the read scope's refusal pass. Every one of
    its refusals keeps a document inside its method tree's read perimeter, which a path that climbs out of the tree,
    names a file the tree keeps out or names the method's own code would cross, so it is ``security.method_path_refused``:
    a refused path into the method's tree, which its author bounds, rather than ``method.resource_missing``, a file the
    method itself refers to and lacks, which the load-time check already refuses for a URL the template writes. Its
    message names only the method's own files, by their tree paths, and where the URL sat in the document, so it is
    kept for the caller.
    """

    error_code = CoreCode.SECURITY_METHOD_PATH_REFUSED

    def __init__(self, message: str, *, refusal_code: TreeRefusalCode | None):
        super().__init__(message)
        self.refusal_code = refusal_code


class DocGenTemplateInputTooLargeError(PipelexError):
    """The file a run input supplies as a `PipeDocGen` step's template is larger than a file the runtime reads.

    A template is read whole and handed to the engine, so it is bounded by `[runtime.network] max_fetch_bytes`, the most a
    fetch reads, whatever kind of URI names it: a stored file is sized before it is read, a local file too, a data URL by
    the length of its text, and a URL's body as the fetch streams it, which raises the fetch's own `RemoteFileTooLargeError`
    naming the input. The input is the caller's, so it is ``input.too_large``, naming the input, the limit and the size.
    """

    error_code = CoreCode.INPUT_TOO_LARGE

    user_action = UserAction(
        kind=UserActionKind.CHANGE_INPUT,
        detail="Use a smaller file, or raise [runtime.network] max_fetch_bytes if you run the runtime yourself.",
    )

    def __init__(self, message: str, *, input_name: str, limit: int, size: int):
        """The refusal of a template input past the limit, named by the step's input, with the limit and the file's size.

        Args:
            message: What is wrong, naming the input and the sizes.
            input_name: The step's input whose file is the template.
            limit: The most bytes the runtime reads.
            size: The file's size in bytes, or as the length of its data URL tells it.
        """
        super().__init__(message)
        self.input_name = input_name
        self.limit = limit
        self.size = size

    @override
    def problem_params(self) -> dict[str, Any]:
        return {"input": self.input_name, "limit": self.limit, "size": self.size}

    @override
    def problem_location(self) -> ProblemLocation | None:
        return make_location(input_name=self.input_name)


class DocGenTemplateInputFormatError(PipelexError):
    """The file a run input supplies as a `PipeDocGen` step's template is not a file of the step's format.

    A step with `template_input` fills the input's file, so a Word document given to a step that fills an Excel workbook
    cannot be its template. The format is judged from the bytes first, an Office file being a zip whose content-types
    entry names its main part, then from the media type the document carries, then from its file name's suffix. Raised at
    run setup, by the check of a template a run input supplies, and by the print stage, which reads the file again. The
    input is the caller's, so it is ``input.file_type_unsupported``, its model the step's engine; the message names the
    input by its name and the formats in words, never the file's name or its URL.
    """

    error_code = CoreCode.INPUT_FILE_TYPE_UNSUPPORTED

    user_action = UserAction(
        kind=UserActionKind.CHANGE_INPUT,
        detail="Give the template input a file in the format the step fills.",
    )

    def __init__(self, message: str, *, input_name: str, file_format: str, model: str):
        """The refusal of a template input, named by the step's input, with the format judged and the engine that fills it.

        Args:
            message: What is wrong, naming the input and the formats.
            input_name: The step's input whose file is the template.
            file_format: The format the file was judged to be, `unknown` when nothing told.
            model: The engine that fills the step's template.
        """
        super().__init__(message)
        self.input_name = input_name
        self.file_format = file_format
        self.model = model

    @override
    def problem_params(self) -> dict[str, Any]:
        return {"input": self.input_name, "format": self.file_format, "model": self.model}

    @override
    def problem_location(self) -> ProblemLocation | None:
        return make_location(input_name=self.input_name)
