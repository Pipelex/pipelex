"""`pipelex-agent init` routing: which profile a config with no backend list leaves active.

The template enables many backends and routes among them with its own profile, so naming no backends
must keep that profile rather than demand a primary backend nobody was asked for.
"""

import shutil
from pathlib import Path

import pytest
import typer

from pipelex.cli.agent_cli.commands.init_cmd import _configure_routing  # pyright: ignore[reportPrivateUsage]
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
