"""The form of a `PipeFunc`'s `function_name`: a Python import path from the root of the method tree.

`function_name = "funcs.totals.compute_totals"` names the function `compute_totals` of the module `funcs.totals`, the
file `funcs/totals.py` or `funcs/totals/__init__.py` of the tree, imported with the tree's root as the import root
(`mthds/docs/spec/mthds-format.md`, "Locating the function"). The name is normalized to NFC, then split at its last
dot: a name with no dot names no module and is refused, and each segment must be a Python identifier that is not a
keyword and that NFKC leaves unchanged, so a ligature or a fullwidth letter is refused rather than mapped to another
name. This is the form alone, checked as the bundle is parsed; whether the tree holds the module, and the module the
function, is checked when the library validates the step.

A flat name, such as `compute_totals`, is the key of the retired function registry: it is refused with the command that
rewrites it, `pipelex fix function-names`.
"""

from typing import NamedTuple

from mthds.method_tree.python_modules import is_valid_function_segment
from mthds.method_tree.tree_path import nfc

#: The command that rewrites every flat `function_name` of a method into its import path.
FUNCTION_NAMES_MIGRATION_COMMAND = "pipelex fix function-names"


class FunctionImportPath(NamedTuple):
    """A `function_name` split at its last dot: the module's dotted import name and the function's name in it."""

    module_name: str
    function: str


def function_name_form_violation(*, function_name: str) -> str | None:
    """Why `function_name` is not an import path a `PipeFunc` can name, or None when its form is valid.

    Args:
        function_name: The `function_name` as the bundle writes it.

    Returns:
        None when the form is valid, else the refusal message, which names the `function_name`.
    """
    normalized = nfc(function_name)
    if "." not in normalized:
        return (
            f"The function_name '{function_name}' holds no dot, so it names no module: a PipeFunc names its function by its import path "
            "from the root of the method tree, such as 'funcs.totals.compute_totals' for the function compute_totals of the file "
            f"funcs/totals.py. A flat name was the key of the retired function registry; run `{FUNCTION_NAMES_MIGRATION_COMMAND} "
            "<method folder>` to rewrite it."
        )
    for segment in normalized.split("."):
        if not is_valid_function_segment(segment):
            return (
                f"The function_name '{function_name}' holds the segment '{segment}', which is not a Python identifier, is a Python keyword, "
                "or changes under NFKC normalization."
            )
    return None


def split_function_name(*, function_name: str) -> FunctionImportPath:
    """Split a `function_name` whose form is valid into its module's import name and the function's name.

    Args:
        function_name: A `function_name` that `function_name_form_violation` accepts.

    Returns:
        The module's dotted import name and the function's name, both in NFC.

    Raises:
        ValueError: When the form is not valid.
    """
    violation = function_name_form_violation(function_name=function_name)
    if violation is not None:
        raise ValueError(violation)
    module_name, _, function = nfc(function_name).rpartition(".")
    return FunctionImportPath(module_name=module_name, function=function)
