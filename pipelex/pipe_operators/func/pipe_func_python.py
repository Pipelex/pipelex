"""Where a `PipeFunc`'s function lives, how its form is proven without running Python, and how it is imported to be called.

A `function_name` is an import path from an import root, which is one of three places:

- **The method tree** the step's bundle was read as a member of, on this host's disk (`mthds/docs/spec/method-tree.md`,
  "Python Modules"). The module is located among the tree's files with `mthds`' `locate_function`, and imported under
  the process's hold on the tree's Python (`pipelex.core.method_trees.tree_python`).
- **The Python submitted with a bundle parsed from a content string**, which a sandbox-hosted deployment captures from
  its library directories and sends to the sandbox with the call. Nothing imports it in this process: the step is
  validated from the captured text.
- **This process's own import path**, for a bundle parsed from a content string in `direct` mode, such as a bundle a
  program builds in memory beside its own modules. The module is located through the import system's finders without
  importing it, then imported as any module of the program is.

Validation never runs Python: it locates the module, reads its source, and proves from the syntax tree that the
function is a top-level `def` or `async def` carrying the `@pipe_func()` marker (`pipe_func_definition_check`). The
function's calling convention is checked once it is imported, when its step first runs.
"""

import importlib
import importlib.machinery
import importlib.util
import inspect
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from types import ModuleType
from typing import Any, NamedTuple

from mthds.method_tree.digest import digest_of_contents, tree_files_from_contents
from mthds.method_tree.exceptions import MethodTreeRefusedError
from mthds.method_tree.models import MethodTree
from mthds.method_tree.python_modules import locate_function

from pipelex.core.method_trees.tree_files import TreeFileEntry, tree_file_bytes
from pipelex.core.method_trees.tree_python import TREE_PYTHON_HOLD, import_held_tree_module
from pipelex.pipe_operators.func.exceptions import PipeFuncFunctionError
from pipelex.pipe_operators.func.function_name import split_function_name
from pipelex.pipe_operators.func.pipe_func_definition_check import pipe_func_definition_violation
from pipelex.pipe_operators.func.pipe_func_signature import pipe_func_signature_violation
from pipelex.system.registries.func_registry import is_marked_pipe_func


class PipeFuncModuleSource(NamedTuple):
    """The module a `function_name` names, located and read: its import name, the function's name, how messages name it, its text."""

    module_name: str
    function: str
    module_label: str
    source: str


def locate_in_tree(*, function_name: str, tree: MethodTree, files: Mapping[str, TreeFileEntry] | None = None) -> PipeFuncModuleSource:
    """Locate the module of a `function_name` among a method tree's files, and read it.

    Args:
        function_name: The step's `function_name`.
        tree: The method tree the step's bundle is a member of.
        files: The tree's files as captured for a call, read in place of the disk when given.

    Raises:
        PipeFuncFunctionError: The tree holds no such module, or holds it twice.
    """
    import_path = split_function_name(function_name=function_name)
    try:
        location = locate_function(function_name, tree=tree)
    except MethodTreeRefusedError as exc:
        raise PipeFuncFunctionError(str(exc)) from exc
    source_bytes: bytes
    if files is not None and location.module in files:
        source_bytes = tree_file_bytes(entry=files[location.module])
    else:
        source_bytes = tree.file_location(location.module).read_bytes()
    return PipeFuncModuleSource(
        module_name=import_path.module_name,
        function=import_path.function,
        module_label=location.module,
        source=_decoded_source(source_bytes=source_bytes, module_label=location.module),
    )


def locate_in_files(*, function_name: str, files: Mapping[str, TreeFileEntry]) -> PipeFuncModuleSource:
    """Locate the module of a `function_name` among submitted files keyed by their path from the import root, and read it.

    Raises:
        PipeFuncFunctionError: The files hold no such module, or hold it twice.
    """
    contents = {tree_path: tree_file_bytes(entry=entry) for tree_path, entry in files.items()}
    tree = MethodTree(files=tree_files_from_contents(contents), digest=digest_of_contents(contents))
    return locate_in_tree(function_name=function_name, tree=tree, files=files)


def locate_on_import_path(*, function_name: str) -> PipeFuncModuleSource:
    """Locate the module of a `function_name` on this process's import path without importing it, and read it.

    Each package of the path is found through the finders, not imported, so no package's code runs before the
    function's form is proven; a package already imported is read from `sys.modules`.

    Raises:
        PipeFuncFunctionError: No such module is found, or it is not a Python source file.
    """
    import_path = split_function_name(function_name=function_name)
    module_file = _find_source_file(module_name=import_path.module_name, function_name=function_name)
    # Named by its import name, never by its file, which is a path on this host.
    module_label = f"'{import_path.module_name}'"
    return PipeFuncModuleSource(
        module_name=import_path.module_name,
        function=import_path.function,
        module_label=module_label,
        source=_decoded_source(source_bytes=module_file.read_bytes(), module_label=module_label),
    )


def check_pipe_func_definition(*, module_source: PipeFuncModuleSource) -> None:
    """Prove from the module's syntax tree that the function is a top-level `def` or `async def` carrying the marker.

    Raises:
        PipeFuncFunctionError: The form is not proven.
    """
    violation = pipe_func_definition_violation(
        source=module_source.source,
        function=module_source.function,
        module_label=module_source.module_label,
    )
    if violation is not None:
        raise PipeFuncFunctionError(violation)


def bind_tree_function(*, function_name: str, tree: MethodTree, holder: str) -> Callable[..., Any]:
    """Import a method tree's function under the process's hold on the tree's Python, and check it.

    The hold is taken for `holder`, the library of the run, and released when that library is torn down.

    Raises:
        PipeFuncFunctionError: The static form is not proven, or the imported function does not follow the
            calling convention.
        TreePythonHeldError: Another tree's Python is held by a run in flight.
        TreeModuleShadowingError: A top-level module of the tree would shadow another module.
    """
    module_source = locate_in_tree(function_name=function_name, tree=tree)
    check_pipe_func_definition(module_source=module_source)
    identity = TREE_PYTHON_HOLD.acquire(tree=tree, holder=holder)
    module = import_held_tree_module(identity=identity, module_name=module_source.module_name)
    return checked_pipe_func(module=module, module_source=module_source)


def bind_import_path_function(*, function_name: str) -> Callable[..., Any]:
    """Import a function from this process's import path, and check it.

    Raises:
        PipeFuncFunctionError: The static form is not proven, or the imported function does not follow the
            calling convention.
    """
    module_source = locate_on_import_path(function_name=function_name)
    check_pipe_func_definition(module_source=module_source)
    module = importlib.import_module(module_source.module_name)
    return checked_pipe_func(module=module, module_source=module_source)


def checked_pipe_func(*, module: ModuleType, module_source: PipeFuncModuleSource) -> Callable[..., Any]:
    """The function of an imported module, once it is proven to be the module's own function, marked, and conventional.

    Raises:
        PipeFuncFunctionError: It is missing, not a function defined in the module, unmarked, or does not follow the
            calling convention.
    """
    function_label = f"'{module_source.function}' of {module_source.module_label}"
    func = getattr(module, module_source.function, None)
    if func is None:
        msg = f"The function {function_label} is missing once the module is imported."
        raise PipeFuncFunctionError(msg)
    if not inspect.isroutine(func) or getattr(func, "__module__", None) != module.__name__:
        msg = f"The attribute {function_label} is not a function the module defines itself once it is imported."
        raise PipeFuncFunctionError(msg)
    if not is_marked_pipe_func(func=func):
        msg = f"The function {function_label} does not carry the @pipe_func() marker once the module is imported."
        raise PipeFuncFunctionError(msg)
    signature_violation = pipe_func_signature_violation(func=func)
    if signature_violation is not None:
        msg = f"The function {function_label} {signature_violation}."
        raise PipeFuncFunctionError(msg)
    return func


def _decoded_source(*, source_bytes: bytes, module_label: str) -> str:
    try:
        return source_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        msg = f"The module {module_label} is not UTF-8 text, so its source cannot be read."
        raise PipeFuncFunctionError(msg) from exc


def _find_source_file(*, module_name: str, function_name: str) -> Path:
    """The source file of a module on the import path, found without importing it or any package above it."""
    segments = module_name.split(".")
    spec: importlib.machinery.ModuleSpec | None = None
    for index in range(len(segments)):
        dotted = ".".join(segments[: index + 1])
        loaded = sys.modules.get(dotted)
        if loaded is not None and getattr(loaded, "__spec__", None) is not None:
            spec = loaded.__spec__
        elif index == 0:
            try:
                spec = importlib.util.find_spec(dotted)
            except (ImportError, ValueError):
                spec = None
        else:
            parent_locations = spec.submodule_search_locations if spec is not None else None
            if parent_locations is None:
                msg = f"The function_name '{function_name}' names the module '{module_name}', but '{'.'.join(segments[:index])}' is not a package."
                raise PipeFuncFunctionError(msg)
            spec = importlib.machinery.PathFinder.find_spec(dotted, list(parent_locations))
        if spec is None:
            msg = f"The function_name '{function_name}' names the module '{module_name}', which is not found on this process's import path."
            raise PipeFuncFunctionError(msg)
    if spec is None or spec.origin is None or not spec.has_location or not spec.origin.endswith(".py"):
        msg = f"The function_name '{function_name}' names the module '{module_name}', which is not a Python source file."
        raise PipeFuncFunctionError(msg)
    return Path(spec.origin)
