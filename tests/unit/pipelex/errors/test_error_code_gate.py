"""The error-code gate: every ``PipelexError`` subclass declares its registry code, and every raise site agrees.

The code an error carries decides its title, its documentation page, who must act and whether a retry can
succeed, so a class without one would report the catch-all ``runtime.unexpected`` for a fault that has a
precise reading. These tests fail the build on:

- a subclass that declares no ``error_code`` in its own body, whatever its parents declare;
- a subclass that still declares what its code now decides (a domain, a retry verdict, a title, a page);
- a ``raise`` that constructs an abstract base directly;
- a raise site that chooses, with ``with_error_code``, a code its class does not declare.

The set of classes comes from ``iter_pipelex_error_subclasses()``, which force-loads every error module; the
raise sites are read from the source of the package and of the runner, ``api/pipelex_api``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from mthds.protocol.problem.registry import CoreCode

import pipelex
from pipelex.errors.error_class_discovery import iter_pipelex_error_subclasses
from pipelex.errors.error_code_declaration import AbstractError, declared_error_codes, describe_error_code_declaration
from pipelex.errors.error_code_sites import iter_chosen_code_sites, iter_raised_class_sites
from pipelex.errors.error_codes import ErrorCode, error_code_spec
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode

if TYPE_CHECKING:
    from pipelex.base_exceptions import PipelexError

_PACKAGE_ROOT: Path = Path(pipelex.__file__).resolve().parent
_REPO_ROOT: Path = _PACKAGE_ROOT.parent
_SOURCE_ROOTS: tuple[Path, ...] = (_PACKAGE_ROOT, _REPO_ROOT / "api" / "pipelex_api")

# What a code decides, which a class no longer declares: ``ErrorReport`` reads all four from the code.
_ATTRIBUTES_THE_CODE_DECIDES: tuple[str, ...] = ("error_domain", "retryable", "_declared_title", "_declared_type_uri")


def _error_classes_by_name() -> dict[str, type[PipelexError]]:
    return {cls.__name__: cls for cls in iter_pipelex_error_subclasses()}


def _source_files() -> list[Path]:
    files: list[Path] = []
    for root in _SOURCE_ROOTS:
        files.extend(path for path in sorted(root.rglob("*.py")) if "__pycache__" not in path.parts)
    return files


def _relative(path: Path) -> str:
    return str(path.relative_to(_REPO_ROOT))


class TestErrorCodeGate:
    def test_the_gate_reads_a_non_empty_set(self) -> None:
        """Anti-vacuity: the discovery found the error classes and the source files."""
        classes = _error_classes_by_name()
        assert "PipelexError" in classes
        assert len(classes) > 1
        assert _source_files()

    def test_every_error_class_declares_its_code(self) -> None:
        missing = sorted(f"{cls.__module__}.{cls.__qualname__}" for cls in iter_pipelex_error_subclasses() if "error_code" not in cls.__dict__)
        if missing:
            lines = [
                "These PipelexError subclasses declare no `error_code` in their own class body:",
                "",
                *(f"  - {name}" for name in missing),
                "",
                "Declare the registry code the class raises, an ErrorCodeSet its raise sites choose from, InheritsCause",
                "with a fallback for a wrapper that adds no fact deciding the code, or ABSTRACT_ERROR for a base that is",
                "never raised directly (pipelex/errors/error_code_declaration.py). A code the registry lacks is added to",
                "pipelex/errors/registry/pipelex-error-registry.yaml first.",
            ]
            raise AssertionError("\n".join(lines))

    def test_every_declared_code_is_registered(self) -> None:
        for cls in iter_pipelex_error_subclasses():
            for code in declared_error_codes(cls.error_code):
                assert isinstance(code, (CoreCode, PipelexErrorCode)), f"{cls.__name__} declares {code!r}, which is no registered code"
                assert error_code_spec(code).code == code

    def test_no_error_class_declares_what_its_code_decides(self) -> None:
        offenders = sorted(
            f"{cls.__module__}.{cls.__qualname__}.{attribute}"
            for cls in iter_pipelex_error_subclasses()
            for attribute in _ATTRIBUTES_THE_CODE_DECIDES
            if attribute in cls.__dict__
        )
        assert not offenders, "These classes declare what their code decides; remove the attribute and choose the code instead:\n" + "\n".join(
            f"  - {offender}" for offender in offenders
        )

    def test_no_abstract_class_is_raised_directly(self) -> None:
        classes = _error_classes_by_name()
        abstract_names = {name for name, cls in classes.items() if isinstance(cls.__dict__.get("error_code"), AbstractError)}
        offenders: list[str] = []
        for path in _source_files():
            for site in iter_raised_class_sites(path=path, source=path.read_text(encoding="utf-8")):
                if site.class_name in abstract_names:
                    offenders.append(f"  - {_relative(site.path)}:{site.line} raises {site.class_name}")
        assert not offenders, (
            "These raise sites construct an abstract base, which reports no code of its own; raise the subclass that "
            "names the fault, or give the class a code:\n" + "\n".join(offenders)
        )

    def test_every_chosen_code_is_one_its_class_declares(self) -> None:
        classes = _error_classes_by_name()
        offenders: list[str] = []
        for path in _source_files():
            for site in iter_chosen_code_sites(path=path, source=path.read_text(encoding="utf-8")):
                cls = classes.get(site.class_name)
                if cls is None:
                    continue
                enum_class = CoreCode if site.enum_name == "CoreCode" else PipelexErrorCode
                chosen: ErrorCode | None = getattr(enum_class, site.member_name, None)
                where = f"{_relative(site.path)}:{site.line}"
                if chosen is None:
                    offenders.append(f"  - {where}: {site.enum_name}.{site.member_name} is no registered code")
                    continue
                if chosen not in declared_error_codes(cls.error_code):
                    declared = describe_error_code_declaration(cls.error_code)
                    offenders.append(f"  - {where}: {site.class_name} chooses {chosen}, but declares {declared}")
        assert not offenders, "These raise sites choose a code their class does not declare:\n" + "\n".join(offenders)
