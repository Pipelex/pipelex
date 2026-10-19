from typing import ClassVar

from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError
from pipelex.errors.error_code_declaration import ErrorCodeDeclaration, ErrorCodeSet, InheritsCause


class PipeComposeError(PipelexError):
    """A ``PipeCompose`` failed to compose its output; raised directly, it takes its cause's code."""

    error_code: ClassVar[ErrorCodeDeclaration] = InheritsCause(fallback=CoreCode.PIPE_OUTPUT_INVALID)


class PipeComposeFactoryError(PipeComposeError):
    """Raised when a ``PipeCompose`` has no template in template mode, or its template does not parse.

    Raised only while the pipe is built from its blueprint, about that blueprint, so it is the method's to fix and
    bundle validation reports it as an item located on the pipe: a template that does not parse is
    ``method.template_invalid``, its code over the parser's own, and a template mode with no template
    ``method.schema_violation``. Its messages name only the author's own pipe, concepts and template text, so they
    are caller-facing copy kept under STRICT disclosure.
    """

    error_code = ErrorCodeSet(default=CoreCode.METHOD_TEMPLATE_INVALID, others=(CoreCode.METHOD_SCHEMA_VIOLATION,))
    _authors_caller_facing_message = True


class ConstructFieldBlueprintTypeError(PipeComposeError, TypeError):
    """A ``construct`` field of the method has a shape the blueprint does not accept."""

    error_code = CoreCode.METHOD_SCHEMA_VIOLATION


class ConstructFieldBlueprintValueError(PipeComposeError, ValueError):
    """A ``construct`` field of the method breaks a rule of the blueprint."""

    error_code = CoreCode.METHOD_SCHEMA_VIOLATION


class PipeComposeTemplateError(PipeComposeError, ValueError):
    """A template of a ``PipeCompose``, its own or a ``construct`` field's, does not parse when its variables are read.

    Its message carries the parser's diagnosis, which can quote the template, so it is not caller-facing: the
    template may be a host library's. It stays a ``ValueError`` for the pydantic validators that read a pipe's
    required variables.
    """

    error_code = CoreCode.METHOD_TEMPLATE_INVALID


class StructuredContentComposerTypeError(PipeComposeError, TypeError):
    """The value a ``construct`` composed does not fit the output concept."""

    error_code = CoreCode.PIPE_OUTPUT_INVALID


class StructuredContentComposerValueError(PipeComposeError, ValueError):
    """A ``construct`` cannot compose a field: a blueprint invariant the load guarantees broke (``runtime.unexpected``),
    or a ``from`` path or key attribute names a field the value lacks (``method.field_path_unresolved``).
    """

    error_code = ErrorCodeSet(default=CoreCode.RUNTIME_UNEXPECTED, others=(CoreCode.METHOD_FIELD_PATH_UNRESOLVED,))


class StructuredContentComposerValidationError(PipeComposeError):
    """The composed value does not validate against the output concept's structure."""

    error_code = CoreCode.PIPE_OUTPUT_INVALID
