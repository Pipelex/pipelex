"""`pipelex-agent init` routing: which profile a config with no backend list leaves active.

The template enables many backends and routes among them with its own profile, so naming no backends
must keep that profile rather than demand a primary backend nobody was asked for.
"""

import json
import shutil
from pathlib import Path

import pytest
import typer

from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat, set_agent_cli_error_format
from pipelex.cli.agent_cli.commands.init_cmd import (
    _configure_backends,  # pyright: ignore[reportPrivateUsage]
    _configure_routing,  # pyright: ignore[reportPrivateUsage]
)
from pipelex.kit.paths import get_kit_configs_dir
from pipelex.tools.misc.toml_utils import load_toml_from_path

TEMPLATE_BACKENDS = ["openai", "anthropic", "mistral"]


@pytest.fixture
def target_dir(tmp_path: Path) -> Path:
    inference_dir = tmp_path / "inference"
    inference_dir.mkdir()
    shutil.copy2(Path(str(get_kit_configs_dir())) / "inference" / "routing_profiles.toml", inference_dir / "routing_profiles.toml")
    return tmp_path


def _active_profile(target_dir: Path) -> str:
    return str(load_toml_from_path(target_dir / "inference" / "routing_profiles.toml")["active"])


class TestAgentInitRouting:
    def test_no_backends_named_keeps_the_template_profile(self, target_dir: Path) -> None:
        template_active = _active_profile(target_dir)

        profile = _configure_routing(TEMPLATE_BACKENDS, config={}, target_dir=target_dir)

        assert profile == template_active
        assert _active_profile(target_dir) == template_active

    def test_primary_named_alone_routes_the_template_backends_to_it_first(self, target_dir: Path) -> None:
        profile = _configure_routing(TEMPLATE_BACKENDS, config={"primary_backend": "mistral"}, target_dir=target_dir)

        assert profile == "custom_routing"
        custom_routing = load_toml_from_path(target_dir / "inference" / "routing_profiles.toml")["profiles"]["custom_routing"]
        assert custom_routing["fallback_order"] == ["mistral", "openai", "anthropic"]

    def test_several_backends_named_without_a_primary_is_refused(self, target_dir: Path) -> None:
        with pytest.raises(typer.Exit):
            _configure_routing(TEMPLATE_BACKENDS, config={"backends": TEMPLATE_BACKENDS}, target_dir=target_dir)


class TestAgentInitMissingFiles:
    """A configuration file `init` should have written but finds missing is `pipelex.config.file_missing`, never a bug."""

    def test_a_missing_routing_profiles_file_is_a_missing_configuration_file(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        set_agent_cli_error_format(CliOutputFormat.JSON)

        with pytest.raises(typer.Exit):
            _configure_routing(TEMPLATE_BACKENDS, config={}, target_dir=tmp_path)

        problem = json.loads(capsys.readouterr().err)
        assert problem["code"] == "pipelex.config.file_missing"
        assert problem["next_step"]["kind"] == "fix_configuration"
        assert "routing_profiles.toml' of the inference configuration" in problem["next_step"]["detail"]

    def test_a_missing_backends_file_is_a_missing_configuration_file(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        set_agent_cli_error_format(CliOutputFormat.JSON)
        template_backends_path = Path(str(get_kit_configs_dir())) / "inference" / "backends.toml"

        with pytest.raises(typer.Exit):
            _configure_backends(config={}, backends_toml_path=tmp_path / "backends.toml", template_backends_path=template_backends_path)

        problem = json.loads(capsys.readouterr().err)
        assert problem["code"] == "pipelex.config.file_missing"
        assert problem["next_step"]["kind"] == "fix_configuration"
        assert "backends.toml' of the inference configuration" in problem["next_step"]["detail"]
