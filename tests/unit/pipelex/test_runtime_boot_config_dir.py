"""`config_dir` at boot must actually scope the config load.

It did not. The parameter was stored as `self.config_dir_path` and never read again, while
`setup_config` was called without a `config_dir` — so an embedder passing an explicit config dir got
the ordinary project/global layering and no error at all. This is the test that would have caught it.

A scoped load is *package defaults + this directory*, so one overridden leaf is enough to tell the
two apart without writing a whole valid config tree.
"""

from pathlib import Path

from pipelex.config import get_config
from pipelex.pipelex import Pipelex
from pipelex.runtime_boot import RuntimeBoot
from pipelex.system.runtime import IntegrationMode, runtime_manager


def _test_integration_mode() -> IntegrationMode:
    """The boot mode the session conftest uses, so a re-boot here matches the one it replaces."""
    return IntegrationMode.CI if runtime_manager.is_ci_testing else IntegrationMode.PYTEST


class TestConfigDirReachesTheConfigLoader:
    def test_an_explicit_config_dir_is_what_gets_loaded(self, tmp_path: Path) -> None:
        # WARNING is quieter than the INFO default, never noisier — this boot configures logging.
        (tmp_path / "pipelex.toml").write_text('[pipelex.log_config]\ndefault_log_level = "WARNING"\n')

        Pipelex.teardown_if_needed()
        try:
            runtime_boot = RuntimeBoot(config_dir=tmp_path)
            try:
                runtime_boot.setup(integration_mode=_test_integration_mode(), needs_inference=False)
                assert get_config().pipelex.log_config.default_log_level == "WARNING"
            finally:
                runtime_boot.teardown()
        finally:
            # Restore what the module fixture set up, so its teardown is sane.
            Pipelex.make(integration_mode=_test_integration_mode())
