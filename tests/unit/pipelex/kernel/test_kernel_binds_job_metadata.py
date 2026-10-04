"""A kernel function that takes a ``job_metadata`` opens its body by binding it onto the log context.

The rule is stated by signature rather than as a list of functions, so that it covers the next function
added as well as the ones written today: every module-level function in ``pipelex/kernel/`` with a
``job_metadata`` parameter must open its body — after its docstring — with
``with job_metadata.log_context():``. Opening the body is what makes the binding cover the whole step,
prompt assembly and write-back included, and not only the generation call in the middle.

The kernel's doctrine records that five ops were once added with every gate green and none of them
covered; this sweep is what keeps a sixth from arriving without its binding. The behaviour the rule
buys is tested in ``test_kernel_log_context.py``; this test only makes the rule impossible to forget.
"""

import ast
from pathlib import Path

import pipelex.kernel

KERNEL_DIR = Path(pipelex.kernel.__file__).parent

JOB_METADATA_PARAMETER = "job_metadata"


def _is_the_binding_call(expression: ast.expr) -> bool:
    """Whether ``expression`` is exactly ``job_metadata.log_context()``."""
    if not isinstance(expression, ast.Call) or expression.args or expression.keywords:
        return False
    method = expression.func
    if not isinstance(method, ast.Attribute) or method.attr != "log_context":
        return False
    return isinstance(method.value, ast.Name) and method.value.id == JOB_METADATA_PARAMETER


def _opens_with_the_binding(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Whether the body's first statement, past a docstring, is ``with job_metadata.log_context():``."""
    body = function.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        body = body[1:]
    if not body or not isinstance(body[0], ast.With):
        return False
    return any(_is_the_binding_call(item.context_expr) for item in body[0].items)


def unbound_functions(*, source: str) -> list[str]:
    """The module-level functions in ``source`` that take a ``job_metadata`` and do not open by binding it."""
    offenders: list[str] = []
    for node in ast.parse(source).body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        arguments = node.args
        parameter_names = {argument.arg for argument in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs)}
        if JOB_METADATA_PARAMETER in parameter_names and not _opens_with_the_binding(node):
            offenders.append(node.name)
    return offenders


class TestKernelBindsJobMetadata:
    def test_every_kernel_function_taking_job_metadata_opens_by_binding_it(self) -> None:
        offenders = [
            f"{module_path.name}::{function_name}"
            for module_path in sorted(KERNEL_DIR.glob("*.py"))
            for function_name in unbound_functions(source=module_path.read_text(encoding="utf-8"))
        ]

        assert not offenders, (
            f"these kernel functions take a `job_metadata` but do not open their body with "
            f"`with job_metadata.log_context():`: {offenders}. A program driving the kernel has no interpreter "
            "to bind the run and the step for it, so a kernel step that does not bind them emits lines naming "
            "neither. See docs/under-the-hood/pipelex-kernel.md, 'The log context'."
        )

    def test_the_sweep_sees_a_function_that_does_not_bind(self) -> None:
        """The control: without it, a predicate that matched nothing would leave the real case green forever."""
        source = '''
async def binds(*, job_metadata):
    """Docstring."""
    with job_metadata.log_context():
        return 1

async def forgets(*, job_metadata):
    return 1

async def binds_too_late(*, job_metadata):
    value = 1
    with job_metadata.log_context():
        return value

async def binds_something_else(*, job_metadata, other):
    with other.log_context():
        return 1

def takes_no_job_metadata(*, memory):
    return memory
'''

        assert unbound_functions(source=source) == ["forgets", "binds_too_late", "binds_something_else"]
