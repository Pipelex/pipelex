from pathlib import Path

from pipelex.base_exceptions import ErrorDomain, PipelexError


class TreePythonError(PipelexError):
    """A method tree's Python cannot be imported in this process."""


class TreePythonHeldError(TreePythonError):
    """Another method tree's Python is held by a run in flight, so this tree's Python cannot load in this process.

    A process imports one tree's Python at a time: the tree root goes first on `sys.path` and its modules keep their
    real names, so two trees defining the same module could not share the process, and evicting the earlier tree's
    modules would pull them from under its run. The message names both trees.
    """


class TreeModuleShadowingError(TreePythonError):
    """A top-level module of a method tree shares its name with a standard-library module or a module importable outside the tree.

    With the tree's root first on `sys.path`, the tree's module would replace the other one for the whole process,
    and the failure would show up far from its cause. The message names the module, the tree file and what it
    would shadow; it describes the caller's own method, so it is kept under STRICT disclosure.
    """

    error_domain = ErrorDomain.INPUT
    retryable = False
    _authors_caller_facing_message = True


class TreeModuleExcludedError(ImportError):
    """An import reached a file under a held method tree's root that the tree's membership rule keeps out of the tree.

    Raised by the import guard from inside Python's import machinery, which expects an `ImportError`. The message
    names the file and the rule that excluded it.
    """

    def __init__(self, message: str, *, module_name: str, file_path: Path):
        super().__init__(message, name=module_name, path=str(file_path))
        self.message = message
