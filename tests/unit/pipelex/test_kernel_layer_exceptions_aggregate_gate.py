"""No declared kernel-layer module may import the `pipelex.exceptions` aggregate — mechanically.

`pipelex/exceptions.py` is the public all-errors aggregate: it re-exports every interpreter
package's exceptions, so importing anything from it loads `pipelex.libraries`, `pipelex.pipeline`,
`pipelex.pipe_operators` and more. From a kernel-layer module that is a layer breach, and it is
exactly the breach neither existing gate can see: `check-hub-layering`'s rules only chase
`pipelex.interpreter_hub`, which the aggregate never reaches, and the import-closure test only
covers module-level imports under its declared entry points — a function-local import is invisible
to both. Five vendor adapters once loaded interpreter modules apiece through precisely this hole,
with both gates green (see `docs/contribute/hub-layering.md`, the aggregate section).

Until now the rule was prose — *import from the definition site, never from the aggregate*. This
test makes it mechanical for every package declared in `KERNEL_LAYER_PACKAGES`: it AST-walks each
module and fails on any import of `pipelex.exceptions`, module-level or function-local, absolute or
relative — and on any bare string literal naming it, because `importlib.import_module`,
`__import__` and a `mocker.patch` target all load the aggregate through a path no import node
records. That string form is the one the sibling hub-layering guard matches for the same reason, and
it is matched the same way: exact-or-boundary against the module path, so prose that merely mentions
the aggregate is not a reference. The fix for a violation is always the same and always cheap:
import the error class from the `exceptions.py` module that defines it.

Interpreter-side code and tests are out of scope on purpose — the aggregate is a legitimate public
surface for callers *outside* the kernel layer; the ban is on the layer whose import closure it
would silently widen.
"""

import ast
from pathlib import Path

from pipelex.cli.dev_cli.commands.hub_layering_guard import KERNEL_LAYER_PACKAGES, references_module

_TESTS_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "tests")
_REPO_ROOT = _TESTS_ROOT.parent

AGGREGATE_MODULE = "pipelex.exceptions"


def _imported_module_targets(*, node: ast.Import | ast.ImportFrom, module_dotted: str, is_package_init: bool) -> list[str]:
    """Resolve the dotted module targets an import statement can bind, relative imports included."""
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    base_parts: list[str]
    if node.level == 0:
        base_parts = []
    else:
        package_parts = module_dotted.split(".") if is_package_init else module_dotted.split(".")[:-1]
        climb = node.level - 1
        if climb >= len(package_parts):
            return []
        base_parts = package_parts[: len(package_parts) - climb]
    resolved_parts = base_parts + (node.module.split(".") if node.module else [])
    resolved_module = ".".join(resolved_parts)
    targets = [resolved_module] if resolved_module else []
    for alias in node.names:
        prefix = f"{resolved_module}." if resolved_module else ""
        targets.append(f"{prefix}{alias.name}")
    return targets


def find_aggregate_references(*, module_path: Path, module_dotted: str) -> list[str]:
    """Return one `path:line` locator per reference to the exceptions aggregate found in the module.

    A reference is an import statement naming it, or a string literal that *is* its dotted path — the
    dynamic-import and patch-target shape, which no import node records.
    """
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    is_package_init = module_path.name == "__init__.py"
    violations: list[str] = []
    for node in ast.walk(tree):
        candidates: list[str]
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            candidates = _imported_module_targets(node=node, module_dotted=module_dotted, is_package_init=is_package_init)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            candidates = [node.value]
        else:
            continue
        if any(references_module(candidate=candidate, target=AGGREGATE_MODULE) for candidate in candidates):
            violations.append(f"{module_path}:{node.lineno}")
    return violations


def _module_paths_for(*, dotted_package: str) -> list[Path]:
    """Yield the .py files a `KERNEL_LAYER_PACKAGES` entry covers — a package directory or a lone module."""
    base_path = _REPO_ROOT / Path(*dotted_package.split("."))
    if base_path.is_dir():
        return sorted(base_path.rglob("*.py"))
    module_file = base_path.with_suffix(".py")
    return [module_file] if module_file.is_file() else []


def _dotted_for(*, module_path: Path) -> str:
    relative_parts = module_path.relative_to(_REPO_ROOT).with_suffix("").parts
    if relative_parts[-1] == "__init__":
        relative_parts = relative_parts[:-1]
    return ".".join(relative_parts)


class TestKernelLayerExceptionsAggregateGate:
    def test_no_kernel_layer_module_imports_the_exceptions_aggregate(self) -> None:
        violations: list[str] = []
        for dotted_package in KERNEL_LAYER_PACKAGES:
            for module_path in _module_paths_for(dotted_package=dotted_package):
                violations.extend(find_aggregate_references(module_path=module_path, module_dotted=_dotted_for(module_path=module_path)))
        assert not violations, (
            "Kernel-layer modules reference the `pipelex.exceptions` aggregate, which drags interpreter packages "
            "into the kernel closure. Import each error class from the `exceptions.py` module that defines it instead:\n" + "\n".join(violations)
        )

    def test_the_gate_detects_every_banned_reference_shape(self, tmp_path: Path) -> None:
        banned_shapes = [
            "from pipelex.exceptions import ConceptError\n",
            "def helper() -> None:\n    from pipelex.exceptions import ConceptError  # noqa: PLC0415\n",
            "import pipelex.exceptions\n",
            "from pipelex import exceptions\n",
            "from .. import exceptions\n",
            "from ..exceptions import ConceptError\n",
            'import importlib\n\nmodule = importlib.import_module("pipelex.exceptions")\n',
            'module = __import__("pipelex.exceptions")\n',
            'def test_it(mocker: object) -> None:\n    mocker.patch("pipelex.exceptions.ConceptError")\n',
        ]
        for index_shape, shape_source in enumerate(banned_shapes):
            module_path = tmp_path / f"module_{index_shape}.py"
            module_path.write_text(shape_source, encoding="utf-8")
            found = find_aggregate_references(module_path=module_path, module_dotted=f"pipelex.fake.module_{index_shape}")
            assert found, f"gate missed the banned shape: {shape_source!r}"

    def test_the_gate_stays_quiet_on_definition_site_imports(self, tmp_path: Path) -> None:
        clean_source = (
            '"""Import errors from their definition site, never from the pipelex.exceptions aggregate."""\n'
            "from pipelex.core.concepts.exceptions import ConceptError\n"
            "from pipelex.system.exceptions import MissingDependencyError\n"
            "import pipelex.core.stuffs.exceptions\n"
            'MODULE_NAME = "pipelex.core.concepts.exceptions"\n'
        )
        module_path = tmp_path / "clean_module.py"
        module_path.write_text(clean_source, encoding="utf-8")
        assert find_aggregate_references(module_path=module_path, module_dotted="pipelex.fake.clean_module") == []
