from typing import Any

from mthds.protocol.problem.registry import CoreCode
from typing_extensions import override

from pipelex.base_exceptions import PipelexError
from pipelex.errors.error_code_declaration import ErrorCodeSet, InheritsCause
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode


class PipeDocGenFactoryError(PipelexError):
    """Raised when a ``PipeDocGen`` cannot be built from its blueprint.

    The output concept is not a Document, a template does not parse or reads a field its input does not have,
    or the template file is missing or cannot be resolved. It is raised only while the pipe is built, about the
    author's own blueprint, so it is the author's to fix and its messages name only the author's pipe, concepts,
    fields, template and file path. Its code defaults to a template that does not parse; the raise site chooses
    the code of what else it found.
    """

    error_code = ErrorCodeSet(
        default=CoreCode.METHOD_TEMPLATE_INVALID,
        others=(
            CoreCode.METHOD_OUTPUT_CONCEPT_MISMATCH,
            CoreCode.METHOD_RESOURCE_MISSING,
            CoreCode.SECURITY_METHOD_PATH_REFUSED,
            CoreCode.METHOD_INPUT_UNDECLARED,
            CoreCode.METHOD_FIELD_PATH_UNRESOLVED,
        ),
    )

    def __init__(self, message: str, *, facts: dict[str, Any] | None = None):
        """The refusal, and the facts its raise site knows, by the parameter names its codes give them.

        Each raise site chooses one of several codes declaring different parameters, so it gives every fact it holds,
        and the problem keeps the ones its code declares, where :meth:`with_params` would log the others.
        """
        super().__init__(message)
        self.facts = facts or {}

    @override
    def problem_params(self) -> dict[str, Any]:
        return dict(self.facts)


class PipeDocGenRunError(PipelexError):
    """Raised when a ``PipeDocGen`` step fails while it composes its document: a template or the filename does not render.

    It takes the code of the render failure it wraps, else a template that failed to render; a raise site finding an
    invariant the load and the crate guarantee broken chooses ``runtime.unexpected``, and one naming a template that
    cannot render as written, with its field and what Jinja2 refused, chooses ``method.template_invalid``.
    """

    error_code = InheritsCause(fallback=CoreCode.PIPE_TEMPLATE_RENDER_FAILED, others=(CoreCode.RUNTIME_UNEXPECTED, CoreCode.METHOD_TEMPLATE_INVALID))


class PipeDocGenUndefinedValueError(PipelexError):
    """Raised when a ``PipeDocGen`` template or filename reads a value its inputs do not have.

    Its templates render with a strict undefined, so a field the load-time check could not follow, such as one
    read through a ``{% set %}`` alias, fails here rather than printing as empty text, at the dry run when the
    template names a field its concept lacks. The template is always the method author's own, unlike the
    renders ``Jinja2TemplateRenderError`` also serves, so the message is the author's to read: it names the pipe,
    the template or the filename, and the missing name, and it never quotes the template's source.
    """

    error_code = CoreCode.PIPE_TEMPLATE_RENDER_FAILED


class PipeDocGenTemplateCheckError(PipelexError):
    """Raised by a ``PipeDocGen`` dry run when the engine's template checker reports errors in the step's template file.

    The dry run is what ``pipelex validate`` runs, so a template naming a field the inputs do not have fails there,
    before anything is spent. Its message lists the checker's findings, which name only the author's template,
    names and fields. PipeDocGen is not in the MTHDS standard, hence a Pipelex code.
    """

    error_code = PipelexErrorCode.DOCGEN_TEMPLATE_INVALID


class PipeDocGenTemplateFileUncheckedError(PipelexError):
    """Raised when a ``PipeDocGen`` step built from a library crate is validated where its HTML template file is not at hand.

    An HTML template file's checks read the file: the variables it reads are inputs of the step, the fields it reads are
    fields of their concepts, and every reference to an optional input is guarded. A crate names the step's method tree
    by digest and carries none of its files, so a validation of the crate reads the file from a tree a library of this
    process holds, and reaches the verdict the load where the crate was assembled reached. Where no library holds the
    tree, the validation cannot reach it, and refuses rather than pass the step unchecked. The fault is where the crate
    was validated, not in the method, and the message names only the step and the template file's tree path: this
    runtime cannot serve the validation, which a runtime holding the method's files can.
    """

    error_code = CoreCode.RUNTIME_UNSUPPORTED
