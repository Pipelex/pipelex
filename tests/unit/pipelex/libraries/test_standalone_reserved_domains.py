from pathlib import Path

import pytest
from mthds.package.exceptions import ManifestError
from mthds.protocol.problem.registry import CoreCode
from pytest_mock import MockerFixture

from pipelex.errors.problem import ProblemView
from pipelex.libraries.exceptions import LibraryLoadingError
from pipelex.libraries.library_manager import LibraryManager
from pipelex.mthds_parsing.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle_translation import translate_to_validate_bundle_error


class TestStandaloneReservedDomains:
    """Tests that reserved domain enforcement applies to standalone bundles (no manifest)."""

    @pytest.mark.parametrize(
        "reserved_domain",
        [
            "native",
            "mthds",
            "pipelex",
        ],
    )
    def test_standalone_bundle_reserved_domain_raises(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
        reserved_domain: str,
    ) -> None:
        """Loading a standalone bundle with a reserved domain should raise LibraryLoadingError."""
        # Patch find_package_manifest to return None (no manifest = standalone)
        mocker.patch("pipelex.libraries.library_manager.find_package_manifest", return_value=None)

        blueprint = PipelexBundleBlueprint(
            domain=reserved_domain,
            source="test_standalone.mthds",
        )

        dummy_path = tmp_path / "test_standalone.mthds"
        dummy_path.touch()

        manager = LibraryManager()
        with pytest.raises(LibraryLoadingError, match="Reserved domain violations"):
            manager._check_package_visibility(  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
                blueprints=[blueprint],
                mthds_paths=[dummy_path],
            )

    def test_standalone_bundle_non_reserved_domain_passes(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Loading a standalone bundle with a non-reserved domain should not raise."""
        mocker.patch("pipelex.libraries.library_manager.find_package_manifest", return_value=None)

        blueprint = PipelexBundleBlueprint(
            domain="legal",
            source="test_standalone.mthds",
        )

        dummy_path = tmp_path / "test_standalone.mthds"
        dummy_path.touch()

        manager = LibraryManager()
        result = manager._check_package_visibility(  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
            blueprints=[blueprint],
            mthds_paths=[dummy_path],
        )
        assert result is None

    @pytest.mark.parametrize(
        "reserved_domain",
        [
            "native",
            "mthds",
            "pipelex",
        ],
    )
    def test_manifest_error_still_checks_reserved_domains(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
        reserved_domain: str,
    ) -> None:
        """ManifestError should not bypass reserved domain validation."""
        mocker.patch(
            "pipelex.libraries.library_manager.find_package_manifest",
            side_effect=ManifestError(message="corrupt METHODS.toml"),
        )

        blueprint = PipelexBundleBlueprint(
            domain=reserved_domain,
            source="test_bad_manifest.mthds",
        )

        dummy_path = tmp_path / "test_bad_manifest.mthds"
        dummy_path.touch()

        manager = LibraryManager()
        with pytest.raises(LibraryLoadingError, match="Reserved domain violations"):
            manager._check_package_visibility(  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
                blueprints=[blueprint],
                mthds_paths=[dummy_path],
            )

    def test_manifest_error_non_reserved_domain_passes(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """ManifestError with a non-reserved domain should return None without raising."""
        mocker.patch(
            "pipelex.libraries.library_manager.find_package_manifest",
            side_effect=ManifestError(message="corrupt METHODS.toml"),
        )

        blueprint = PipelexBundleBlueprint(
            domain="legal",
            source="test_bad_manifest.mthds",
        )

        dummy_path = tmp_path / "test_bad_manifest.mthds"
        dummy_path.touch()

        manager = LibraryManager()
        result = manager._check_package_visibility(  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
            blueprints=[blueprint],
            mthds_paths=[dummy_path],
        )
        assert result is None

    def test_two_bundles_declaring_one_reserved_domain_are_each_located_on_their_own_file(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """One item per bundle, each on its own file, never every item on the last bundle of the domain."""
        mocker.patch("pipelex.libraries.library_manager.find_package_manifest", return_value=None)
        blueprints = [PipelexBundleBlueprint(domain="native", source=source) for source in ("first.mthds", "second.mthds")]
        dummy_path = tmp_path / "first.mthds"
        dummy_path.touch()

        manager = LibraryManager()
        with pytest.raises(ValidateBundleError) as exc_info, translate_to_validate_bundle_error():
            manager._check_package_visibility(  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
                blueprints=blueprints,
                mthds_paths=[dummy_path],
            )

        items = exc_info.value.to_problem(view=ProblemView.CALLER).errors or []
        assert [(item.code, item.location.file if item.location else None) for item in items] == [
            (CoreCode.METHOD_NAME_CONFLICT, "first.mthds"),
            (CoreCode.METHOD_NAME_CONFLICT, "second.mthds"),
        ]
        assert [item.params.as_wire() if item.params else None for item in items] == [
            {"name": "native", "conflict": "reserved_domain"},
            {"name": "native", "conflict": "reserved_domain"},
        ]
