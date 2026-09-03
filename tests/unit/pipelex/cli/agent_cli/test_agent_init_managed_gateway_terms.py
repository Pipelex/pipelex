"""`pipelex-agent init` records service-terms acceptance for any managed gateway backend.

The agent flow takes `accept_gateway_terms` as an explicit instruction. Asked the gateway-only way,
that instruction was silently dropped for a request naming only the manifold service — and since
the same flow marks inference setup complete unconditionally, the next inference boot refused with
`GatewayTermsNotAcceptedError` on a configuration the agent had been told was finished.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pipelex.cli.agent_cli.commands.init_cmd import _configure_backends  # pyright: ignore[reportPrivateUsage]
from pipelex.cogt.model_backends.backend import PipelexBackend
from pipelex.kit.paths import get_kit_configs_dir

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _backends_files(tmp_path: Path) -> tuple[Path, Path]:
    """The user's backends.toml (a copy of the kit template) and the template itself."""
    template = Path(str(get_kit_configs_dir())) / "inference" / "backends.toml"
    user_file = tmp_path / "backends.toml"
    shutil.copy2(template, user_file)
    return user_file, template


class TestAgentInitTermsForAnyManagedGateway:
    def test_a_manifold_only_request_persists_the_acceptance_it_was_given(self, tmp_path: Path, mocker: MockerFixture) -> None:
        user_file, template = _backends_files(tmp_path)
        mocker.patch("pipelex.cli.agent_cli.commands.init_cmd.config_manager", mocker.MagicMock(global_config_dir=tmp_path))
        recorded = mocker.patch("pipelex.cli.agent_cli.commands.init_cmd.update_service_terms_acceptance")

        config: dict[str, Any] = {"backends": [PipelexBackend.MANIFOLD], "accept_gateway_terms": True}
        _configure_backends(config=config, backends_toml_path=user_file, template_backends_path=template)

        recorded.assert_called_once()
        assert recorded.call_args.kwargs["accepted"] is True

    def test_a_byok_only_request_records_nothing(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """The guard: no managed backend means no terms question, whatever the config carries."""
        user_file, template = _backends_files(tmp_path)
        mocker.patch("pipelex.cli.agent_cli.commands.init_cmd.config_manager", mocker.MagicMock(global_config_dir=tmp_path))
        recorded = mocker.patch("pipelex.cli.agent_cli.commands.init_cmd.update_service_terms_acceptance")

        config: dict[str, Any] = {"backends": ["anthropic"], "accept_gateway_terms": True}
        _configure_backends(config=config, backends_toml_path=user_file, template_backends_path=template)

        recorded.assert_not_called()
