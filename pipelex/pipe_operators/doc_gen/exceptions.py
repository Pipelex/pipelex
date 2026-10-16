from pipelex.base_exceptions import ErrorDomain, PipelexError


class PipeDocGenFactoryError(PipelexError):
    """Raised when a ``PipeDocGen`` cannot be built from its blueprint.

    The output concept is not a Document, a template does not parse or reads a field its input does not have,
    or the template file is missing or cannot be resolved. It is raised only while the pipe is built, about the
    author's own blueprint, so it is the author's to fix and its messages name only the author's pipe, concepts,
    fields, template and file path.
    """

    error_domain = ErrorDomain.INPUT
    _authors_caller_facing_message = True


class PipeDocGenRunError(PipelexError):
    """Raised when a ``PipeDocGen`` step fails while it composes its document: a template or the filename does not render."""


class PipeDocGenUndefinedValueError(PipelexError):
    """Raised when a ``PipeDocGen`` template or filename reads a value its inputs do not have.

    Its templates render with a strict undefined, so a field the load-time check could not follow, such as one
    read through a ``{% set %}`` alias, fails here rather than printing as empty text, at the dry run when the
    template names a field its concept lacks. The template is always the method author's own, unlike the
    renders ``Jinja2TemplateRenderError`` also serves, so the message is the author's to read: it names the pipe,
    the template or the filename, and the missing name, and it never quotes the template's source.
    """

    error_domain = ErrorDomain.INPUT
    _authors_caller_facing_message = True


class PipeDocGenTemplateCheckError(PipelexError):
    """Raised by a ``PipeDocGen`` dry run when the engine's template checker reports errors in the step's template file.

    The dry run is what ``pipelex validate`` runs, so a template naming a field the inputs do not have fails there,
    before anything is spent. Its message lists the checker's findings, which name only the author's template,
    names and fields.
    """

    error_domain = ErrorDomain.INPUT
    _authors_caller_facing_message = True


class PipeDocGenTemplateFileUncheckedError(PipelexError):
    """Raised when a ``PipeDocGen`` step built from a library crate is validated where its HTML template file is not at hand.

    An HTML template file's checks read the file: the variables it reads are inputs of the step, the fields it reads are
    fields of their concepts, and every reference to an optional input is guarded. A crate names the step's method tree
    by digest and carries none of its files, so a validation of the crate reads the file from a tree a library of this
    process holds, and reaches the verdict the load where the crate was assembled reached. Where no library holds the
    tree, the validation cannot reach it, and refuses rather than pass the step unchecked. The fault is where the crate
    was validated, not in the method, and the message names only the step and the template file's tree path.
    """

    error_domain = ErrorDomain.RUNTIME
    retryable = False
