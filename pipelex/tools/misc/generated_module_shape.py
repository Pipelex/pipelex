"""Check that a generated Python module has the shape its generator writes, before anyone imports it.

Two generators write Python modules with authored text in them: the runtime structure generator, which executes its
module, and the codegen emitters, whose modules a developer's app, tests or CI import. Both write only imports and
plain classes whose bodies hold a docstring and annotated fields, and authored text reaches the module only inside
string literals and comments (`pipelex.tools.misc.python_literals`). So a module holding any other statement means a
text was rendered as code, and its generator refuses it rather than let it run.

The check reads statements only: what an annotation, a base, an import or a value holds is left to the rendering.
"""

import ast
from collections.abc import Sequence


def generated_module_shape_refusal(
    *,
    module: ast.Module,
    module_label: str,
    opens_with_docstring: bool,
    expected_class_names: Sequence[str] | None,
    class_attribute_assignments: frozenset[str],
) -> str | None:
    """Why `module` is not of the shape a generator writes, or `None` when it is.

    The shape is: a header docstring when `opens_with_docstring`, then `from ... import ...` statements, then
    undecorated classes whose bases are plain names and whose body is a docstring followed only by annotated fields,
    `name: <annotation> = <value>`, or by a plain assignment to one of `class_attribute_assignments`, such as the
    `model_config` of a pydantic model. When `expected_class_names` is given, the classes are exactly those, in order.

    Args:
        module: The parsed module
        module_label: What the module is, as a refusal names it ("generated structure module")
        opens_with_docstring: Whether the module opens with a header docstring, which is then required
        expected_class_names: The names of the classes the module defines, in order, or `None` to admit any classes
        class_attribute_assignments: The class attributes a class body may assign without an annotation

    Returns:
        The refusal, naming the first statement out of shape, or `None` when the module is of the shape.
    """
    statements = list(module.body)
    if opens_with_docstring:
        if len(statements) < 2 or not is_string_statement(statements[0]):
            return f"The {module_label} does not open with its header docstring followed by its class"
        statements = statements[1:]

    import_count = 0
    while import_count < len(statements) and isinstance(statements[import_count], ast.ImportFrom):
        import_count += 1
    class_defs: list[ast.ClassDef] = []
    for statement in statements[import_count:]:
        if not isinstance(statement, ast.ClassDef):
            return f"The {module_label} holds a top-level statement other than its imports and its classes"
        class_defs.append(statement)

    if expected_class_names is not None and [class_def.name for class_def in class_defs] != list(expected_class_names):
        expected = ", ".join(f"'{name}'" for name in expected_class_names)
        return f"The {module_label} does not end with the class {expected}"

    for class_def in class_defs:
        refusal = _class_shape_refusal(class_def=class_def, class_attribute_assignments=class_attribute_assignments)
        if refusal is not None:
            return refusal
    return None


def is_string_statement(statement: ast.stmt) -> bool:
    """Whether the statement is a lone string literal, as a docstring is."""
    return isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant) and isinstance(statement.value.value, str)


def _class_shape_refusal(*, class_def: ast.ClassDef, class_attribute_assignments: frozenset[str]) -> str | None:
    """Why a generated class is not a plain class of a docstring and fields, or `None` when it is."""
    if (
        class_def.decorator_list
        or class_def.keywords
        or getattr(class_def, "type_params", None)
        or not all(isinstance(base, ast.Name) for base in class_def.bases)
    ):
        return f"The generated class '{class_def.name}' is not a plain class deriving from named bases"
    docstring, *members = class_def.body
    if not is_string_statement(docstring) or any(
        not _is_field_statement(member=member, class_attribute_assignments=class_attribute_assignments) for member in members
    ):
        return f"The body of the generated class '{class_def.name}' holds a statement other than its docstring and its fields"
    return None


def _is_field_statement(*, member: ast.stmt, class_attribute_assignments: frozenset[str]) -> bool:
    """Whether a class-body statement is an annotated field, or the plain assignment of an admitted class attribute."""
    if isinstance(member, ast.AnnAssign):
        return isinstance(member.target, ast.Name)
    if isinstance(member, ast.Assign):
        return len(member.targets) == 1 and isinstance(member.targets[0], ast.Name) and member.targets[0].id in class_attribute_assignments
    return False
