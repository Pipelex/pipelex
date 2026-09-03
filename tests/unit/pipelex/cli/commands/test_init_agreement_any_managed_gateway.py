"""`pipelex init agreement` is the recovery path, and it has to cover every managed gateway.

The boot puts an installation behind service-terms acceptance as soon as *any* managed gateway
backend is enabled. This command is the human CLI's only way to record that acceptance after the
fact, so a question narrower than the boot's leaves a manifold-only installation with no supported
step that unblocks it — the command reports there is nothing to accept while the boot refuses to
start for want of exactly that.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelex.cli.commands.init.command import _init_agreement  # pyright: ignore[reportPrivateUsage]
from pipelex.cogt.model_backends.backend import PipelexBackend

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

MANIFOLD_ONLY_SECTIONS = {PipelexBackend.MANIFOLD: "manifold_model_specs"}


class TestInitAgreementCoversEveryManagedGateway:
    def test_a_manifold_only_installation_is_prompted_rather_than_told_nothing_is_needed(self, mocker: MockerFixture) -> None:
        """The dead end this closes: the terms panel must appear, and acceptance must persist."""
        mocker.patch("pipelex.cli.commands.init.command.enabled_managed_gateway_sections", return_value=MANIFOLD_ONLY_SECTIONS)
        mocker.patch("pipelex.cli.commands.init.command.load_pipelex_service_config_if_exists", return_value=None)
        mocker.patch("rich.prompt.Confirm.ask", return_value=True)
        recorded = mocker.patch("pipelex.cli.commands.init.command.update_service_terms_acceptance")

        _init_agreement(console=mocker.MagicMock())

        recorded.assert_called_once()
        assert recorded.call_args.kwargs["accepted"] is True

    def test_no_managed_gateway_at_all_still_reports_nothing_to_accept(self, mocker: MockerFixture) -> None:
        """The guard: a BYOK-only installation must keep its early exit, and prompt for nothing."""
        mocker.patch("pipelex.cli.commands.init.command.enabled_managed_gateway_sections", return_value={})
        recorded = mocker.patch("pipelex.cli.commands.init.command.update_service_terms_acceptance")
        asked = mocker.patch("rich.prompt.Confirm.ask")

        _init_agreement(console=mocker.MagicMock())

        recorded.assert_not_called()
        asked.assert_not_called()
