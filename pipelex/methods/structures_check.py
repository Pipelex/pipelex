"""The structures-refusal check, reusable by the CLI, the runner, and the loader.

The rule (execution locus decides): `.mthds` content is data — always acceptable. PipeFunc
`.py` executes in the network-blocked sandbox — acceptable on sandbox-hosted deployments.
`structures/*.py` is imported into the runner's own process, so a fetched package that
declares `StructuredContent` subclasses is refused, loudly, with an error that names the
rule. The discrimination is what the AST declares — the same AST pre-check the library
loader's import gate performs — never mere `.py` presence: PipeFunc-only Python is
supported.
"""

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from pipelex.methods.exceptions import MethodStructuresRefusedError
from pipelex.tools.typing.exceptions import ModuleFileError
from pipelex.tools.typing.module_inspector import find_class_names_in_file

STRUCTURE_BASE_CLASS_NAME = "StructuredContent"

STRUCTURES_REFUSAL_RULE = "hosted execution accepts MTHDS concepts and sandboxed PipeFuncs, not in-process Python"

_SKIPPED_DIR_NAMES = {".git", "__pycache__"}


class StructuredContentViolation(BaseModel):
    """One `.py` file inside a package that declares `StructuredContent` subclasses."""

    model_config = ConfigDict(frozen=True)

    relative_path: str
    class_names: list[str]


def scan_structured_content_classes(*, package_dir: Path) -> list[StructuredContentViolation]:
    """AST-scan a package directory for `.py` files declaring `StructuredContent` subclasses.

    Files that cannot be parsed are skipped: the loader's own AST import gate skips them
    the same way, so they cannot smuggle a structure class into the process.

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
            class_names = find_class_names_in_file(py_file, base_class_names=[STRUCTURE_BASE_CLASS_NAME])
        except ModuleFileError:
            # Unparseable or otherwise unloadable file: the loader's AST gate would skip it too.
            continue
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
