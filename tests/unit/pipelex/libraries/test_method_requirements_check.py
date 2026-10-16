import shlex
import sys
from pathlib import Path

import pytest
from mthds.method_tree.lister import list_method_tree
from pytest_mock import MockerFixture

from pipelex.base_exceptions import INTERNAL_ERROR_PLACEHOLDER, DisclosureMode, ErrorDomain, ValidationErrorCategory
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
)
from pipelex.libraries.method_trees import reporting_host_library_tree_faults
from pipelex.libraries.package_environments import OfferedPackageEnvironment
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle_translation import translate_to_validate_bundle_error
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
        assert exc_info.value.to_error_report().error_domain == ErrorDomain.INPUT

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

    def test_the_environment_is_resolved_once_and_each_tree_judged_once(self, mocker: MockerFixture, tmp_path: Path) -> None:
        resolve = mocker.patch(
            f"{_MODULE}.resolve_pipe_func_package_environment",
            return_value=OfferedPackageEnvironment(offer=MethodRequirementsTestData.sandbox_offer()),
        )
        first = list_method_tree(_method(directory=tmp_path / "first", requirements="pandas\n"))
        second = list_method_tree(_method(directory=tmp_path / "second", requirements="openpyxl\n"))

        ensure_method_requirements_met(trees=[first, second, first], names_host_paths=True)

        resolve.assert_called_once_with(names_host_paths=True)

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

        report = exc_info.value.to_error_report()
        assert report.validation_errors is not None
        (item,) = report.validation_errors
        assert item.category == ValidationErrorCategory.BLUEPRINT_VALIDATION
        assert item.source == "requirements.txt"
        assert item.line == 1
        assert f"The requirement '{_ABSENT_PACKAGE}' is not met" in item.message

    def test_under_strict_disclosure_a_served_method_refused_in_direct_mode_names_no_host_path(self, tmp_path: Path) -> None:
        """This interpreter, read for real in the direct mode: the caller reads the method, its lines and the packages, and no path on the host."""
        method_dir = _method(directory=tmp_path / "request-files", requirements=f"pydantic>=2\n{_ABSENT_PACKAGE}>=1\n")

        with pytest.raises(MethodRequirementsNotMetError) as refusal_info:
            ensure_served_method_requirements_met(library_dirs=[method_dir])
        with pytest.raises(ValidateBundleError) as verdict_info, translate_to_validate_bundle_error():
            ensure_served_method_requirements_met(library_dirs=[method_dir])

        refusal = refusal_info.value.to_error_report().to_dict(disclosure_mode=DisclosureMode.STRICT)
        verdict = verdict_info.value.to_error_report().to_dict(disclosure_mode=DisclosureMode.STRICT)
        message = refusal["message"]
        assert message.startswith("The method needs Python packages that the Python interpreter Pipelex runs in does not have")
        assert f"line 2 '{_ABSENT_PACKAGE}>=1' ({_ABSENT_PACKAGE} is missing)" in message
        assert f"uv pip install '{_ABSENT_PACKAGE}>=1'" in message
        assert [(item["source"], item["line"]) for item in verdict["validation_errors"]] == [("requirements.txt", 2)]
        for disclosed in (str(refusal), str(verdict)):
            for host_path in (str(tmp_path), str(tmp_path.resolve()), sys.executable):
                assert host_path not in disclosed, host_path

    def test_a_served_method_whose_directory_cannot_be_listed_is_the_hosts_fault(self, tmp_path: Path) -> None:
        method_dir = _method(directory=tmp_path / "request-files", requirements=f"{_ABSENT_PACKAGE}\n")
        (method_dir / "linked.py").symlink_to(method_dir / "funcs" / "crunch.py")

        with pytest.raises(HostLibraryTreeError) as exc_info:
            ensure_served_method_requirements_met(library_dirs=[method_dir])

        report = exc_info.value.to_error_report()
        assert report.error_domain == ErrorDomain.CONFIG
        assert report.to_dict(disclosure_mode=DisclosureMode.STRICT)["message"] == INTERNAL_ERROR_PLACEHOLDER

    def test_around_a_hosts_library_directories_a_refusal_is_the_hosts_fault(self, tmp_path: Path) -> None:
        _method(directory=tmp_path, requirements=f"{_ABSENT_PACKAGE}\n")

        with pytest.raises(HostLibraryRequirementsError) as exc_info, reporting_host_library_tree_faults():
            ensure_method_requirements_met(trees=[list_method_tree(tmp_path)], names_host_paths=True)

        assert isinstance(exc_info.value.__cause__, MethodRequirementsNotMetError)
        report = exc_info.value.to_error_report()
        assert report.error_domain == ErrorDomain.CONFIG
        assert report.to_dict(disclosure_mode=DisclosureMode.STRICT)["message"] == INTERNAL_ERROR_PLACEHOLDER

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
