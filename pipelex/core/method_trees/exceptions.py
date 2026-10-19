from typing import ClassVar

from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError
from pipelex.errors.error_code_declaration import ErrorCodeDeclaration, ErrorCodeSet


class TreePythonError(PipelexError):
    """A method tree's Python cannot be imported in this process.

    The default ``runtime.unexpected`` is an invariant of the import hold; a raise site chooses ``request.unsupported``
    for a tree handed over in a form that holds no directory of Python, and ``method.name_conflict`` for a module of the
    tree that a module of the same name imported earlier hides.
    """

    error_code: ClassVar[ErrorCodeDeclaration] = ErrorCodeSet(
        default=CoreCode.RUNTIME_UNEXPECTED,
        others=(CoreCode.REQUEST_UNSUPPORTED, CoreCode.METHOD_NAME_CONFLICT),
    )


class TreePythonHeldError(TreePythonError):
    """Another method tree's Python is held by a run in flight, so this tree's Python cannot load in this process.

    A process imports one tree's Python at a time: the tree root goes first on `sys.path` and its modules keep their
    real names, so two trees defining the same module could not share the process, and evicting the earlier tree's
    modules would pull them from under its run. The message names both trees, and the same run succeeds once the run
    in flight ends.
    """

    error_code = CoreCode.RUNTIME_UNAVAILABLE


class TreeModuleShadowingError(TreePythonError):
    """A top-level module of a method tree shares its name with a standard-library module or a module importable outside the tree.

    With the tree's root first on `sys.path`, the tree's module would replace the other one for the whole process,
    and the failure would show up far from its cause. The message names the module, the tree file and what it
    would shadow; it describes the caller's own method, so it is kept under STRICT disclosure.
    """

    error_code = CoreCode.METHOD_NAME_CONFLICT
    _authors_caller_facing_message = True


class TreeModuleExcludedError(ImportError):
    """An import reached a file under a held method tree's root that the tree's membership rule keeps out of the tree.

    Raised by the import guard from inside Python's import machinery, which expects an `ImportError`. The message
    names the file by its tree path and the rule that excluded it, never the tree's root, which is a path on this host.
    """

    def __init__(self, message: str, *, module_name: str, tree_path: str):
        super().__init__(message, name=module_name)
        self.message = message
        self.tree_path = tree_path


class MethodFileUnavailableError(PipelexError):
    """A method file, or the listing of the tree that holds it, cannot be read through the method file store.

    The store does not hold it, such as a tree the process that assembled the run never handed over, or the bytes it
    holds no longer match the hash the tree's listing names, such as a file edited on disk after its tree was listed. The
    message names the tree by its digest and the file by its tree path, never by a path of this host. A tree that names
    no file at the path a method refers to chooses ``method.resource_missing``; the rest is the store failing this run.
    """

    error_code = ErrorCodeSet(default=CoreCode.RUNTIME_UNEXPECTED, others=(CoreCode.METHOD_RESOURCE_MISSING,))
