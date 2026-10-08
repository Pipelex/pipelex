"""A home a former release set up is refused at boot with one error naming the cleanup, before any low-level refusal.

The model manager is where the boot reads the inference files, so it is where the check runs, ahead of the backend
library and the routing profile library. Without it a v0.72 home meets whichever refusal comes first: the Gateway's
missing key on a boot that needs inference, its backend file declaring no model on a keyless one, or
`RoutingProfileDisabledBackendError` once the Gateway is turned off and `active` still names its profile. None of them
says that the release behind the files is gone, or what to run.

The home is faked as the other model-manager tests fake it: the kit's inference tree, with the v0.72 release's own
files laid over it, copied from that release's wheel.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pipelex.base_exceptions import PipelexSetupError
from pipelex.cogt.models.model_manager import ModelManager
from pipelex.kit.paths import get_kit_configs_dir
from pipelex.migration.exceptions import FormerReleaseConfigError
from pipelex.migration.former_release import kit_default_routing_profile_name
from pipelex.migration.former_release_cleanup import clean_former_release
from pipelex.plugins.plugin_model_declarations import PluginModelDeclarations
from pipelex.system.configuration.config_loader import BACKENDS_FILE_NAME, INFERENCE_DIR_NAME, ROUTING_PROFILES_OVERRIDE_FILE_NAME
from pipelex.system.environment import CONFIG_DIR_NAME
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


pytestmark = pytest.mark.usefixtures("no_pipelex_home")

V0_72_CONFIG_DIR = Path("tests/data/migration/former_release/v0_72")

# The line of the v0.72 kit's `backends.toml` that enables the Pipelex Gateway.
GATEWAY_ENABLED_LINE = "enabled = true                         # Enable after accepting terms via `pipelex init config`"


def _setup(*, needs_inference: bool) -> ModelManager:
    models_manager = ModelManager()
    models_manager.setup(
        secrets_provider=EnvSecretsProvider(),
        plugin_model_declarations=PluginModelDeclarations.make_empty(),
        needs_inference=needs_inference,
    )
    return models_manager


class TestAFormerReleaseHomeAtBoot:
    @pytest.fixture
    def home_config_dir(self, tmp_path: Path, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch) -> Path:
        """A faked home holding the kit's inference tree with the v0.72 release's files over it, and no project."""
        fake_home = tmp_path / "home"
        config_dir = fake_home / CONFIG_DIR_NAME
        shutil.copytree(Path(str(get_kit_configs_dir())) / INFERENCE_DIR_NAME, config_dir / INFERENCE_DIR_NAME)
        shutil.copytree(V0_72_CONFIG_DIR, config_dir, dirs_exist_ok=True)
        project_root = tmp_path / "project"
        (project_root / ".git").mkdir(parents=True)
        mocker.patch.object(Path, "home", return_value=fake_home)
        mocker.patch.object(Path, "cwd", return_value=project_root)
        # The Gateway's own key is unset, so a boot that resolved credentials first would stop on it instead.
        monkeypatch.delenv("PIPELEX_GATEWAY_API_KEY", raising=False)
        return config_dir

    @pytest.mark.parametrize("needs_inference", [False, True])
    def test_a_v0_72_home_is_refused_with_the_one_error_naming_both_remedies(self, home_config_dir: Path, needs_inference: bool) -> None:
        with pytest.raises(FormerReleaseConfigError) as refused:
            _setup(needs_inference=needs_inference)

        message = str(refused.value)
        assert isinstance(refused.value, PipelexSetupError)
        assert "`pipelex migrate`" in message
        assert "`pipelex init`" in message
        assert str(home_config_dir / INFERENCE_DIR_NAME / BACKENDS_FILE_NAME) in message
        assert "'pipelex_gateway'" in message
        assert "'all_pipelex_gateway'" in message
        assert "PIPELEX_GATEWAY_API_KEY" not in message, "the refusal is the former release, not the key it once needed"

    def test_a_disabled_gateway_is_refused_by_the_same_error_rather_than_the_routing_refusal(self, home_config_dir: Path) -> None:
        backends_path = home_config_dir / INFERENCE_DIR_NAME / BACKENDS_FILE_NAME
        text = backends_path.read_text(encoding="utf-8")
        assert text.count(GATEWAY_ENABLED_LINE) == 1
        backends_path.write_text(text.replace(GATEWAY_ENABLED_LINE, "enabled = false"), encoding="utf-8")

        with pytest.raises(FormerReleaseConfigError) as refused:
            _setup(needs_inference=False)

        message = str(refused.value)
        assert "'all_pipelex_gateway'" in message
        assert "enables the 'pipelex_gateway' backend" not in message

    def test_a_home_whose_overrides_moved_it_off_the_gateway_boots(self, home_config_dir: Path) -> None:
        """Only what stops the boot is refused: what is inert is left for `pipelex migrate` and the doctor to report."""
        inference_dir = home_config_dir / INFERENCE_DIR_NAME
        (inference_dir / "backends_override.toml").write_text("[pipelex_gateway]\nenabled = false\n", encoding="utf-8")
        (inference_dir / ROUTING_PROFILES_OVERRIDE_FILE_NAME).write_text('active = "all_openai"\n', encoding="utf-8")

        models_manager = _setup(needs_inference=False)

        assert models_manager.routing_profile.name == "all_openai"
        assert "pipelex_gateway" not in models_manager.inference_backend_library.root

    @pytest.mark.parametrize("needs_inference", [False, True])
    def test_a_v0_72_home_boots_once_cleaned_on_the_kit_default_profile(self, home_config_dir: Path, needs_inference: bool) -> None:
        cleanup = clean_former_release(config_dirs=[home_config_dir], dry_run=False)
        assert not cleanup.needs_attention

        models_manager = _setup(needs_inference=needs_inference)

        assert models_manager.routing_profile.name == kit_default_routing_profile_name()
        assert "pipelex_gateway" not in models_manager.inference_backend_library.root
        assert "pipelex_manifold" not in models_manager.inference_backend_library.root, "the table the release left for Manifold stays, disabled"
