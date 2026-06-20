"""Unit tests for the ``pipelex-temporal setup-namespace`` CLI command.

The command wraps ``ensure_required_search_attributes_registered`` with a
copy-paste-ready dry-run output and a permission-denied fallback runbook so
operators whose worker API key lacks ``OperatorService.AddSearchAttributes``
permission still get the exact ``temporal`` / ``tcld`` invocation they need
the namespace admin to run on their behalf.
"""

from typing import Any

import pytest
import typer
from pytest_mock import MockerFixture

from pipelex.temporal.setup_namespace_cmd import setup_namespace_cmd
from pipelex.temporal.tprl.namespace_check import RegistrationFailure


class TestSetupTemporalNamespaceCmd:
    @pytest.fixture
    def patch_pipelex_lifecycle(self, mocker: MockerFixture) -> None:
        """Skip the heavy ``make_pipelex_for_cli`` / ``teardown`` lifecycle.

        The CLI command's interaction with the Pipelex boot is not what this
        test exercises — we care about the search-attribute registration logic
        and the dry-run / permission-denied branches.
        """
        mocker.patch("pipelex.temporal.setup_namespace_cmd.make_pipelex_for_cli")
        mocker.patch("pipelex.temporal.setup_namespace_cmd.Pipelex.teardown_if_needed")

    def _patch_config(
        self,
        mocker: MockerFixture,
        *,
        enabled: bool = True,
        attributes: list[str] | None = None,
        namespace: str = "default",
        selected_server: str = "local",
    ) -> Any:
        """Build a fake config root and patch the module-level ``get_config``."""
        config_root = mocker.MagicMock()
        config_root.temporal.search_attributes.enabled = enabled
        config_root.temporal.search_attributes.attributes = (
            attributes if attributes is not None else ["PipeCode", "PipelineRunId", "SessionId", "UserId", "DomainCode"]
        )
        config_root.temporal.temporal_config.selected_server = selected_server
        server_config = mocker.MagicMock()
        server_config.namespace = namespace
        config_root.temporal.temporal_config.temporal_server_configs = {selected_server: server_config}
        mocker.patch("pipelex.temporal.setup_namespace_cmd.get_config", return_value=config_root)
        return config_root

    @pytest.mark.usefixtures("patch_pipelex_lifecycle")
    def test_dry_run_prints_temporal_cli_command_without_connecting(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        self._patch_config(mocker)
        connect_mock = mocker.patch(
            "pipelex.temporal.temporal_connect.connect_to_temporal_selected_server",
            new=mocker.AsyncMock(),
        )
        register_mock = mocker.patch(
            "pipelex.temporal.tprl.namespace_check.ensure_required_search_attributes_registered",
            new=mocker.AsyncMock(),
        )

        setup_namespace_cmd(dry_run=True, server=None)

        captured = capsys.readouterr().out
        assert "temporal operator search-attribute create" in captured
        assert "--namespace default" in captured
        for name in ("PipeCode", "PipelineRunId", "SessionId", "UserId", "DomainCode"):
            assert f"--name {name} --type Keyword" in captured
        assert "tcld namespace search-attributes add" in captured
        connect_mock.assert_not_called()
        register_mock.assert_not_called()

    @pytest.mark.usefixtures("patch_pipelex_lifecycle")
    def test_happy_path_connects_and_registers(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        self._patch_config(mocker)
        fake_client = mocker.MagicMock()
        connect_mock = mocker.patch(
            "pipelex.temporal.temporal_connect.connect_to_temporal_selected_server",
            new=mocker.AsyncMock(return_value=fake_client),
        )
        # Helper now returns the tuple of newly-registered names; two of the five
        # attributes were missing and have just been added.
        register_mock = mocker.patch(
            "pipelex.temporal.tprl.namespace_check.ensure_required_search_attributes_registered",
            new=mocker.AsyncMock(return_value=("SessionId", "DomainCode")),
        )

        setup_namespace_cmd(dry_run=False, server=None)

        connect_mock.assert_awaited_once()
        register_mock.assert_awaited_once()
        kwargs = register_mock.call_args.kwargs
        assert kwargs["temporal_client"] is fake_client
        assert kwargs["namespace"] == "default"
        assert kwargs["configured_attributes"] == ["PipeCode", "PipelineRunId", "SessionId", "UserId", "DomainCode"]
        # Success message names the actual delta, not the configured set size.
        captured_out = capsys.readouterr().out
        assert "Registered 2 new" in captured_out
        assert "SessionId" in captured_out
        assert "DomainCode" in captured_out

    @pytest.mark.usefixtures("patch_pipelex_lifecycle")
    def test_idempotent_no_op_reports_already_registered(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """When every configured attribute is already registered, the helper
        returns an empty tuple. The CLI must report the idempotent outcome
        clearly instead of falsely claiming it just registered the full set
        (the misleading "Registered N" that operators saw before).
        """
        self._patch_config(mocker)
        mocker.patch(
            "pipelex.temporal.temporal_connect.connect_to_temporal_selected_server",
            new=mocker.AsyncMock(return_value=mocker.MagicMock()),
        )
        mocker.patch(
            "pipelex.temporal.tprl.namespace_check.ensure_required_search_attributes_registered",
            new=mocker.AsyncMock(return_value=()),
        )

        setup_namespace_cmd(dry_run=False, server=None)

        out = capsys.readouterr().out
        assert "already registered" in out
        assert "All 5" in out

    @pytest.mark.usefixtures("patch_pipelex_lifecycle")
    def test_permission_denied_prints_fallback_runbook_and_exits(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        self._patch_config(mocker)
        failure = RegistrationFailure(
            namespace="default",
            missing=("SessionId", "UserId"),
            rpc_error_message="permission denied",
        )
        mocker.patch(
            "pipelex.temporal.temporal_connect.connect_to_temporal_selected_server",
            new=mocker.AsyncMock(return_value=mocker.MagicMock()),
        )
        mocker.patch(
            "pipelex.temporal.tprl.namespace_check.ensure_required_search_attributes_registered",
            new=mocker.AsyncMock(return_value=failure),
        )

        with pytest.raises(typer.Exit) as exc_info:
            setup_namespace_cmd(dry_run=False, server=None)

        assert exc_info.value.exit_code == 1
        err = capsys.readouterr().err
        # The error stream carries the actionable runbook.
        assert "Permission denied" in err
        assert "--name SessionId --type Keyword" in err
        assert "--name UserId --type Keyword" in err
        assert "tcld namespace search-attributes add" in err
        assert "permission denied" in err  # the underlying rpc message is surfaced

    @pytest.mark.usefixtures("patch_pipelex_lifecycle")
    def test_disabled_config_short_circuits_with_message(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        self._patch_config(mocker, enabled=False, attributes=[])
        connect_mock = mocker.patch(
            "pipelex.temporal.temporal_connect.connect_to_temporal_selected_server",
            new=mocker.AsyncMock(),
        )

        setup_namespace_cmd(dry_run=False, server=None)

        connect_mock.assert_not_called()
        assert "enabled = false" in capsys.readouterr().err

    @pytest.mark.usefixtures("patch_pipelex_lifecycle")
    def test_rpc_error_other_than_permission_denied_is_framed_for_operator(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """When the namespace doesn't exist or the control plane is down, the
        helper propagates a raw ``RPCError``. The CLI must catch it and frame
        a friendly message instead of leaking a traceback.
        """
        from temporalio.service import RPCError, RPCStatusCode  # noqa: PLC0415

        self._patch_config(mocker)
        mocker.patch(
            "pipelex.temporal.temporal_connect.connect_to_temporal_selected_server",
            new=mocker.AsyncMock(return_value=mocker.MagicMock()),
        )
        mocker.patch(
            "pipelex.temporal.tprl.namespace_check.ensure_required_search_attributes_registered",
            new=mocker.AsyncMock(side_effect=RPCError("namespace not found", RPCStatusCode.NOT_FOUND, raw_grpc_status=b"")),
        )

        with pytest.raises(typer.Exit) as exc_info:
            setup_namespace_cmd(dry_run=False, server=None)

        assert exc_info.value.exit_code == 1
        err = capsys.readouterr().err
        assert "Could not reach Temporal namespace" in err
        assert "namespace not found" in err

    @pytest.mark.usefixtures("patch_pipelex_lifecycle")
    def test_unknown_server_profile_exits_with_helpful_message(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        self._patch_config(mocker, selected_server="local")
        mocker.patch(
            "pipelex.temporal.temporal_connect.connect_to_temporal_selected_server",
            new=mocker.AsyncMock(),
        )

        with pytest.raises(typer.Exit) as exc_info:
            setup_namespace_cmd(dry_run=False, server="does_not_exist")

        assert exc_info.value.exit_code == 1
        err = capsys.readouterr().err
        assert "does_not_exist" in err
        assert "Known:" in err
