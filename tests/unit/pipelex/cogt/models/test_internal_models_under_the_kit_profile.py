"""The internal backend's models, served by the kit's own routing profile whichever provider backends are enabled.

The kit's active profile routes along a `fallback_order` of provider backends and has no `default`, so with none of
them enabled it sends every name nowhere; the internal backend serves its models all the same. Booted the way an
installation boots, through the global `config_manager` over the kit's inference tree in a faked home, from a project
root with no `.pipelex/`, and keyless (`needs_inference=False`) so no credential on this machine is a precondition.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pipelex.cogt.model_backends.backend import PipelexBackend
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_manager import ModelManager
from pipelex.kit.paths import get_kit_configs_dir
from pipelex.plugins.plugin_model_declarations import PluginModelDeclarations
from pipelex.system.configuration.config_loader import INFERENCE_DIR_NAME
from pipelex.system.environment import CONFIG_DIR_NAME
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


pytestmark = pytest.mark.usefixtures("no_pipelex_home")

INTERNAL_ONLY_BACKENDS = "[internal]\nenabled = true\n"
# TypeSafe is reached only through the kit profile's optional route for its own models, outside its `fallback_order`.
INTERNAL_AND_TYPESAFE_BACKENDS = f'{INTERNAL_ONLY_BACKENDS}\n[typesafe]\nenabled = true\napi_key = "${{TYPESAFE_API_KEY}}"\n'
# The control: Mistral is in the `fallback_order`, so the profile matches every name by default.
INTERNAL_AND_MISTRAL_BACKENDS = f'{INTERNAL_ONLY_BACKENDS}\n[mistral]\nenabled = true\napi_key = "${{MISTRAL_API_KEY}}"\n'

KIT_INTERNAL_MODELS = [
    ("reportlab-pdf", ModelType.DOC_GEN),
    ("pypdfium2-extract-pdf", ModelType.TEXT_EXTRACTOR),
    ("docling-extract-text", ModelType.TEXT_EXTRACTOR),
]


class TestInternalModelsUnderTheKitProfile:
    @pytest.fixture
    def global_inference_dir(self, tmp_path: Path, mocker: MockerFixture) -> Path:
        """A faked home carrying the kit's inference tree, and a project root with no `.pipelex/` to shadow it."""
        fake_home = tmp_path / "home"
        inference_dir = fake_home / CONFIG_DIR_NAME / INFERENCE_DIR_NAME
        shutil.copytree(Path(str(get_kit_configs_dir())) / INFERENCE_DIR_NAME, inference_dir)
        project_root = tmp_path / "project"
        (project_root / ".git").mkdir(parents=True)
        mocker.patch.object(Path, "home", return_value=fake_home)
        mocker.patch.object(Path, "cwd", return_value=project_root)
        return inference_dir

    @pytest.mark.parametrize(
        "backends_toml",
        [INTERNAL_ONLY_BACKENDS, INTERNAL_AND_TYPESAFE_BACKENDS, INTERNAL_AND_MISTRAL_BACKENDS],
        ids=["internal_only", "internal_and_typesafe", "internal_and_mistral"],
    )
    def test_the_kit_profile_serves_every_internal_model(self, global_inference_dir: Path, backends_toml: str) -> None:
        (global_inference_dir / "backends.toml").write_text(backends_toml, encoding="utf-8")

        models_manager = ModelManager()
        models_manager.setup(
            secrets_provider=EnvSecretsProvider(),
            plugin_model_declarations=PluginModelDeclarations.make_empty(),
            needs_inference=False,
        )

        assert models_manager.routing_profile.name == "all_enabled_backends"
        model_deck = models_manager.get_model_deck()
        for model_handle, model_type in KIT_INTERNAL_MODELS:
            inference_model = model_deck.get_required_inference_model(model_handle=model_handle, model_type=model_type)
            assert inference_model.backend_name == PipelexBackend.INTERNAL
