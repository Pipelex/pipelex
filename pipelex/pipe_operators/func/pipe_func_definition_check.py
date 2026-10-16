"""The static check of a `PipeFunc`'s function: its form, proven from the module's syntax tree without running Python.

The function a `function_name` names must be a top-level `def` or `async def` of its module, bound there once, and
decorated with the `@pipe_func()` marker, directly or through an import alias of it or of its module. Anything the
syntax tree cannot decide is refused rather than guessed at: a re-export (`from .impl import compute_totals`), an
assignment (`compute_totals = build()`), a class, a definition under an `if`, a `try` or a loop, and a name bound twice.
This is the strict form of `wip/extra-files/design.md`'s D10: validation proves it from the source alone, and the
calling convention, which needs the annotations resolved, is checked once the module is imported
(`pipe_func_signature`).
"""

import ast

from pipelex.pipe_operators.func.function_name import FUNCTION_NAMES_MIGRATION_COMMAND
from pipelex.system.registries.func_registry import PIPE_FUNC_MARKER_MODULE, PIPE_FUNC_MARKER_NAME

_MARKER_PARENT_MODULE, _, _MARKER_MODULE_LEAF = PIPE_FUNC_MARKER_MODULE.rpartition(".")
_MARKER_SPELLING = f"@{PIPE_FUNC_MARKER_NAME}()"
_COMPOUND_STATEMENTS = (ast.If, ast.Try, ast.TryStar, ast.With, ast.AsyncWith, ast.For, ast.AsyncFor, ast.While, ast.Match)


def pipe_func_definition_violation(*, source: str, function: str, module_label: str) -> str | None:
    """Why the module's source does not define `function` as a `PipeFunc` may call it, or None when it does.

    Args:
        source: The module's source text.
        function: The name of the function in the module, the last segment of the `function_name`.
        module_label: How the messages name the module, such as its tree path.

    Returns:
        None when the form is proven, else a refusal message naming the module and the function.
    """
    try:
        module = ast.parse(source, filename=module_label)
    except SyntaxError as exc:
        return f"The module {module_label} does not parse as Python: {exc.msg} (line {exc.lineno})."

    definitions: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for statement in module.body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if statement.name == function:
                definitions.append(statement)
            continue
        other_binding = _other_binding_kind(statement=statement, name=function)
        if other_binding is not None:
            return (
                f"The module {module_label} binds '{function}' through {other_binding}, which validation cannot prove to be a function "
                f"carrying {_MARKER_SPELLING}: define it as a top-level def or async def of {module_label} itself."
            )

    if not definitions:
        return (
            f"The module {module_label} defines no top-level function '{function}': the function must be a def or async def at the top of the module."
        )
    if len(definitions) > 1:
        return f"The module {module_label} defines '{function}' more than once at top level, so which one runs depends on the order: keep one."
    return _marker_violation(definition=definitions[0], marker_refs=marker_references(module=module), module_label=module_label)


def _other_binding_kind(*, statement: ast.stmt, name: str) -> str | None:
    """How a top-level statement other than a function definition binds `name`, described for a message, or None."""
    if isinstance(statement, ast.ClassDef):
        return "a class definition" if statement.name == name else None
    if isinstance(statement, (ast.Import, ast.ImportFrom)):
        for alias in statement.names:
            bound_name = alias.asname or alias.name.partition(".")[0]
            if bound_name == name:
                return "an import, which re-exports a function defined elsewhere"
        return None
    if isinstance(statement, _COMPOUND_STATEMENTS):
        return "a definition under a condition, a loop or a context manager" if _binds_name_anywhere(node=statement, name=name) else None
    if _binds_name_anywhere(node=statement, name=name):
        return "an assignment"
    return None


def _binds_name_anywhere(*, node: ast.AST, name: str) -> bool:
    """Whether `node` binds `name` in the module's scope, at any depth short of a nested function or class body."""
    pending: list[ast.AST] = [node]
    while pending:
        current = pending.pop()
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if current.name == name:
                return True
            continue
        if isinstance(current, ast.Lambda):
            continue
        if isinstance(current, ast.Name) and current.id == name and isinstance(current.ctx, (ast.Store, ast.Del)):
            return True
        if isinstance(current, (ast.Import, ast.ImportFrom)):
            for alias in current.names:
                if (alias.asname or alias.name.partition(".")[0]) == name:
                    return True
        if isinstance(current, ast.ExceptHandler) and current.name == name:
            return True
        if isinstance(current, (ast.MatchAs, ast.MatchStar)) and current.name == name:
            return True
        pending.extend(ast.iter_child_nodes(current))
    return False


def marker_references(*, module: ast.Module) -> frozenset[str]:
    """The dotted spellings under which the module's top-level imports make the marker reachable."""
    references: set[str] = set()
    for statement in module.body:
        if isinstance(statement, ast.ImportFrom) and statement.level == 0:
            for alias in statement.names:
                if statement.module == PIPE_FUNC_MARKER_MODULE and alias.name == PIPE_FUNC_MARKER_NAME:
                    references.add(alias.asname or alias.name)
                elif statement.module == _MARKER_PARENT_MODULE and alias.name == _MARKER_MODULE_LEAF:
                    references.add(f"{alias.asname or alias.name}.{PIPE_FUNC_MARKER_NAME}")
        elif isinstance(statement, ast.Import):
            for alias in statement.names:
                if alias.name != PIPE_FUNC_MARKER_MODULE:
                    continue
                spelled_module = alias.asname or PIPE_FUNC_MARKER_MODULE
                references.add(f"{spelled_module}.{PIPE_FUNC_MARKER_NAME}")
    return frozenset(references)


def _dotted_name(*, expression: ast.expr) -> str | None:
    """The dotted spelling of a name or attribute chain, such as `registries.func_registry.pipe_func`, else None."""
    if isinstance(expression, ast.Name):
        return expression.id
    if isinstance(expression, ast.Attribute):
        owner = _dotted_name(expression=expression.value)
        return f"{owner}.{expression.attr}" if owner is not None else None
    return None


def marker_call(*, definition: ast.FunctionDef | ast.AsyncFunctionDef, marker_refs: frozenset[str]) -> ast.Call | None:
    """The decorator of a function that calls the marker, such as `@pipe_func()` or `@pipe_func(name="x")`, else None."""
    for decorator in definition.decorator_list:
        if isinstance(decorator, ast.Call) and _dotted_name(expression=decorator.func) in marker_refs:
            return decorator
    return None


def _marker_violation(*, definition: ast.FunctionDef | ast.AsyncFunctionDef, marker_refs: frozenset[str], module_label: str) -> str | None:
    """Why the function's decorators do not include the marker as `@pipe_func()`, or None when they do."""
    function = definition.name
    for decorator in definition.decorator_list:
        if isinstance(decorator, ast.Call) and _dotted_name(expression=decorator.func) in marker_refs:
            if decorator.args or decorator.keywords:
                return (
                    f"The function '{function}' of {module_label} passes arguments to {_MARKER_SPELLING}, which takes none: the import path "
                    "in function_name is the function's only name, so the registration name the marker once took is gone. "
                    f"Run `{FUNCTION_NAMES_MIGRATION_COMMAND} <method folder>` to rewrite the method."
                )
            return None
        if _dotted_name(expression=decorator) in marker_refs:
            return f"The function '{function}' of {module_label} is decorated with the marker without parentheses: write {_MARKER_SPELLING}."
    return (
        f"The function '{function}' of {module_label} is not decorated with {_MARKER_SPELLING}, imported from {PIPE_FUNC_MARKER_MODULE}: "
        "only a function carrying the marker can be called from a PipeFunc step."
    )
