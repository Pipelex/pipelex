from typing import ClassVar

from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError
from pipelex.core.exceptions import PipelexBundleBlueprintValidationErrorData, PipesAndConceptValidationErrorData
from pipelex.errors.error_code_declaration import ABSTRACT_ERROR, ErrorCodeDeclaration, ErrorCodeSet
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode


class LibraryError(PipelexError):
    """A library that cannot hold what it is asked to hold.

    The default ``runtime.unexpected`` is an invariant of the library manager, such as a library id that does not
    exist; a raise site that finds a fault of the request, of the method or of the library directories chooses
    ``request.invalid``, ``method.concept_unresolved`` or ``pipelex.config.invalid``.
    """

    error_code: ClassVar[ErrorCodeDeclaration] = ErrorCodeSet(
        default=CoreCode.RUNTIME_UNEXPECTED,
        others=(CoreCode.REQUEST_INVALID, CoreCode.METHOD_CONCEPT_UNRESOLVED, PipelexErrorCode.CONFIG_INVALID),
    )


class CrateNormalizationError(LibraryError):
    """Raised when a library crate cannot be normalized (e.g. a non-domain-qualified key, or a pipe ref matching no crate pipe, or several).

    A key the crate builder failed to qualify is an invariant; a refinement cycle chooses ``method.cycle``.
    """

    error_code = ErrorCodeSet(default=CoreCode.RUNTIME_UNEXPECTED, others=(CoreCode.METHOD_CYCLE,))


class LibraryLoadingError(LibraryError):
    """Error raised when loading library components fails.

    This error aggregates TWO types of validation errors:
    1. Blueprint validation errors (from PipelexBundleBlueprint.model_validate())
       - Stored in: blueprint_validation_errors
       - Example: PIPE_SEQUENCE_OUTPUT_MISMATCH

    2. Pipe/Concept validation errors (from Pipe or Concept class validation)
       - Stored in: pipe_concept_validation_errors
       - Example: MISSING_INPUT_VARIABLE, INPUT_STUFF_SPEC_MISMATCH

    Also handles:
    - Factory errors (Domain, Concept, Pipe)
    - Interpreter errors (blueprint parsing)

    The default ``method.invalid`` is the umbrella whose items carry their own codes; a raise site that finds one
    fault chooses its code.
    """

    error_code: ClassVar[ErrorCodeDeclaration] = ErrorCodeSet(
        default=CoreCode.METHOD_INVALID,
        others=(
            CoreCode.METHOD_CYCLE,
            CoreCode.METHOD_NAME_CONFLICT,
            CoreCode.METHOD_PIPE_NOT_EXPORTED,
            CoreCode.METHOD_DEPENDENCY_MISSING,
            CoreCode.METHOD_CONCEPT_INVALID,
            CoreCode.METHOD_NOT_FOUND,
        ),
    )

    def __init__(
        self,
        message: str,
        blueprint_validation_errors: list[PipelexBundleBlueprintValidationErrorData] | None = None,
        pipe_concept_validation_errors: list[PipesAndConceptValidationErrorData] | None = None,
    ):
        """Initialize LibraryLoadingError.

        Args:
            message: Error message
            blueprint_validation_errors: Blueprint validation errors (from PipelexBundleBlueprint validation)
            pipe_concept_validation_errors: Pipe/Concept validation errors (from Pipe/Concept validation)
        """
        self.blueprint_validation_errors = blueprint_validation_errors or []
        self.pipe_concept_validation_errors = pipe_concept_validation_errors or []
        super().__init__(message)


class MethodTreeLoadError(LibraryLoadingError):
    """Raised when a method tree a load reads from this host's disk cannot be listed.

    The tree of a method's folder, of a library directory, of a `.mthds` file named alone or of a dependency package:
    the standard refused it (a symbolic link, a name that is not a tree path, a lone file the membership rule keeps
    out), it passed a limit this machine lists trees under, or a directory or a file of it could not be read. The
    tree is the caller's own method, so the message, which names the tree's root and the files by their tree paths,
    is theirs to read, and the same load is refused again until the tree changes.
    """

    error_code = CoreCode.METHOD_PACKAGE_INVALID
    _authors_caller_facing_message = True


class HostLibraryTreeError(PipelexError):
    """Raised when a library directory of this host, one a load reads beside a caller's bundles, cannot be read as a method tree.

    Such a directory is the host's own (installed libraries, the defaults, `PIPELEXPATH` on a server), so a tree of it
    that the standard refuses, that passes a limit or that cannot be read is a fault of the host's configuration, not
    of the caller's method: it is not an `INPUT` error, and its message, which names paths on the host, is not
    caller-facing. It is deliberately no `LibraryError`, which a validation would report as the caller's invalid bundle.
    """

    error_code = PipelexErrorCode.CONFIG_INVALID


class MethodRequirementsError(LibraryLoadingError):
    """Raised when a method's `requirements.txt` refuses the method as it loads.

    The method's own declaration, so the caller can fix it: the message names the file's lines and the packages, and
    one structured item per line rides the validation verdict, its `source` the file's path in the method's tree. Around
    a load of a host's own library directories it leaves as a `HostLibraryRequirementsError` instead, the host's fault
    (`reporting_host_library_tree_faults`).
    """

    error_code: ClassVar[ErrorCodeDeclaration] = ABSTRACT_ERROR
    _authors_caller_facing_message = True

    def __init__(self, message: str, *, items: list[PipelexBundleBlueprintValidationErrorData]):
        super().__init__(message, blueprint_validation_errors=items)


class MethodRequirementsFileError(MethodRequirementsError):
    """Raised when a method's `requirements.txt` holds a line the MTHDS standard refuses, or cannot be read as UTF-8 text.

    Each line is blank, a comment, or exactly one PEP 508 requirement; a requirement naming a URL, an option such as
    `-r`, `-e` or `--index-url`, a comment after a requirement and a line continued with a backslash are refused.
    """

    error_code = CoreCode.METHOD_PACKAGE_INVALID


class MethodRequirementsNotMetError(MethodRequirementsError):
    """Raised when the Python environment a method's PipeFunc steps run in does not satisfy its `requirements.txt`.

    Locally that environment is the interpreter Pipelex runs in, which Pipelex never installs anything into; on a
    sandbox-hosted deployment it is the package set the deployment states for its PipeFunc sandbox, which is the whole
    offer. The message names each requirement not met and why.
    """

    error_code = CoreCode.METHOD_DEPENDENCY_MISSING


class HostLibraryRequirementsError(PipelexError):
    """Raised when a method of this host's own library directories, loaded beside a caller's bundles, is refused for its requirements.

    Such a directory is the host's own (installed libraries, the defaults, `PIPELEXPATH` on a server), so its
    `requirements.txt` holding a refused line, or naming packages the environment does not hold, is a fault of the
    host's configuration, not of the caller's method: it is not an `INPUT` error, and its message, which names paths on
    the host, is not caller-facing. Like `HostLibraryTreeError`, it is deliberately no `LibraryError`.
    """

    error_code = PipelexErrorCode.CONFIG_INVALID


class PipeFuncPackageSetUnstatedError(PipelexError):
    """Raised when a method declaring requirements loads on a deployment that states no package set for its PipeFunc sandbox.

    PipeFunc steps run out of this process, in the configured execution mode's sandbox, and either no plugin registers
    a statement of the packages found there (`PluginRegistrar.add_pipe_func_package_offer`), or the one registered could
    not state them, so no requirement can be judged and the method is refused rather than left to fail inside the
    sandbox. A fault of the deployment, not of the method: it is no `LibraryError`, which a validation would report as
    the caller's invalid bundle, and its message is not caller-facing.
    """

    error_code = CoreCode.RUNTIME_MISCONFIGURED

    def __init__(self, *, execution_mode: str, offer_registered: bool):
        self.execution_mode = execution_mode
        self.offer_registered = offer_registered
        if offer_registered:
            message = (
                f"PipeFunc steps run in the '{execution_mode}' execution mode, whose plugin registers a package offer that "
                "could not state the Python packages they run with on this deployment, so a method declaring requirements "
                "in its requirements.txt cannot load. Check the plugin's configuration, such as the sandbox image or "
                "snapshot it reads its package set from."
            )
        else:
            message = (
                f"PipeFunc steps run in the '{execution_mode}' execution mode, for which no plugin registers the Python "
                "packages they run with, so a method declaring requirements in its requirements.txt cannot load. The plugin "
                "providing the mode must register its package offer with PluginRegistrar.add_pipe_func_package_offer."
            )
        super().__init__(message)
