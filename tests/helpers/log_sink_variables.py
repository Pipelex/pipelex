"""Fakes and builders shared by the tests of the built-in sink factories resolving ``${…}`` placeholders."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

from typing_extensions import override

from pipelex.plugins.discovery import build_registrar
from pipelex.plugins.log_sink_registry import LogSinkFactoryFn, LogSinkRegistry
from pipelex.providers.builtins import KERNEL_BUILTIN_PLUGINS, KERNEL_CORE_UNCONDITIONAL_PLUGIN_NAMES, KERNEL_ENTRY_POINT_GROUPS
from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.tools.log.log_config import LogConfig
from pipelex.tools.misc.toml_utils import load_toml_from_path
from pipelex.tools.secrets.exceptions import SecretNotFoundError
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from pipelex.system.configuration.configs import PipelexConfig
    from pipelex.tools.log.log_sink import LogSinkMethod


class DictSecretsProvider(SecretsProviderAbstract):
    """The secrets a test hands it, and nothing else."""

    def __init__(self, *, secrets: dict[str, str]) -> None:
        self._secrets = secrets

    @override
    def get_required_secret(self, secret_id: str) -> str:
        if secret_id not in self._secrets:
            msg = f"No secret '{secret_id}' in this test provider"
            raise SecretNotFoundError(msg)
        return self._secrets[secret_id]

    @override
    def get_optional_secret(self, secret_id: str) -> str | None:
        return self._secrets.get(secret_id)

    @override
    def get_required_secret_specific_version(self, secret_id: str, *, version_id: str) -> str:
        raise NotImplementedError

    @override
    def get_optional_secret_specific_version(self, secret_id: str, *, version_id: str) -> str | None:
        raise NotImplementedError

    @override
    def set_secret_as_env_var(self, secret_id: str, *, version_id: str = "latest") -> None:
        raise NotImplementedError


def sink_settings_log_config(*, otlp_headers: dict[str, str] | None = None, gcp_credentials_file_path: str | None = None) -> LogConfig:
    """The shipped ``[runtime.log]``, with the ``otlp`` headers and the ``gcp`` key path the test names."""
    config_dict = load_toml_from_path(ConfigLoader().pipelex_root_dir / "pipelex.toml")
    log_dict = config_dict["runtime"]["log"]
    otlp = {**log_dict["otlp"], "headers": otlp_headers or {}}
    gcp = {**log_dict["gcp"], "credentials_file_path": gcp_credentials_file_path}
    return LogConfig.model_validate({**log_dict, "otlp": otlp, "gcp": gcp})


def builtin_log_sink_factory(*, method: LogSinkMethod, mocker: MockerFixture) -> LogSinkFactoryFn:
    """The factory the built-in plugins register for ``method``, discovered with no external plugin."""
    mocker.patch("pipelex.plugins.discovery._external_entry_points", return_value=[])
    registrar = build_registrar(
        config=cast("PipelexConfig", SimpleNamespace(runtime=SimpleNamespace(plugins=SimpleNamespace(disabled=[])))),
        boot_orchestrator=None,
        builtin_plugins=KERNEL_BUILTIN_PLUGINS,
        core_unconditional_plugin_names=KERNEL_CORE_UNCONDITIONAL_PLUGIN_NAMES,
        entry_point_groups=KERNEL_ENTRY_POINT_GROUPS,
    )
    return LogSinkRegistry(registrar.log_sinks).get_required(method=method)
