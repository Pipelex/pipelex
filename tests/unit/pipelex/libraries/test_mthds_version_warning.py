from pytest_mock import MockerFixture

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
