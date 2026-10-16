"""The runner's error-code gate: every `PipelexError` subclass the api member defines declares its registry code.

The library's gate, `tests/unit/pipelex/errors/test_error_code_gate.py` at the repository root, discovers the
classes of the `pipelex` package and reads the raise sites of both the package and the runner, but it never
imports `pipelex_api`, so the runner's own classes escape it. This test imports every module of the runner,
collects the `PipelexError` subclasses it defines, and holds them to the same rules: a code in the class's own
body, nothing the code decides declared beside it, the class in an error module, and every raise site of one of
them choosing only a code its class declares and never constructing an abstract base.
"""

import importlib
import pkgutil
from pathlib import Path

from mthds.protocol.problem.registry import CoreCode
from pipelex.base_exceptions import PipelexError
from pipelex.errors.error_code_declaration import AbstractError, declared_error_codes, describe_error_code_declaration
from pipelex.errors.error_code_sites import iter_chosen_code_sites, iter_raised_class_sites
from pipelex.errors.error_codes import ErrorCode, error_code_spec
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode

import pipelex_api

_PACKAGE_NAME = pipelex_api.__name__
_PACKAGE_ROOT = Path(pipelex_api.__file__).resolve().parent

# What a code decides, which a class no longer declares: `ErrorReport` reads all four from the code.
_ATTRIBUTES_THE_CODE_DECIDES: tuple[str, ...] = ("error_domain", "retryable", "_declared_title", "_declared_type_uri")


def _runner_error_classes() -> dict[str, type[PipelexError]]:
    """Every `PipelexError` subclass the runner defines, by name, after importing every module of the runner."""
    for module_info in pkgutil.walk_packages(pipelex_api.__path__, prefix=f"{_PACKAGE_NAME}."):
        importlib.import_module(module_info.name)
    classes: dict[str, type[PipelexError]] = {}
    stack: list[type[PipelexError]] = [PipelexError]
    seen: set[type[PipelexError]] = set()
    while stack:
        cls = stack.pop()
        if cls in seen:
            continue
        seen.add(cls)
        if cls.__module__ == _PACKAGE_NAME or cls.__module__.startswith(f"{_PACKAGE_NAME}."):
            classes[cls.__name__] = cls
        stack.extend(cls.__subclasses__())
    return classes


def _source_files() -> list[Path]:
    return [path for path in sorted(_PACKAGE_ROOT.rglob("*.py")) if "__pycache__" not in path.parts]


def _relative(path: Path) -> str:
    return str(path.relative_to(_PACKAGE_ROOT.parent))


class TestRunnerErrorCodeGate:
    def test_the_gate_reads_a_non_empty_set(self) -> None:
        """Anti-vacuity: the discovery found the runner's boot errors and its source files."""
        classes = _runner_error_classes()
        assert {"ApiBootConfigError", "InvalidAuthModeError", "InvalidErrorDisclosureError"} <= set(classes)
        assert _source_files()

    def test_every_runner_error_class_declares_its_code(self) -> None:
        missing = sorted(f"{cls.__module__}.{cls.__qualname__}" for cls in _runner_error_classes().values() if "error_code" not in cls.__dict__)
        assert not missing, (
            "These PipelexError subclasses of the runner declare no `error_code` in their own class body; declare the "
            "registry code, an ErrorCodeSet, InheritsCause or ABSTRACT_ERROR (pipelex/errors/error_code_declaration.py):\n"
            + "\n".join(f"  - {name}" for name in missing)
        )

    def test_every_declared_code_is_registered(self) -> None:
        for cls in _runner_error_classes().values():
            for code in declared_error_codes(cls.error_code):
                assert isinstance(code, (CoreCode, PipelexErrorCode)), f"{cls.__name__} declares {code!r}, which is no registered code"
                assert error_code_spec(code).code == code

    def test_no_runner_error_class_declares_what_its_code_decides(self) -> None:
        offenders = sorted(
            f"{cls.__module__}.{cls.__qualname__}.{attribute}"
            for cls in _runner_error_classes().values()
            for attribute in _ATTRIBUTES_THE_CODE_DECIDES
            if attribute in cls.__dict__
        )
        assert not offenders, "These classes declare what their code decides; remove the attribute and choose the code instead:\n" + "\n".join(
            f"  - {offender}" for offender in offenders
        )

    def test_every_runner_error_class_lives_in_an_error_module(self) -> None:
        offenders = sorted(
            f"  - {cls.__module__}.{cls.__qualname__}"
            for cls in _runner_error_classes().values()
            if not (cls.__module__.rpartition(".")[2] == "exceptions" or cls.__module__.endswith("_exceptions"))
        )
        assert not offenders, "These error classes live outside an `exceptions.py` or `<topic>_exceptions.py` module:\n" + "\n".join(offenders)

    def test_no_abstract_runner_class_is_raised_directly(self) -> None:
        abstract_names = {name for name, cls in _runner_error_classes().items() if isinstance(cls.__dict__.get("error_code"), AbstractError)}
        offenders = [
            f"  - {_relative(site.path)}:{site.line} raises {site.class_name}"
            for path in _source_files()
            for site in iter_raised_class_sites(path=path, source=path.read_text(encoding="utf-8"))
            if site.class_name in abstract_names
        ]
        assert not offenders, "These raise sites construct an abstract base; raise the subclass that names the fault:\n" + "\n".join(offenders)

    def test_every_chosen_code_is_one_its_runner_class_declares(self) -> None:
        classes = _runner_error_classes()
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
                elif chosen not in declared_error_codes(cls.error_code):
                    offenders.append(
                        f"  - {where}: {site.class_name} chooses {chosen}, but declares {describe_error_code_declaration(cls.error_code)}"
                    )
        assert not offenders, "These raise sites choose a code their class does not declare:\n" + "\n".join(offenders)
