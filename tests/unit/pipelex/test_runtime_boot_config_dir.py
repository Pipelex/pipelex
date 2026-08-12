"""`config_dir` at boot must actually scope the main config load.

It scoped nothing at all at first: the parameter was stored as `self.config_dir_path` and never read
again, while `setup_config` was called without a `config_dir`, so an embedder passing an explicit
config dir got the ordinary project/global layering and no error. This is the test that would have
caught it.

A scoped load is *package defaults + this directory*, so one overridden leaf is enough to tell the
two apart without writing a whole valid config tree.

Scope note: `config_dir` scopes the main TOML load only — the inference file paths still resolve
through the layered `config_manager.*` properties, because pinning them needs overrides that live on
the concrete `ModelManager` rather than on the `ModelManagerAbstract` this boot is typed against. That
gap is deliberate and documented in the boot docstrings, which is
why this module asserts the main-config leaf and nothing about backends or decks.
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
            # Through `make()`, not a bare construct-then-setup: `make()` is the only entry point that
            # releases the process globals when a boot dies partway (`_release_after_failed_boot`), and
            # a hand-rolled `teardown()` on a half-built instance raises `AttributeError` instead —
            # masking the real error and leaving the singleton registered for the rest of the worker.
            runtime_boot = RuntimeBoot.make(
                integration_mode=_test_integration_mode(),
                needs_inference=False,
                config_dir=tmp_path,
            )
            try:
                assert get_config().pipelex.log_config.default_log_level == "WARNING"
            finally:
                runtime_boot.teardown()
        finally:
            # Restore what the module fixture set up, so its teardown is sane.
            Pipelex.make(integration_mode=_test_integration_mode())
