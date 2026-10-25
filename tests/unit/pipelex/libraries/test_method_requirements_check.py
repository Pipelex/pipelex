import shlex
import sys
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError
from pathlib import Path

import pytest
from mthds.method_tree.lister import list_method_tree
from mthds.protocol.problem.registry import CoreCode, ProblemDomain
from pytest_mock import MockerFixture

from pipelex.base_exceptions import PipelexError, ValidationErrorCategory
from pipelex.errors.problem import ProblemView
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.libraries.exceptions import (
    HostLibraryRequirementsError,
    HostLibraryTreeError,
    MethodRequirementsFileError,
    MethodRequirementsNotMetError,
)
from pipelex.libraries.method_requirements import (
    ensure_method_requirements_met,
    ensure_package_requirements_met,
    ensure_served_method_requirements_met,
    requirements_needed_in,
)
from pipelex.libraries.method_tree_listing import MethodTreeListing
from pipelex.libraries.method_trees import reporting_host_library_tree_faults
from pipelex.libraries.package_environments import OfferedPackageEnvironment
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle_translation import translate_to_validate_bundle_error
from pipelex.plugins.pipe_func_package_offer_registry import PipeFuncPackageOffer, PipeFuncPackageOfferRequest, PipeFuncPackageRefusal
from pipelex.system.configuration.pipe_func_config import PipeFuncConfig
from tests.unit.pipelex.libraries.test_data import MethodRequirementsTestData

_MODULE = "pipelex.libraries.method_requirements"
_ABSENT_PACKAGE = "pipelex-requirements-test-absent"
_MANIFEST = '[package]\naddress = "github.com/pipelex-tests/requirements"\nversion = "1.0.0"\ndescription = "A nested package"\n'


def _write(*, directory: Path, tree_path: str, content: str | bytes) -> None:
    file_path = directory / tree_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        file_path.write_bytes(content)
    else:
        file_path.write_text(content, encoding="utf-8")


def _method(*, directory: Path, requirements: str | bytes | None, with_python: bool = True) -> Path:
    _write(directory=directory, tree_path="main.mthds", content="domain = 'requirements_tests'\n")
    if with_python:
        _write(directory=directory, tree_path="funcs/crunch.py", content="def crunch() -> int:\n    return 1\n")
    if requirements is not None:
        _write(directory=directory, tree_path="requirements.txt", content=requirements)
    return directory


def _assert_the_host_s_fault(*, error: PipelexError) -> None:
    """The host's library is the operator's configuration: its code is the operator's, and its message the operator's alone."""
    caller = error.to_problem(view=ProblemView.CALLER)
    assert caller.code == PipelexErrorCode.CONFIG_INVALID
    assert caller.domain == ProblemDomain.OPERATOR
    assert error.message not in str(caller.to_wire())
    operator = error.to_problem(view=ProblemView.OPERATOR)
    assert operator.diagnostics is not None
    assert operator.diagnostics.message == error.message


class TestMethodRequirementsCheck:
    @pytest.mark.parametrize(
        ("topic", "requirements", "with_python", "nested_requirements"),
        [
            ("no Python to import a package", "-r base.txt\n", False, None),
            ("no requirements.txt", None, True, None),
            ("only the root's file declares anything", None, True, "-r base.txt\n"),
        ],
    )
    def test_a_tree_without_requirements_to_check_is_never_read(
        self, mocker: MockerFixture, tmp_path: Path, topic: str, requirements: str | None, with_python: bool, nested_requirements: str | None
    ) -> None:
        resolve = mocker.patch(f"{_MODULE}.resolve_pipe_func_package_environment")
        _method(directory=tmp_path, requirements=requirements, with_python=with_python)
        if nested_requirements is not None:
            _write(directory=tmp_path, tree_path="funcs/requirements.txt", content=nested_requirements)

        ensure_method_requirements_met(trees=[list_method_tree(tmp_path)], names_host_paths=True)

        assert resolve.call_count == 0, topic

    def test_refused_lines_are_named_each_before_any_environment_is_read(self, mocker: MockerFixture, tmp_path: Path) -> None:
        resolve = mocker.patch(f"{_MODULE}.resolve_pipe_func_package_environment")
        _method(directory=tmp_path, requirements="# data\n-r base.txt\npandas>=2\nname @ https://example.com/x.whl\n")

        with pytest.raises(MethodRequirementsFileError) as exc_info:
            ensure_method_requirements_met(trees=[list_method_tree(tmp_path)], names_host_paths=True)

        resolve.assert_not_called()
        message = exc_info.value.message
        assert f"The method rooted at '{tmp_path}'" in message
        assert "line 2 '-r base.txt'" in message
        assert "line 4 'name @ https://example.com/x.whl'" in message
        items = exc_info.value.blueprint_validation_errors
        assert [(item.source, item.line) for item in items] == [("requirements.txt", 2), ("requirements.txt", 4)]
        problem = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert problem.code == CoreCode.METHOD_PACKAGE_INVALID
        assert problem.domain == ProblemDomain.METHOD

    def test_a_file_that_is_not_utf8_is_refused(self, tmp_path: Path) -> None:
        _method(directory=tmp_path, requirements=b"pandas\xff\n")

        with pytest.raises(MethodRequirementsFileError, match="not UTF-8 text"):
            ensure_method_requirements_met(trees=[list_method_tree(tmp_path)], names_host_paths=True)

    def test_comments_alone_need_no_environment(self, mocker: MockerFixture, tmp_path: Path) -> None:
        resolve = mocker.patch(f"{_MODULE}.resolve_pipe_func_package_environment")
        _method(directory=tmp_path, requirements="# nothing yet\n\n")

        ensure_method_requirements_met(trees=[list_method_tree(tmp_path)], names_host_paths=True)

        resolve.assert_not_called()

    def test_locally_each_unmet_requirement_is_named_with_the_command_that_installs_it(self, tmp_path: Path) -> None:
        """This interpreter, read for real: the refusal names the method's root, each line and the uv command."""
        _method(directory=tmp_path, requirements=f"pydantic>=2\n{_ABSENT_PACKAGE}>=1\npydantic>=999\n")

        with pytest.raises(MethodRequirementsNotMetError) as exc_info:
            ensure_method_requirements_met(trees=[list_method_tree(tmp_path)], names_host_paths=True)

        message = exc_info.value.message
        assert message.startswith(f"The method rooted at '{tmp_path}' needs Python packages that this Python interpreter")
        assert f"line 2 '{_ABSENT_PACKAGE}>=1' ({_ABSENT_PACKAGE} is missing)" in message
        assert "line 3 'pydantic>=999' (pydantic " in message
        assert f"uv pip install --python {shlex.quote(sys.executable)} '{_ABSENT_PACKAGE}>=1' 'pydantic>=999'" in message
        items = exc_info.value.blueprint_validation_errors
        assert [item.line for item in items] == [2, 3]
        assert all(item.source == "requirements.txt" for item in items)

    def test_an_unmet_extra_names_the_distribution_it_needs(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """The distribution an extra needs is the one named: missing is `not_found`, held at a refused version `no_matching_version`."""
        installed: dict[str, tuple[str, list[str]]] = {
            "fastlib": ("1.4", ['turbo>=2; extra == "speed"', 'unrelated; extra == "other"']),
            "turbo": ("1.5", []),
        }

        def fake_distribution(distribution_name: str) -> object:
            normalized = distribution_name.lower().replace("_", "-")
            if normalized not in installed:
                raise PackageNotFoundError(distribution_name)
            version, requires = installed[normalized]
            return mocker.Mock(version=version, requires=requires)

        mocker.patch("pipelex.libraries.package_environments.distribution", side_effect=fake_distribution)
        _method(directory=tmp_path, requirements="fastlib[speed]>=1\nfastlib[other]\n")

        with pytest.raises(MethodRequirementsNotMetError) as exc_info:
            ensure_method_requirements_met(trees=[list_method_tree(tmp_path)], names_host_paths=True)

        assert [item.params for item in exc_info.value.blueprint_validation_errors] == [
            {"kind": "requirement", "name": "turbo", "reason": "no_matching_version"},
            {"kind": "requirement", "name": "unrelated", "reason": "not_found"},
        ]
        caller = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert caller.code == CoreCode.METHOD_DEPENDENCY_MISSING
        assert caller.params is not None
        assert caller.params.as_wire() == {"kind": "requirement", "name": "turbo", "reason": "no_matching_version"}

    def test_where_host_paths_may_not_be_named_the_refusal_names_none(self, mocker: MockerFixture, tmp_path: Path) -> None:
        mocker.patch(
            f"{_MODULE}.resolve_pipe_func_package_environment",
            return_value=OfferedPackageEnvironment(offer=MethodRequirementsTestData.sandbox_offer()),
        )
        _method(directory=tmp_path, requirements="pandas>=2.2\npandas>=3\npolars\n")

        with pytest.raises(MethodRequirementsNotMetError) as exc_info:
            ensure_method_requirements_met(trees=[list_method_tree(tmp_path)], names_host_paths=False)

        message = exc_info.value.message
        assert str(tmp_path) not in message
        assert message.startswith(f"The method needs Python packages that {MethodRequirementsTestData.SANDBOX_ENVIRONMENT} does not have")
        assert "line 2 'pandas>=3' (pandas 2.2.3 is there); line 3 'polars' (polars is missing)" in message
        assert [(item.source, item.line) for item in exc_info.value.blueprint_validation_errors] == [("requirements.txt", 2), ("requirements.txt", 3)]

    def test_each_tree_is_judged_once_against_the_environment_resolved_for_its_own_requirements(self, mocker: MockerFixture, tmp_path: Path) -> None:
        resolve = mocker.patch(
            f"{_MODULE}.resolve_pipe_func_package_environment",
            return_value=OfferedPackageEnvironment(offer=MethodRequirementsTestData.sandbox_offer()),
        )
        first = list_method_tree(_method(directory=tmp_path / "first", requirements="pandas\n"))
        second = list_method_tree(_method(directory=tmp_path / "second", requirements="# spreadsheets\nopenpyxl\n"))

        ensure_method_requirements_met(trees=[first, second, first], names_host_paths=True)

        resolved_for = [
            ([(line.line_number, line.text) for line in call.kwargs["requirements"]], call.kwargs["names_host_paths"])
            for call in resolve.call_args_list
        ]
        assert resolved_for == [([(1, "pandas")], True), ([(2, "openpyxl")], True)]

    def test_trees_judged_in_one_check_each_get_the_offer_stated_for_their_own_requirements(
        self, tmp_path: Path, sandbox_offering: Callable[..., PipeFuncConfig]
    ) -> None:
        """A sandbox mode building an environment per method states one for each tree, and each tree is judged against its own."""
        offers_by_requirements: dict[tuple[str, ...], PipeFuncPackageOffer] = {
            ("polars>=1",): MethodRequirementsTestData.environment_offer(snapshot_name="pipelex-env-polars", distributions={"polars": "1.2.0"}),
            ("pandas>=3",): MethodRequirementsTestData.environment_offer(snapshot_name="pipelex-env-pandas", distributions={"pandas": "3.0.1"}),
            ("pandas>=4",): MethodRequirementsTestData.environment_offer(snapshot_name="pipelex-env-stale", distributions={"pandas": "3.0.1"}),
        }
        asked: list[tuple[str, ...]] = []

        def offer_for(request: PipeFuncPackageOfferRequest) -> PipeFuncPackageOffer | PipeFuncPackageRefusal | None:
            requirement_texts = tuple(line.text for line in request.requirements)
            asked.append(requirement_texts)
            return offers_by_requirements[requirement_texts]

        sandbox_offering(offers={"daytona": offer_for})
        polars_tree = list_method_tree(_method(directory=tmp_path / "polars", requirements="polars>=1\n"))
        pandas_tree = list_method_tree(_method(directory=tmp_path / "pandas", requirements="pandas>=3\n"))
        stale_tree = list_method_tree(_method(directory=tmp_path / "stale", requirements="pandas>=4\n"))

        ensure_method_requirements_met(trees=[polars_tree, pandas_tree], names_host_paths=False)
        assert asked == [("polars>=1",), ("pandas>=3",)]

        with pytest.raises(MethodRequirementsNotMetError) as exc_info:
            ensure_method_requirements_met(trees=[pandas_tree, stale_tree], names_host_paths=False)

        message = exc_info.value.message
        assert message.startswith("The method needs Python packages that the Daytona sandbox environment 'pipelex-env-stale' does not have")
        assert "line 1 'pandas>=4' (pandas 3.0.1 is there)" in message
        assert "pipelex-env-pandas" not in message
        assert [(item.source, item.line) for item in exc_info.value.blueprint_validation_errors] == [("requirements.txt", 1)]

    def test_a_run_s_listing_asks_the_factory_once_for_a_tree_found_met_and_again_for_a_refused_one(
        self, tmp_path: Path, sandbox_offering: Callable[..., PipeFuncConfig]
    ) -> None:
        """The listing keeps the trees a check of the run found met, however the check names them, and never a refused one."""
        offers_by_requirements: dict[tuple[str, ...], PipeFuncPackageOffer] = {
            ("polars>=1",): MethodRequirementsTestData.environment_offer(snapshot_name="pipelex-env-polars", distributions={"polars": "1.2.0"}),
            ("pandas>=4",): MethodRequirementsTestData.environment_offer(snapshot_name="pipelex-env-stale", distributions={"pandas": "3.0.1"}),
        }
        asked: list[tuple[str, ...]] = []

        def offer_for(request: PipeFuncPackageOfferRequest) -> PipeFuncPackageOffer | PipeFuncPackageRefusal | None:
            requirement_texts = tuple(line.text for line in request.requirements)
            asked.append(requirement_texts)
            return offers_by_requirements[requirement_texts]

        sandbox_offering(offers={"daytona": offer_for})
        polars_tree = list_method_tree(_method(directory=tmp_path / "polars", requirements="polars>=1\n"))
        stale_tree = list_method_tree(_method(directory=tmp_path / "stale", requirements="pandas>=4\n"))
        tree_listing = MethodTreeListing()

        # A server's check, then the load of the same request, which names host paths, then a later step of that load.
        ensure_method_requirements_met(trees=[polars_tree], names_host_paths=False, tree_listing=tree_listing)
        ensure_method_requirements_met(trees=[polars_tree], names_host_paths=True, tree_listing=tree_listing)
        ensure_method_requirements_met(trees=[polars_tree], names_host_paths=True, tree_listing=tree_listing)
        assert asked == [("polars>=1",)]

        for _ in range(2):
            with pytest.raises(MethodRequirementsNotMetError):
                ensure_method_requirements_met(trees=[polars_tree, stale_tree], names_host_paths=True, tree_listing=tree_listing)
        assert asked == [("polars>=1",), ("pandas>=4",), ("pandas>=4",)]

        ensure_method_requirements_met(trees=[polars_tree], names_host_paths=True, tree_listing=MethodTreeListing())
        assert asked == [("polars>=1",), ("pandas>=4",), ("pandas>=4",), ("polars>=1",)]

    def test_a_factory_refusing_only_what_its_sandbox_needs_lets_a_false_marker_requirement_load(
        self, tmp_path: Path, sandbox_offering: Callable[..., PipeFuncConfig]
    ) -> None:
        """The factory sees every requirement, markers unevaluated, and rests a refusal only on those its sandbox needs."""
        base = MethodRequirementsTestData.sandbox_offer()
        asked: list[list[str]] = []

        def offer_or_refuse(request: PipeFuncPackageOfferRequest) -> PipeFuncPackageOffer | PipeFuncPackageRefusal | None:
            asked.append([line.text for line in request.requirements])
            needed = requirements_needed_in(requirements=request.requirements, marker_environment=base.marker_environment)
            beyond = [line.text for line in needed if line.requirement.name not in base.distributions]
            if beyond:
                return PipeFuncPackageRefusal(environment="the Daytona sandbox", reason=f"no environment holds {', '.join(beyond)}")
            return base

        sandbox_offering(offers={"daytona": offer_or_refuse})
        windows_only = list_method_tree(
            _method(directory=tmp_path / "windows-only", requirements="pandas>=2\npywin32>=306; sys_platform == 'win32'\n")
        )
        everywhere = list_method_tree(_method(directory=tmp_path / "everywhere", requirements="pandas>=2\npywin32>=306\n"))

        ensure_method_requirements_met(trees=[windows_only], names_host_paths=False)
        assert asked == [["pandas>=2", "pywin32>=306; sys_platform == 'win32'"]]

        with pytest.raises(MethodRequirementsNotMetError) as exc_info:
            ensure_method_requirements_met(trees=[everywhere], names_host_paths=False)

        assert exc_info.value.message == (
            "The method needs Python packages that the Daytona sandbox cannot offer, "
            "as its requirements.txt declares: no environment holds pywin32>=306"
        )

    def test_a_deployment_refusing_the_requirements_refuses_the_method_with_its_reason(
        self, tmp_path: Path, sandbox_offering: Callable[..., PipeFuncConfig]
    ) -> None:
        """No environment of the mode can hold them: the method is refused as its own fault, carrying the plugin's words."""
        reason = "uv explains: Because pandas<3 conflicts with the base snapshot's pandas==3.0.1, the requirements are unsatisfiable."

        def refuse(_request: PipeFuncPackageOfferRequest) -> PipeFuncPackageOffer | PipeFuncPackageRefusal | None:
            return PipeFuncPackageRefusal(environment="the Daytona sandbox", reason=reason)

        sandbox_offering(offers={"daytona": refuse})
        method_dir = _method(directory=tmp_path / "request-files", requirements="pandas<3\n")

        with pytest.raises(MethodRequirementsNotMetError) as refusal_info:
            ensure_served_method_requirements_met(library_dirs=[method_dir])
        with pytest.raises(ValidateBundleError) as verdict_info, translate_to_validate_bundle_error():
            ensure_served_method_requirements_met(library_dirs=[method_dir])

        message = refusal_info.value.message
        assert message == f"The method needs Python packages that the Daytona sandbox cannot offer, as its requirements.txt declares: {reason}"
        refusal = refusal_info.value.to_problem(view=ProblemView.CALLER)
        assert refusal.code == CoreCode.METHOD_DEPENDENCY_MISSING
        assert refusal.domain == ProblemDomain.METHOD
        # The refusal names the first requirement, as one of several unmet requirements names the first.
        assert refusal.params is not None
        assert refusal.params.as_wire() == {"kind": "requirement", "name": "pandas", "reason": "no_matching_version"}
        (item,) = verdict_info.value.validation_error_items()
        assert (item.source, item.line) == ("requirements.txt", None)
        assert item.message == f"The requirements are refused by the Daytona sandbox: {reason}"
        for disclosed in (message, str(refusal.to_wire()), str(item)):
            assert str(tmp_path) not in disclosed

    def test_a_served_method_checks_the_packages_nested_in_its_directory(self, tmp_path: Path) -> None:
        _write(directory=tmp_path, tree_path="top.mthds", content="domain = 'requirements_top'\n")
        nested = tmp_path / "packages" / "invoicing"
        _write(directory=nested, tree_path="METHODS.toml", content=_MANIFEST)
        _method(directory=nested, requirements=f"{_ABSENT_PACKAGE}\n")

        with pytest.raises(MethodRequirementsNotMetError, match=f"line 1 '{_ABSENT_PACKAGE}'"):
            ensure_served_method_requirements_met(library_dirs=[tmp_path])

    def test_a_validation_reports_the_refusal_as_located_items(self, tmp_path: Path) -> None:
        _method(directory=tmp_path, requirements=f"{_ABSENT_PACKAGE}\n")

        with pytest.raises(ValidateBundleError) as exc_info, translate_to_validate_bundle_error():
            ensure_served_method_requirements_met(library_dirs=[tmp_path])

        (item,) = exc_info.value.validation_error_items()
        assert item.category == ValidationErrorCategory.BLUEPRINT_VALIDATION
        assert item.source == "requirements.txt"
        assert item.line == 1
        assert f"The requirement '{_ABSENT_PACKAGE}' is not met" in item.message

    def test_a_served_method_refused_in_direct_mode_names_no_host_path_to_its_caller(self, tmp_path: Path) -> None:
        """This interpreter, read for real in the direct mode: the caller reads the method's lines, and no path on the host."""
        method_dir = _method(directory=tmp_path / "request-files", requirements=f"pydantic>=2\n{_ABSENT_PACKAGE}>=1\n")

        with pytest.raises(MethodRequirementsNotMetError) as refusal_info:
            ensure_served_method_requirements_met(library_dirs=[method_dir])
        with pytest.raises(ValidateBundleError) as verdict_info, translate_to_validate_bundle_error():
            ensure_served_method_requirements_met(library_dirs=[method_dir])

        # The refusal's message, which names the packages and the command that installs them, names no host path either.
        message = refusal_info.value.message
        assert message.startswith("The method needs Python packages that the Python interpreter Pipelex runs in does not have")
        assert f"line 2 '{_ABSENT_PACKAGE}>=1' ({_ABSENT_PACKAGE} is missing)" in message
        assert f"uv pip install '{_ABSENT_PACKAGE}>=1'" in message
        refusal = refusal_info.value.to_problem(view=ProblemView.CALLER)
        assert refusal.code == CoreCode.METHOD_DEPENDENCY_MISSING
        verdict_items = verdict_info.value.validation_error_items()
        assert [(item.source, item.line) for item in verdict_items] == [("requirements.txt", 2)]
        verdict = verdict_info.value.to_problem(view=ProblemView.CALLER)
        for disclosed in (message, str(refusal.to_wire()), str(verdict.to_wire()), str(verdict_items)):
            for host_path in (str(tmp_path), str(tmp_path.resolve()), sys.executable):
                assert host_path not in disclosed, host_path

    def test_a_served_method_whose_directory_cannot_be_listed_is_the_hosts_fault(self, tmp_path: Path) -> None:
        method_dir = _method(directory=tmp_path / "request-files", requirements=f"{_ABSENT_PACKAGE}\n")
        (method_dir / "linked.py").symlink_to(method_dir / "funcs" / "crunch.py")

        with pytest.raises(HostLibraryTreeError) as exc_info:
            ensure_served_method_requirements_met(library_dirs=[method_dir])

        _assert_the_host_s_fault(error=exc_info.value)

    def test_around_a_hosts_library_directories_a_refusal_is_the_hosts_fault(self, tmp_path: Path) -> None:
        _method(directory=tmp_path, requirements=f"{_ABSENT_PACKAGE}\n")

        with pytest.raises(HostLibraryRequirementsError) as exc_info, reporting_host_library_tree_faults():
            ensure_method_requirements_met(trees=[list_method_tree(tmp_path)], names_host_paths=True)

        assert isinstance(exc_info.value.__cause__, MethodRequirementsNotMetError)
        _assert_the_host_s_fault(error=exc_info.value)

    def test_a_dependency_package_is_named_by_its_address(self, tmp_path: Path) -> None:
        package_dir = _method(directory=tmp_path / "installed" / "invoicing", requirements=f"-r base.txt\n{_ABSENT_PACKAGE}\n")

        with pytest.raises(MethodRequirementsFileError) as exc_info:
            ensure_package_requirements_met(tree=list_method_tree(package_dir), package_address="github.com/pipelex-tests/invoicing")

        message = exc_info.value.message
        assert message.startswith("The method package 'github.com/pipelex-tests/invoicing' declares its packages")
        assert str(tmp_path) not in message
        assert [(item.source, item.line) for item in exc_info.value.blueprint_validation_errors] == [
            ("github.com/pipelex-tests/invoicing/requirements.txt", 1)
        ]
