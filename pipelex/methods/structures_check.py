"""The structures-refusal check, reusable by the CLI, the runner, and the loader.

The rule (execution locus decides): `.mthds` content is data — always acceptable. PipeFunc
`.py` executes in the network-blocked sandbox — acceptable on sandbox-hosted deployments.
`structures/*.py` is imported into the runner's own process, so a fetched package that
declares `StructuredContent` subclasses is refused, loudly, with an error that names the
rule. The discrimination is what the AST declares — never mere `.py` presence: PipeFunc-only
Python is supported.

The scan is alias-aware: a base written as `StructuredContent`, imported under another name
(`from ... import StructuredContent as SC`), or reached as an attribute
(`module.StructuredContent`, whatever the module was imported as) is caught. It remains a
static pre-check, and honestly so: dynamic tricks (rebinding through assignments, metaclass
construction, `type(...)` calls) are out of its scope — its job is that straightforward
declarations and straightforward aliasing cannot defeat the refusal. A subclass of a caught
class in the same package is covered transitively, because the file declaring the base is
itself refused and refusal applies to the whole package.
"""

import ast
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from pipelex.methods.exceptions import MethodStructuresRefusedError

STRUCTURE_BASE_CLASS_NAME = "StructuredContent"

STRUCTURES_REFUSAL_RULE = "hosted execution accepts MTHDS concepts and sandboxed PipeFuncs, not in-process Python"

_SKIPPED_DIR_NAMES = {".git", "__pycache__"}


def _collect_base_name_bindings(*, tree: ast.Module) -> set[str]:
    """Names bound to `StructuredContent` in this module: the literal name plus `import ... as` aliases."""
    bindings = {STRUCTURE_BASE_CLASS_NAME}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for import_alias in node.names:
                if import_alias.name == STRUCTURE_BASE_CLASS_NAME and import_alias.asname:
                    bindings.add(import_alias.asname)
    return bindings


def _structured_content_class_names(*, tree: ast.Module) -> list[str]:
    """Class names in *tree* whose declared bases resolve to `StructuredContent`.

    A base matches when it is a name bound to `StructuredContent` (directly or via an
    `import ... as` alias) or an attribute access ending in `.StructuredContent` — the
    attribute form always spells the real class name, whatever the module alias.
    """
    bindings = _collect_base_name_bindings(tree=tree)
    class_names: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for base in node.bases:
            if isinstance(base, ast.Name) and base.id in bindings:
                class_names.append(node.name)
                break
            if isinstance(base, ast.Attribute) and base.attr == STRUCTURE_BASE_CLASS_NAME:
                class_names.append(node.name)
                break
    return class_names


class StructuredContentViolation(BaseModel):
    """One `.py` file inside a package that declares `StructuredContent` subclasses."""

    model_config = ConfigDict(frozen=True)

    relative_path: str
    class_names: list[str]


def scan_structured_content_classes(*, package_dir: Path) -> list[StructuredContentViolation]:
    """AST-scan a package directory for `.py` files declaring `StructuredContent` subclasses.

    Alias-aware: bases reached through `from ... import StructuredContent as SC` or through
    an attribute access (`module.StructuredContent`) are caught alongside the literal name.
    Files that cannot be parsed are skipped: an unparseable file cannot be imported either,
    so it cannot smuggle a structure class into the process.

    Args:
        package_dir: The package directory to scan.

    Returns:
        One violation per offending file, with the subclass names it declares.
    """
    violations: list[StructuredContentViolation] = []
    for py_file in sorted(package_dir.rglob("*.py")):
        relative = py_file.relative_to(package_dir)
        if any(part in _SKIPPED_DIR_NAMES for part in relative.parts):
            continue
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(py_file))
        except (OSError, SyntaxError, ValueError):
            # Unparseable or unreadable file: it cannot be imported either, so it cannot
            # smuggle a structure class into the process.
            continue
        class_names = _structured_content_class_names(tree=tree)
        if class_names:
            violations.append(StructuredContentViolation(relative_path=relative.as_posix(), class_names=class_names))
    return violations


def describe_structured_content_violations(*, violations: list[StructuredContentViolation]) -> str:
    """Render violations as a compact, human-readable listing."""
    return "; ".join(f"{violation.relative_path} defines {', '.join(violation.class_names)}" for violation in violations)


def ensure_no_structured_content_python(*, package_dir: Path, package_address: str) -> None:
    """Refuse a package that declares in-process Python structure classes.

    Args:
        package_dir: The package directory to check.
        package_address: The package's full address, named in the error.

    Raises:
        MethodStructuresRefusedError: If the package declares `StructuredContent` subclasses.
            The message names the rule and teaches the fix.
    """
    violations = scan_structured_content_classes(package_dir=package_dir)
    if not violations:
        return
    details = describe_structured_content_violations(violations=violations)
    msg = (
        f"Method package '{package_address}' declares Python structure classes ({details}), which are imported "
        f"into the runner's own process. Refused: {STRUCTURES_REFUSAL_RULE}. Express the types as MTHDS concepts "
        f"with inline structures instead of Python classes."
    )
    raise MethodStructuresRefusedError(msg)
