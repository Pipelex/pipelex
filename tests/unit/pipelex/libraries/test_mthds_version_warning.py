from pathlib import Path

from mthds.package.dependency_resolver import ResolvedDependency
from mthds.package.manifest.schema import MethodsManifest
from pytest_mock import MockerFixture

from pipelex.libraries.library_factory import LibraryFactory
from pipelex.libraries.library_manager import LibraryManager


class TestMthdsVersionWarning:
    """Tests for _warn_if_mthds_version_unsatisfied runtime warning."""

    def test_warning_emitted_when_version_unsatisfied(self, mocker: MockerFixture) -> None:
        """Warning emitted when current MTHDS standard version does not satisfy the constraint."""
        mocker.patch("pipelex.libraries.library_manager.MTHDS_STANDARD_VERSION", "1.0.0")
        mock_log = mocker.patch("pipelex.libraries.library_manager.log")

        manager = LibraryManager()
        manager._warn_if_mthds_version_unsatisfied(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
            mthds_version_constraint="^2.0.0",
            package_address="github.com/org/pkg",
        )

        mock_log.warning.assert_called_once()
        warning_msg = mock_log.warning.call_args[0][0]
        assert "github.com/org/pkg" in warning_msg
        assert "^2.0.0" in warning_msg
        assert "1.0.0" in warning_msg

    def test_no_warning_when_version_satisfied(self, mocker: MockerFixture) -> None:
        """No warning emitted when current MTHDS standard version satisfies the constraint."""
        mocker.patch("pipelex.libraries.library_manager.MTHDS_STANDARD_VERSION", "1.0.0")
        mock_log = mocker.patch("pipelex.libraries.library_manager.log")

        manager = LibraryManager()
        manager._warn_if_mthds_version_unsatisfied(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
            mthds_version_constraint="^1.0.0",
            package_address="github.com/org/pkg",
        )

        mock_log.warning.assert_not_called()

    def test_warning_on_unparseable_constraint(self, mocker: MockerFixture) -> None:
        """Warning emitted when the constraint is not parseable by the semver engine."""
        mock_log = mocker.patch("pipelex.libraries.library_manager.log")

        manager = LibraryManager()
        manager._warn_if_mthds_version_unsatisfied(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
            mthds_version_constraint=">>>garbage",
            package_address="github.com/org/pkg",
        )

        mock_log.warning.assert_called_once()
        warning_msg = mock_log.warning.call_args[0][0]
        assert "Could not parse" in warning_msg

    def test_warning_emitted_for_dependency_mthds_version(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """Warning emitted when a dependency manifest has unsatisfied mthds_version."""
        mocker.patch("pipelex.libraries.library_manager.MTHDS_STANDARD_VERSION", "1.0.0")
        mock_log = mocker.patch("pipelex.libraries.library_manager.log")

        # Create a minimal .mthds file so the interpreter can parse it
        mthds_file = tmp_path / "dep.mthds"
        mthds_file.write_text('domain = "dep_domain"\n')

        dep_manifest = MethodsManifest(
            address="github.com/org/dep-pkg",
            version="1.0.0",
            description="A dependency",
            mthds_version="^2.0.0",
        )
        resolved_dep = ResolvedDependency(
            alias="dep_alias",
            address="github.com/org/dep-pkg",
            manifest=dep_manifest,
            package_root=tmp_path,
            mthds_files=[mthds_file],
            exported_pipe_codes=None,
        )

        manager = LibraryManager()
        library = LibraryFactory.make_empty()

        manager._load_single_dependency(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
            library=library,
            resolved_dep=resolved_dep,
        )

        # Verify a version warning was emitted for the dependency address
        warning_calls = [call_args[0][0] for call_args in mock_log.warning.call_args_list]
        dep_version_warnings = [msg for msg in warning_calls if "github.com/org/dep-pkg" in msg and "^2.0.0" in msg]
        assert len(dep_version_warnings) >= 1
