"""`pipelex-agent init` takes `"execution": "hosted"`: it writes the setting, configures no backend, and reports it."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
import typer
from typer.testing import CliRunner

from pipelex.cli.agent_cli.commands.init_cmd import agent_init_cmd
from pipelex.cli.commands.init.setup_path import read_run_execution
from pipelex.hosted.run_config import RunExecution
from pipelex.kit.paths import get_kit_configs_dir
from tests.helpers.pipelex_api_key_env import isolate_pipelex_api_key

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

_app = typer.Typer()
_app.command()(agent_init_cmd)


@pytest.fixture
def target_dir(tmp_path: Path, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The project's `.pipelex/`, with the credentials file in a home of the test's own and no key in the environment."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    config_manager = mocker.MagicMock()
    config_manager.project_root = project_root
    config_manager.global_config_dir = tmp_path / "home"
    mocker.patch("pipelex.cli.agent_cli.commands.init_cmd.config_manager", config_manager)
    mocker.patch("pipelex.cli.commands.init.credentials.config_manager", config_manager)
    isolate_pipelex_api_key(monkeypatch)
    return project_root / ".pipelex"


def _init(*, config: dict[str, Any] | None) -> tuple[int, dict[str, Any]]:
    args = ["--format", "json"]
    if config is not None:
        args.extend(["--config", json.dumps(config)])
    result = CliRunner().invoke(_app, args)
    output = result.stdout if result.exit_code == 0 else result.stderr
    return result.exit_code, json.loads(output)


def _kit_text(relative_path: str) -> str:
    return (get_kit_configs_dir() / relative_path).read_text(encoding="utf-8")


class TestAgentInitExecution:
    def test_hosted_writes_the_setting_and_leaves_the_kit_inference_files(self, target_dir: Path) -> None:
        exit_code, payload = _init(config={"execution": "hosted"})

        assert exit_code == 0
        assert payload["execution"] == "hosted"
        assert payload["api_key_set"] is False
        assert "backends_enabled" not in payload
        assert "routing_profile" not in payload
        assert read_run_execution(pipelex_toml_path=target_dir / "pipelex.toml") == RunExecution.HOSTED
        for relative_path in ("inference/backends.toml", "inference/routing_profiles.toml"):
            assert (target_dir / relative_path).read_text(encoding="utf-8") == _kit_text(relative_path)

    @pytest.mark.usefixtures("target_dir")
    def test_hosted_reports_a_key_in_the_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PIPELEX_API_KEY", "plx_sk_test_not_a_secret")

        exit_code, payload = _init(config={"execution": "hosted"})

        assert exit_code == 0
        assert payload["api_key_set"] is True
        assert "plx_sk_test_not_a_secret" not in json.dumps(payload)

    @pytest.mark.parametrize("config", [None, {}, {"execution": "local"}, {"execution": "local", "backends": ["openai"]}])
    def test_local_or_absent_configures_the_backends_as_before(self, target_dir: Path, config: dict[str, Any] | None) -> None:
        exit_code, payload = _init(config=config)

        assert exit_code == 0
        assert payload["execution"] == "local"
        assert "backends_enabled" in payload
        assert "routing_profile" in payload
        assert read_run_execution(pipelex_toml_path=target_dir / "pipelex.toml") == RunExecution.LOCAL

    def test_an_unknown_execution_is_refused(self, target_dir: Path) -> None:
        exit_code, payload = _init(config={"execution": "elsewhere"})

        assert exit_code != 0
        assert payload["error_type"] == "ArgumentError"
        assert "elsewhere" in payload["message"]
        assert not target_dir.exists()

    @pytest.mark.parametrize("config", [{"execution": "hosted", "backends": ["openai"]}, {"execution": "hosted", "primary_backend": "openai"}])
    def test_hosted_refuses_the_backend_keys(self, target_dir: Path, config: dict[str, Any]) -> None:
        exit_code, payload = _init(config=config)

        assert exit_code != 0
        assert payload["error_type"] == "ArgumentError"
        assert not target_dir.exists()
