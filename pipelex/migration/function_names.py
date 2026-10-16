"""The migration of a method's `PipeFunc` steps from flat function names to import paths.

Until the function registry retired, a `PipeFunc` step named its function by a flat name, `function_name =
"compute_totals"`, which the registry resolved among every `@pipe_func` function of every scanned directory: the
function's own name, or the name its marker gave it, `@pipe_func(name="...")`. A step now names its function by its
import path from the root of the method tree, `function_name = "funcs.totals.compute_totals"`, and a flat name is
refused (`wip/extra-files/design.md`, D3).

The migration is mechanical: for each `PipeFunc` step whose `function_name` holds no dot, find the module of the tree
that defines the marked function the flat name registered, and write its import path; then drop the argument of every
`@pipe_func(name=...)` marker, since the marker takes none. Nothing is imported: the modules are read as syntax trees,
so a method whose Python cannot run here still migrates. A flat name no module of the tree registers, or that two
register, is left as it is and reported, for the author to decide, and so is the name of each marker registering it,
which is then the only record of which function the step meant; a marker whose name is not a string literal is left and
reported too, since its name cannot be read without running the module.

The engine is pure, over a map of tree paths to texts, so it serves a method folder on disk (`pipelex fix
function-names`) and a method held anywhere else, such as a stored method rewritten in place, alike. Only the `.mthds`
and `.py` files are read; the others are ignored.
"""

import ast
import re
from collections.abc import Mapping, MutableMapping
from pathlib import Path
from typing import Any, cast

import tomlkit
from mthds.method_tree.exceptions import MethodTreeRefusedError, TreeLimitError, TreeSourceError
from mthds.method_tree.lister import list_method_tree
from mthds.method_tree.python_modules import is_valid_function_segment
from pydantic import BaseModel, ConfigDict, Field
from tomlkit.exceptions import TOMLKitError
from tomlkit.items import String

from pipelex.migration.exceptions import FunctionNamesMigrationError
from pipelex.pipe_operators.func.pipe_func_definition_check import marker_call, marker_references
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of

_BUNDLE_SUFFIX = ".mthds"
_PYTHON_SUFFIX = ".py"
_PACKAGE_INIT = "__init__"
_PIPE_FUNC_TYPE = "PipeFunc"
_MARKER_NAME_ARGUMENT = "name"
# A line of a module as the syntax tree counts lines, with its ending: Python ends a line only at `\r\n`, `\r` or `\n`,
# where `str.splitlines` also breaks at a form feed, a vertical tab, the separators of the C1 and Unicode ranges.
_SOURCE_LINE = re.compile(r".*?(?:\r\n|\r|\n)|.+\Z", flags=re.DOTALL)


class FunctionNameRewrite(BaseModel):
    """One `function_name` the migration rewrote: the step, the flat name it held and the import path it holds now."""

    model_config = ConfigDict(frozen=True)

    bundle: str = Field(description="The tree path of the .mthds file that defines the step")
    pipe_code: str = Field(description="The step's pipe code")
    flat_name: str = Field(description="The flat function name the step held")
    import_path: str = Field(description="The import path it holds now, from the root of the method tree")


class MarkerArgumentRemoval(BaseModel):
    """One `@pipe_func(...)` marker whose registration name the migration dropped."""

    model_config = ConfigDict(frozen=True)

    module: str = Field(description="The tree path of the Python module that defines the function")
    function: str = Field(description="The function's own name, which its import path ends with")
    registered_name: str = Field(description="The name the marker registered the function under")


class UnresolvedMarker(BaseModel):
    """A `@pipe_func(...)` marker whose argument the migration left in place, and why."""

    model_config = ConfigDict(frozen=True)

    module: str = Field(description="The tree path of the Python module that defines the function")
    function: str = Field(description="The function's own name")
    registered_name: str | None = Field(default=None, description="The name the marker registered the function under, when it is a string literal")
    reason: str = Field(description="Why the argument was left, and what to do")


class UnresolvedFunctionName(BaseModel):
    """A flat `function_name` the migration left as it is, and why."""

    model_config = ConfigDict(frozen=True)

    bundle: str = Field(description="The tree path of the .mthds file that defines the step")
    pipe_code: str | None = Field(default=None, description="The step's pipe code, when the bundle could be read")
    flat_name: str | None = Field(default=None, description="The flat function name the step holds, when the bundle could be read")
    reason: str = Field(description="Why the name was not rewritten, and what to do")
    candidates: list[str] = Field(default_factory=list, description="The import paths that register the name, when more than one does")


class FunctionNamesMigration(BaseModel):
    """What migrating one method's function names changed, and what it left for the author."""

    model_config = ConfigDict(frozen=True)

    rewrites: list[FunctionNameRewrite] = Field(default_factory=empty_list_factory_of(FunctionNameRewrite))
    marker_removals: list[MarkerArgumentRemoval] = Field(default_factory=empty_list_factory_of(MarkerArgumentRemoval))
    unresolved: list[UnresolvedFunctionName] = Field(default_factory=empty_list_factory_of(UnresolvedFunctionName))
    unresolved_markers: list[UnresolvedMarker] = Field(default_factory=empty_list_factory_of(UnresolvedMarker))
    changed_files: dict[str, str] = Field(default_factory=dict, description="Each file the migration changed, by tree path, with its new text")

    @property
    def is_complete(self) -> bool:
        """Whether every `PipeFunc` step names its function by import path, and every marker takes no argument, once the changes are written."""
        return not self.unresolved and not self.unresolved_markers

    @property
    def has_changes(self) -> bool:
        return bool(self.changed_files)


class _MarkedFunction(BaseModel):
    """A top-level function of the tree carrying the marker, with the name it was registered under."""

    model_config = ConfigDict(frozen=True)

    module_path: str
    module_name: str | None
    function: str
    registered_name: str | None
    name_argument_span: tuple[int, int, int, int] | None

    @property
    def import_path(self) -> str | None:
        return f"{self.module_name}.{self.function}" if self.module_name is not None else None


def migrate_function_names(*, files: Mapping[str, str]) -> FunctionNamesMigration:
    """Rewrite every flat `function_name` of a method's bundles into its import path, and drop the markers' names.

    Args:
        files: The method tree's files by tree path, each as its text; only the `.mthds` and `.py` files are read.

    Returns:
        The rewrites, the marker names dropped, the names left unresolved, and the new text of each changed file.
    """
    marked_functions = _marked_functions(files=files)
    registrations: dict[str, list[_MarkedFunction]] = {}
    for marked_function in marked_functions:
        if marked_function.registered_name is not None:
            registrations.setdefault(marked_function.registered_name, []).append(marked_function)

    changed_files: dict[str, str] = {}
    rewrites: list[FunctionNameRewrite] = []
    unresolved: list[UnresolvedFunctionName] = []
    for tree_path in sorted(files):
        if not tree_path.endswith(_BUNDLE_SUFFIX):
            continue
        new_text = _migrate_bundle(
            bundle=tree_path,
            text=files[tree_path],
            registrations=registrations,
            rewrites=rewrites,
            unresolved=unresolved,
        )
        if new_text is not None:
            changed_files[tree_path] = new_text

    # A marker's name is the only record of which function a step left unresolved meant, so it stays until every step
    # naming it is rewritten.
    unresolved_names = {name.flat_name: name for name in unresolved if name.flat_name is not None}
    marker_removals: list[MarkerArgumentRemoval] = []
    unresolved_markers: list[UnresolvedMarker] = []
    spans_by_module: dict[str, list[tuple[int, int, int, int]]] = {}
    for marked_function in marked_functions:
        if marked_function.name_argument_span is None:
            continue
        if marked_function.registered_name is None:
            unresolved_markers.append(
                UnresolvedMarker(
                    module=marked_function.module_path,
                    function=marked_function.function,
                    reason=(
                        "The marker's name is not a string literal, so the name the retired registry gave the function cannot be read "
                        "without running the module: write the function's import path in each step that names it, then drop the "
                        "marker's argument."
                    ),
                )
            )
            continue
        unresolved_step = unresolved_names.get(marked_function.registered_name)
        if unresolved_step is not None:
            unresolved_markers.append(
                UnresolvedMarker(
                    module=marked_function.module_path,
                    function=marked_function.function,
                    registered_name=marked_function.registered_name,
                    reason=(
                        f"The step '{unresolved_step.pipe_code}' of {unresolved_step.bundle} still names '{marked_function.registered_name}', "
                        "which the migration left unresolved: the marker keeps its name until that step names its function by import "
                        "path, then the migration drops it."
                    ),
                )
            )
            continue
        spans_by_module.setdefault(marked_function.module_path, []).append(marked_function.name_argument_span)
        marker_removals.append(
            MarkerArgumentRemoval(
                module=marked_function.module_path,
                function=marked_function.function,
                registered_name=marked_function.registered_name,
            )
        )
    for module_path, spans in sorted(spans_by_module.items()):
        changed_files[module_path] = _without_spans(text=files[module_path], spans=spans)

    return FunctionNamesMigration(
        rewrites=rewrites,
        marker_removals=marker_removals,
        unresolved=unresolved,
        unresolved_markers=unresolved_markers,
        changed_files=dict(sorted(changed_files.items())),
    )


def migrate_function_names_in_directory(*, directory: Path, is_dry_run: bool) -> FunctionNamesMigration:
    """Migrate the function names of the method tree rooted at a directory, writing the changed files unless it is a dry run.

    The tree is listed by the standard's membership rule, so a `.gitignore`d file or a virtual environment is never
    read nor written. A file that is not UTF-8 text is left out of the migration.

    Raises:
        FunctionNamesMigrationError: The path is not a directory, or its tree cannot be listed or a file written.
    """
    if not directory.is_dir():
        msg = f"'{directory}' is not a directory: hand over the folder of the method, whose tree holds its bundles and its Python."
        raise FunctionNamesMigrationError(msg)
    try:
        tree = list_method_tree(directory)
    except (MethodTreeRefusedError, TreeLimitError, TreeSourceError) as exc:
        msg = f"The method tree at '{directory}' cannot be listed: {exc}"
        raise FunctionNamesMigrationError(msg) from exc

    files: dict[str, str] = {}
    for tree_path in tree.tree_paths:
        if not tree_path.endswith((_BUNDLE_SUFFIX, _PYTHON_SUFFIX)):
            continue
        try:
            files[tree_path] = tree.file_location(tree_path).read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            continue
        except OSError as exc:
            msg = f"The file '{tree_path}' of the method tree at '{directory}' cannot be read: {exc}"
            raise FunctionNamesMigrationError(msg) from exc

    migration = migrate_function_names(files=files)
    if is_dry_run:
        return migration
    for tree_path, new_text in migration.changed_files.items():
        try:
            tree.file_location(tree_path).write_bytes(new_text.encode("utf-8"))
        except OSError as exc:
            msg = f"The file '{tree_path}' of the method tree at '{directory}' cannot be written: {exc}"
            raise FunctionNamesMigrationError(msg) from exc
    return migration


def _module_name_of(*, tree_path: str) -> str | None:
    """The import name of a Python file of the tree, from its root, or None when it cannot be imported by name."""
    segments = tree_path.removesuffix(_PYTHON_SUFFIX).split("/")
    if segments[-1] == _PACKAGE_INIT:
        segments = segments[:-1]
    if not segments or not all(is_valid_function_segment(segment) for segment in segments):
        return None
    return ".".join(segments)


def _marked_functions(*, files: Mapping[str, str]) -> list[_MarkedFunction]:
    """Every top-level function of the tree's Python decorated with the marker, with the name the registry gave it."""
    marked_functions: list[_MarkedFunction] = []
    for tree_path in sorted(files):
        if not tree_path.endswith(_PYTHON_SUFFIX):
            continue
        try:
            module = ast.parse(files[tree_path], filename=tree_path)
        except SyntaxError:
            continue
        marker_refs = marker_references(module=module)
        if not marker_refs:
            continue
        for statement in module.body:
            if not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            decorator = marker_call(definition=statement, marker_refs=marker_refs)
            if decorator is None:
                continue
            registered_name, has_name_argument = _registered_name(decorator=decorator, function=statement.name)
            marked_functions.append(
                _MarkedFunction(
                    module_path=tree_path,
                    module_name=_module_name_of(tree_path=tree_path),
                    function=statement.name,
                    registered_name=registered_name,
                    name_argument_span=_arguments_span(decorator=decorator) if has_name_argument else None,
                )
            )
    return marked_functions


def _registered_name(*, decorator: ast.Call, function: str) -> tuple[str | None, bool]:
    """The name the retired registry registered a marked function under, and whether the marker passed one.

    The name is the marker's `name` argument, positional or by keyword, when it is a string literal, and the function's
    own name when the marker passes none. A name the syntax tree cannot read, such as a variable, is None.
    """
    has_arguments = bool(decorator.args or decorator.keywords)
    name_node: ast.expr | None = None
    if decorator.args:
        name_node = decorator.args[0]
    for keyword in decorator.keywords:
        if keyword.arg == _MARKER_NAME_ARGUMENT:
            name_node = keyword.value
    if name_node is None or (isinstance(name_node, ast.Constant) and name_node.value is None):
        return function, has_arguments
    if isinstance(name_node, ast.Constant) and isinstance(name_node.value, str):
        return name_node.value, has_arguments
    return None, has_arguments


def _arguments_span(*, decorator: ast.Call) -> tuple[int, int, int, int] | None:
    """The span of a marker call's arguments between its parentheses, as (start line, start column, end line, end column).

    Lines count from 1 and columns are UTF-8 byte offsets, as the syntax tree gives them.
    """
    func_end_line = decorator.func.end_lineno
    func_end_col = decorator.func.end_col_offset
    call_end_line = decorator.end_lineno
    call_end_col = decorator.end_col_offset
    if func_end_line is None or func_end_col is None or call_end_line is None or call_end_col is None:
        return None
    return (func_end_line, func_end_col, call_end_line, call_end_col)


def _without_spans(*, text: str, spans: list[tuple[int, int, int, int]]) -> str:
    """The module's text with each marker call's arguments replaced by `()`, the last span first so offsets hold."""
    lines = _SOURCE_LINE.findall(text)
    encoded_lines = [line.encode("utf-8") for line in lines]
    for start_line, start_col, end_line, end_col in sorted(spans, reverse=True):
        head = encoded_lines[start_line - 1][:start_col]
        tail = encoded_lines[end_line - 1][end_col:]
        encoded_lines[start_line - 1 : end_line] = [head + b"()" + tail]
    return b"".join(encoded_lines).decode("utf-8")


def _migrate_bundle(
    *,
    bundle: str,
    text: str,
    registrations: Mapping[str, list[_MarkedFunction]],
    rewrites: list[FunctionNameRewrite],
    unresolved: list[UnresolvedFunctionName],
) -> str | None:
    """Rewrite the flat names of one bundle's `PipeFunc` steps; its new text, or None when nothing changed."""
    try:
        document = tomlkit.parse(text)
    except TOMLKitError as exc:
        if _holds_flat_function_name_hint(text=text):
            unresolved.append(UnresolvedFunctionName(bundle=bundle, reason=f"The bundle does not parse as TOML, so its steps cannot be read: {exc}"))
        return None
    # tomlkit's containers are untyped mappings: each level is read as a mapping of strings once checked to be one.
    pipes = cast("Mapping[str, object]", document).get("pipe")
    if not isinstance(pipes, Mapping):
        return None
    has_changed = False
    for pipe_code, pipe_item in cast("Mapping[str, object]", pipes).items():
        if not isinstance(pipe_item, MutableMapping):
            continue
        pipe_table = cast("MutableMapping[str, Any]", pipe_item)
        if pipe_table.get("type") != _PIPE_FUNC_TYPE:
            continue
        function_name = pipe_table.get("function_name")
        if not isinstance(function_name, str) or "." in function_name:
            continue
        candidates = registrations.get(function_name, [])
        import_paths = sorted({candidate.import_path for candidate in candidates if candidate.import_path is not None})
        if not candidates:
            unresolved.append(
                UnresolvedFunctionName(
                    bundle=bundle,
                    pipe_code=pipe_code,
                    flat_name=function_name,
                    reason=(
                        f"No module of the method tree defines a @pipe_func function registered as '{function_name}'. If the function lives "
                        "outside the method's folder, move its module into the folder, then run the migration again, or write its import "
                        "path from the folder's root by hand."
                    ),
                )
            )
            continue
        if len(candidates) > 1:
            unresolved.append(
                UnresolvedFunctionName(
                    bundle=bundle,
                    pipe_code=pipe_code,
                    flat_name=function_name,
                    reason=(
                        f"More than one @pipe_func function of the method tree is registered as '{function_name}', which the retired registry "
                        "refused as a collision: write the import path of the one the step calls."
                    ),
                    candidates=[candidate.import_path or candidate.module_path for candidate in candidates],
                )
            )
            continue
        if not import_paths:
            unresolved.append(
                UnresolvedFunctionName(
                    bundle=bundle,
                    pipe_code=pipe_code,
                    flat_name=function_name,
                    reason=(
                        f"The function registered as '{function_name}' lives in {candidates[0].module_path}, whose path is not an import path: "
                        "rename its folders and file to Python identifiers, then run the migration again."
                    ),
                )
            )
            continue
        import_path = import_paths[0]
        _replace_string_value(table=pipe_table, key="function_name", value=import_path)
        rewrites.append(FunctionNameRewrite(bundle=bundle, pipe_code=pipe_code, flat_name=function_name, import_path=import_path))
        has_changed = True
    return tomlkit.dumps(document) if has_changed else None  # pyright: ignore[reportUnknownMemberType]


def _replace_string_value(*, table: MutableMapping[str, Any], key: str, value: str) -> None:
    """Replace a string value in a tomlkit table, keeping the comment and the spacing around it."""
    new_item = tomlkit.string(value)
    old_item = table[key]
    if isinstance(old_item, String):
        new_item.trivia.indent = old_item.trivia.indent
        new_item.trivia.comment_ws = old_item.trivia.comment_ws
        new_item.trivia.comment = old_item.trivia.comment
        new_item.trivia.trail = old_item.trivia.trail
    table[key] = new_item


def _holds_flat_function_name_hint(*, text: str) -> bool:
    """Whether a bundle that does not parse mentions a PipeFunc, so its failure to parse is worth reporting."""
    return _PIPE_FUNC_TYPE in text and "function_name" in text
