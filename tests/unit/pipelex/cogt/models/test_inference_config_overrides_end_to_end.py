"""The two personal override files, read where the boot reads them: through the global `config_manager`.

A developer writes `~/.pipelex/inference/backends_override.toml` and `routing_profiles_override.toml`
once, and every project on the machine follows — the model manager's default paths carry both, and
deleting the two files restores the shipped default. Built on the kit's own inference tree so the shipped defaults are the
fixture, and lenient (`needs_inference=False`) so no credential on this machine is a precondition.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pipelex.cogt.models.model_manager import ModelManager
from pipelex.kit.paths import get_kit_configs_dir
from pipelex.plugins.plugin_model_declarations import PluginModelDeclarations
from pipelex.system.configuration.config_loader import CONFIG_DIR_NAME, INFERENCE_DIR_NAME
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


pytestmark = pytest.mark.usefixtures("no_pipelex_home")

# Ollama needs no credential, so whether it loads depends on the override alone.
OLLAMA_OFF_OVERRIDE = "[ollama]\nenabled = false\n"
ANTHROPIC_PROFILE_OVERRIDE = 'active = "all_anthropic"\n'


class TestInferenceConfigOverridesEndToEnd:
    @pytest.fixture
    def global_inference_dir(self, tmp_path: Path, mocker: MockerFixture) -> Path:
        """A faked home carrying the kit's inference tree, and a project root with no `.pipelex/`.

        `Path.home` and `Path.cwd` are what the global `config_manager` derives its tiers from on
        every call, so patching them is enough to point the real singleton at this tree.
        """
        fake_home = tmp_path / "home"
        inference_dir = fake_home / CONFIG_DIR_NAME / INFERENCE_DIR_NAME
        shutil.copytree(Path(str(get_kit_configs_dir())) / INFERENCE_DIR_NAME, inference_dir)
        project_root = tmp_path / "project"
        (project_root / ".git").mkdir(parents=True)
        mocker.patch.object(Path, "home", return_value=fake_home)
        mocker.patch.object(Path, "cwd", return_value=project_root)
        return inference_dir

    def _setup(self) -> ModelManager:
        models_manager = ModelManager()
        models_manager.setup(
            secrets_provider=EnvSecretsProvider(),
            plugin_model_declarations=PluginModelDeclarations.make_empty(),
            needs_inference=False,
        )
        return models_manager

    def _active_profile_name(self) -> str:
        return self._setup().routing_profile.name

    def _ollama_is_loaded(self) -> bool:
        return "ollama" in self._setup().inference_backend_library.root

    @pytest.mark.usefixtures("global_inference_dir")
    def test_the_shipped_default_needs_no_pipelex_account(self) -> None:
        """The control, and the state the overrides must restore when deleted."""
        assert self._ollama_is_loaded()
        assert self._active_profile_name() == "all_enabled_backends"

    def test_two_global_override_files_move_the_machine_and_deleting_them_moves_it_back(self, global_inference_dir: Path) -> None:
        backends_override = global_inference_dir / "backends_override.toml"
        routing_override = global_inference_dir / "routing_profiles_override.toml"
        backends_override.write_text(OLLAMA_OFF_OVERRIDE, encoding="utf-8")
        routing_override.write_text(ANTHROPIC_PROFILE_OVERRIDE, encoding="utf-8")

        assert not self._ollama_is_loaded()
        assert self._active_profile_name() == "all_anthropic"

        backends_override.unlink()
        routing_override.unlink()

        assert self._ollama_is_loaded()
        assert self._active_profile_name() == "all_enabled_backends"

    def test_a_project_override_wins_over_the_global_one(self, global_inference_dir: Path, tmp_path: Path) -> None:
        """The project keeps its own inference files out of it: only its override is added, last."""
        (global_inference_dir / "routing_profiles_override.toml").write_text(ANTHROPIC_PROFILE_OVERRIDE, encoding="utf-8")
        project_inference_dir = tmp_path / "project" / CONFIG_DIR_NAME / INFERENCE_DIR_NAME
        project_inference_dir.mkdir(parents=True)
        (project_inference_dir / "routing_profiles_override.toml").write_text('active = "all_openai"\n', encoding="utf-8")

        assert self._active_profile_name() == "all_openai"
