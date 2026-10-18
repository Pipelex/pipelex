from pathlib import Path

import pytest
from mthds.package.manifest.schema import MethodsManifest
from mthds.protocol.problem.registry import CoreCode
from pytest_mock import MockerFixture

from pipelex.errors.problem import ProblemView
from pipelex.libraries.library_manager import LibraryManager
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle_translation import translate_to_validate_bundle_error
from tests.unit.pipelex.libraries.test_data import PackageVisibilityTestData


def _refused_items(*, mocker: MockerFixture, tmp_path: Path, bundles: dict[str, str]) -> list[tuple[str, str | None, dict[str, object] | None]]:
    """The code, file and parameters of each item refusing the bundles of a package whose METHODS.toml exports nothing."""
    manifest = MethodsManifest(address=PackageVisibilityTestData.PACKAGE_ADDRESS, version="1.0.0", description="A package exporting nothing")
    mocker.patch("pipelex.libraries.library_manager.find_package_manifest", return_value=manifest)
    blueprints = [MthdsParser.make_pipelex_bundle_blueprint(mthds_content=content, mthds_source=source) for source, content in bundles.items()]
    first_path = tmp_path / next(iter(bundles))
    first_path.touch()

    with pytest.raises(ValidateBundleError) as exc_info, translate_to_validate_bundle_error():
        LibraryManager()._check_package_visibility(  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
            blueprints=blueprints,
            mthds_paths=[first_path],
        )

    items = exc_info.value.to_problem(view=ProblemView.CALLER).errors or []
    return [(item.code, item.location.file if item.location else None, item.params.as_wire() if item.params else None) for item in items]


class TestPackageVisibilityRefusals:
    def test_a_pipe_another_domain_does_not_export_is_refused_naming_the_pipe_and_the_package(self, mocker: MockerFixture, tmp_path: Path) -> None:
        items = _refused_items(
            mocker=mocker,
            tmp_path=tmp_path,
            bundles={"scoring.mthds": PackageVisibilityTestData.SCORING_MTHDS, "legal.mthds": PackageVisibilityTestData.LEGAL_MTHDS},
        )

        assert items == [
            (
                CoreCode.METHOD_PIPE_NOT_EXPORTED,
                "legal.mthds",
                {"pipe": PackageVisibilityTestData.UNEXPORTED_PIPE_REF, "package": PackageVisibilityTestData.PACKAGE_ADDRESS},
            )
        ]

    def test_a_reserved_domain_in_a_package_is_a_name_conflict_never_an_export_refusal(self, mocker: MockerFixture, tmp_path: Path) -> None:
        items = _refused_items(
            mocker=mocker,
            tmp_path=tmp_path,
            bundles={
                "native.mthds": PackageVisibilityTestData.RESERVED_DOMAIN_MTHDS,
                "scoring.mthds": PackageVisibilityTestData.SCORING_MTHDS,
                "legal.mthds": PackageVisibilityTestData.LEGAL_MTHDS,
            },
        )

        assert items == [(CoreCode.METHOD_NAME_CONFLICT, "native.mthds", {"name": "native", "conflict": "reserved_domain"})]
