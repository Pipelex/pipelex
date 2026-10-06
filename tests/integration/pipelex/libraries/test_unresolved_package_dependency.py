"""A bundle's reference to a method package that cannot be resolved is a verdict item, never a no-verdict fault.

A consumer calls a pipe of another package by its address (`<address>->domain.code`). When no installed copy matches
and the package cannot be fetched, the load is refused with one `unresolved_package_dependency` item per address,
located on the first pipe that names it, with the reference as written in `missing_pipe_code`. A failure of the host's
own store stays the fault it is, and so does a host library directory's unresolvable reference.

The packages are invented; every test isolates the installed store, and none reaches the network.
"""

import json
from pathlib import Path

import pytest
from mthds.package.manifest.parser import parse_methods_toml
from pytest_mock import MockerFixture

from pipelex.base_exceptions import DisclosureMode, ValidationErrorCategory, ValidationErrorItem
from pipelex.interpreter_hub import get_library_manager
from pipelex.libraries.exceptions import LibraryLoadingError
from pipelex.methods.exceptions import MethodInstallError, MethodPackageNotFoundError
from pipelex.methods.fetching import FetchedMethodPackage, fetch_method_package
from pipelex.methods.method_ref import MethodRef, parse_method_ref
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.execution_seams import acquire_library
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.validation_error_types import PipeValidationErrorType
from tests.integration.pipelex.libraries.installed_packages import isolate_installed_methods, write_consumer
from tests.integration.pipelex.libraries.test_data import ProbePackageTestData

PROBE_REFERENCE = f"{ProbePackageTestData.DEP_ALIAS}->probe_dep.entry"
GITLAB_REFERENCE = "gitlab.com/someone/pkg->other_dep.entry"

TWO_REFERENCES_BUNDLE = f"""domain      = "probe_consumer"
description = "A consumer naming two packages, the first one twice"

[pipe.go]
type        = "PipeSequence"
description = "Call both packages"
inputs      = {{ data = "Text" }}
output      = "Text"
steps       = [
  {{ pipe = "{PROBE_REFERENCE}", result = "first" }},
  {{ pipe = "{GITLAB_REFERENCE}", result = "second" }},
]

[pipe.again]
type        = "PipeSequence"
description = "Call the first package again"
inputs      = {{ data = "Text" }}
output      = "Text"
steps       = [{{ pipe = "{PROBE_REFERENCE}", result = "out" }}]
"""


def _enable_fetch_on_miss(*, mocker: MockerFixture) -> None:
    mocker.patch("pipelex.methods.fetch_on_miss.is_method_fetch_on_miss_enabled", return_value=True)


async def _verdict_for(*, mthds_content: str) -> ValidateBundleError:
    with pytest.raises(ValidateBundleError) as exc_info:
        await validate_bundle(mthds_contents=[mthds_content])
    return exc_info.value


def _package_items(verdict: ValidateBundleError) -> list[ValidationErrorItem]:
    items = verdict.to_error_report().validation_errors or []
    package_items = [item for item in items if item.error_type == PipeValidationErrorType.UNRESOLVED_PACKAGE_DEPENDENCY]
    assert len(package_items) == len(items), f"Only package items were expected, got {[(item.category, item.error_type) for item in items]}"
    return package_items


def _strict_dump(verdict: ValidateBundleError) -> str:
    return json.dumps(verdict.to_error_report().to_dict(disclosure_mode=DisclosureMode.STRICT))


def _assert_located_on_go(item: ValidationErrorItem, *, reference: str) -> None:
    assert item.category == ValidationErrorCategory.PIPE_VALIDATION
    assert item.pipe_code == "go"
    assert item.domain_code == "probe_consumer"
    assert item.missing_pipe_code == reference
    assert item.field_path == "pipe.go.steps[0].pipe"


@pytest.mark.asyncio(loop_scope="class")
class TestUnresolvedPackageDependency:
    async def test_a_package_not_installed_with_fetching_off_is_one_item(self, tmp_path: Path, mocker: MockerFixture) -> None:
        isolate_installed_methods(mocker=mocker, root=tmp_path)
        fetch_mock = mocker.patch("pipelex.methods.fetch_on_miss.fetch_method_package")

        verdict = await _verdict_for(mthds_content=ProbePackageTestData.CONSUMER_BUNDLE)

        (item,) = _package_items(verdict)
        _assert_located_on_go(item, reference=PROBE_REFERENCE)
        assert ProbePackageTestData.DEP_ALIAS in item.message
        assert "fetch-on-miss is disabled" in item.message
        fetch_mock.assert_not_called()

    async def test_the_library_load_carries_the_item(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """The refusal is raised by the load itself, so every surface that translates a load gets it."""
        isolate_installed_methods(mocker=mocker, root=tmp_path)
        library_manager = get_library_manager()
        library_id, _library = library_manager.open_library()
        try:
            blueprint = MthdsParser.make_pipelex_bundle_blueprint(mthds_content=ProbePackageTestData.CONSUMER_BUNDLE)
            with pytest.raises(LibraryLoadingError) as exc_info:
                library_manager.load_from_blueprints(library_id=library_id, blueprints=[blueprint])
        finally:
            library_manager.teardown(library_id=library_id)
        items = exc_info.value.pipe_concept_validation_errors or []
        assert [(item.error_type, item.pipe_code, item.missing_pipe_code) for item in items] == [
            (PipeValidationErrorType.UNRESOLVED_PACKAGE_DEPENDENCY, "go", PROBE_REFERENCE)
        ]

    async def test_an_address_no_runtime_can_fetch_is_one_item(self, tmp_path: Path, mocker: MockerFixture) -> None:
        isolate_installed_methods(mocker=mocker, root=tmp_path)
        _enable_fetch_on_miss(mocker=mocker)

        verdict = await _verdict_for(mthds_content=ProbePackageTestData.consumer_calling(pipe_ref=GITLAB_REFERENCE))

        (item,) = _package_items(verdict)
        _assert_located_on_go(item, reference=GITLAB_REFERENCE)
        assert "gitlab.com/someone/pkg" in item.message
        assert "github.com/" in item.message

    async def test_a_failed_clone_is_one_item_naming_no_host_path(self, tmp_path: Path, mocker: MockerFixture) -> None:
        isolate_installed_methods(mocker=mocker, root=tmp_path)
        _enable_fetch_on_miss(mocker=mocker)
        unreachable_url = "file:///nonexistent-zz9/no-such-repo-zz9.git"

        def _fetch_from_nowhere(*, ref: MethodRef, dest_dir: Path, refuse_structures: bool) -> FetchedMethodPackage:
            return fetch_method_package(ref=ref, dest_dir=dest_dir, clone_url=unreachable_url, refuse_structures=refuse_structures)

        mocker.patch("pipelex.methods.fetch_on_miss.fetch_method_package", side_effect=_fetch_from_nowhere)

        verdict = await _verdict_for(mthds_content=ProbePackageTestData.CONSUMER_BUNDLE)

        (item,) = _package_items(verdict)
        _assert_located_on_go(item, reference=PROBE_REFERENCE)
        # Git's own explanation stays; its progress line naming the runner's clone directory does not.
        assert "does not appear to be a git repository" in item.message
        strict_dump = _strict_dump(verdict)
        assert "does not appear to be a git repository" in strict_dump
        assert "Cloning into" not in strict_dump
        assert "mthds_fetch_on_miss_" not in strict_dump

    async def test_a_repository_without_the_package_is_one_item(self, tmp_path: Path, mocker: MockerFixture) -> None:
        isolate_installed_methods(mocker=mocker, root=tmp_path)
        _enable_fetch_on_miss(mocker=mocker)
        mocker.patch(
            "pipelex.methods.fetch_on_miss.fetch_method_package",
            side_effect=MethodPackageNotFoundError("No package in 'github.com/invented/probe-lib' matches 'probe'; the repository holds: other."),
        )

        verdict = await _verdict_for(mthds_content=ProbePackageTestData.CONSUMER_BUNDLE)

        (item,) = _package_items(verdict)
        _assert_located_on_go(item, reference=PROBE_REFERENCE)
        assert "the repository holds: other" in item.message

    async def test_every_unresolved_address_is_one_item_on_the_first_pipe_naming_it(self, tmp_path: Path, mocker: MockerFixture) -> None:
        isolate_installed_methods(mocker=mocker, root=tmp_path)

        verdict = await _verdict_for(mthds_content=TWO_REFERENCES_BUNDLE)

        items = _package_items(verdict)
        assert [(item.pipe_code, item.missing_pipe_code, item.field_path) for item in items] == [
            ("go", PROBE_REFERENCE, "pipe.go.steps[0].pipe"),
            ("go", GITLAB_REFERENCE, "pipe.go.steps[1].pipe"),
        ]

    async def test_an_install_failure_stays_the_host_s_fault(self, tmp_path: Path, mocker: MockerFixture) -> None:
        isolate_installed_methods(mocker=mocker, root=tmp_path)
        _enable_fetch_on_miss(mocker=mocker)
        package_dir = tmp_path / "fetched"
        package_dir.mkdir()
        (package_dir / "METHODS.toml").write_text(ProbePackageTestData.MANIFEST_EXPORTING_EVERYTHING, encoding="utf-8")
        (package_dir / "probe_dep.mthds").write_text(ProbePackageTestData.DEP_BUNDLE, encoding="utf-8")
        fetched = FetchedMethodPackage(
            ref=parse_method_ref(ProbePackageTestData.DEP_ALIAS),
            full_address=ProbePackageTestData.DEP_ALIAS,
            commit_sha="c" * 40,
            clone_dir=tmp_path,
            package_dir=package_dir,
            manifest=parse_methods_toml(ProbePackageTestData.MANIFEST_EXPORTING_EVERYTHING),
        )
        mocker.patch("pipelex.methods.fetch_on_miss.fetch_method_package", return_value=fetched)
        mocker.patch("pipelex.methods.fetch_on_miss.install_method_package", side_effect=MethodInstallError("The install target is occupied."))

        with pytest.raises(MethodInstallError):
            await validate_bundle(mthds_contents=[ProbePackageTestData.CONSUMER_BUNDLE])

    async def test_a_host_library_directory_s_unresolved_reference_is_no_verdict(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """A host's own directories load untranslated: their refusal is the host's fault, never the caller's verdict."""
        isolate_installed_methods(mocker=mocker, root=tmp_path)
        host_dir = tmp_path / "host-library"
        host_dir.mkdir()
        write_consumer(root=host_dir, bundles={"consumer.mthds": ProbePackageTestData.CONSUMER_BUNDLE})

        with pytest.raises(LibraryLoadingError) as exc_info:
            acquire_library(library_id="", library_dirs=[str(host_dir)])

        assert not isinstance(exc_info.value, ValidateBundleError)
        assert exc_info.value.to_error_report().error_domain is None
