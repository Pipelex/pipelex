from pathlib import Path

import pytest
from mthds.package.exceptions import ManifestError
from pytest_mock import MockerFixture

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.libraries.exceptions import LibraryLoadingError
from pipelex.libraries.library_manager import LibraryManager


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
            manager._check_package_visibility(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
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
        result = manager._check_package_visibility(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
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
            manager._check_package_visibility(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
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
        result = manager._check_package_visibility(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
            blueprints=[blueprint],
            mthds_paths=[dummy_path],
        )
        assert result is None
