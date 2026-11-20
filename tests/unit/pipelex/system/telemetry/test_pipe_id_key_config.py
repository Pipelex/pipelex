from pathlib import Path

import pytest
from pydantic import ValidationError
from pytest_mock import MockerFixture

from pipelex.cli.commands.doctor_cmd import check_telemetry_config
from pipelex.system.telemetry.exceptions import TelemetryConfigValidationError
from pipelex.system.telemetry.telemetry_config import PIPE_ID_KEY_MIN_LENGTH, TelemetryConfig
from pipelex.system.telemetry.telemetry_loader import load_telemetry_config
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider

_KEY_ENV_VAR = "PIPELEX_TEST_PIPE_ID_KEY"

pytestmark = pytest.mark.usefixtures("no_pipelex_home")


class TestPipeIdKeyConfig:
    @pytest.fixture
    def global_dir(self, tmp_path: Path, mocker: MockerFixture) -> Path:
        """A fake home whose `.pipelex/` is the only configuration layer."""
        fake_home = tmp_path / "home"
        global_config_dir = fake_home / ".pipelex"
        global_config_dir.mkdir(parents=True)
        project_root = tmp_path / "project"
        (project_root / ".git").mkdir(parents=True)
        mocker.patch.object(Path, "home", return_value=fake_home)
        mocker.patch.object(Path, "cwd", return_value=project_root)
        return global_config_dir

    def test_no_key_is_the_default(self) -> None:
        assert TelemetryConfig().pipe_id_key is None

    def test_a_long_enough_key_is_kept(self) -> None:
        key = "k" * PIPE_ID_KEY_MIN_LENGTH

        assert TelemetryConfig(pipe_id_key=key).pipe_id_key == key

    @pytest.mark.parametrize(
        ("key", "reason"),
        [
            ("k" * (PIPE_ID_KEY_MIN_LENGTH - 1), "too short"),
            ("${env:PIPELEX_PIPE_ID_KEY}" + "k" * PIPE_ID_KEY_MIN_LENGTH, "placeholder"),
        ],
    )
    def test_a_key_that_is_no_key_is_refused(self, key: str, reason: str) -> None:
        with pytest.raises(ValidationError, match=reason):
            TelemetryConfig(pipe_id_key=key)

    def test_a_key_read_from_the_environment_loads(self, global_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        key = "e" * PIPE_ID_KEY_MIN_LENGTH
        monkeypatch.setenv(_KEY_ENV_VAR, key)
        (global_dir / "telemetry.toml").write_text(f'pipe_id_key = "${{env:{_KEY_ENV_VAR}}}"\n')

        assert load_telemetry_config(secrets_provider=EnvSecretsProvider()).pipe_id_key == key

    def test_a_key_whose_variable_is_missing_refuses_the_load(self, global_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """The hosted plane relies on this: a runner or a worker whose secret did not arrive does not boot."""
        monkeypatch.delenv(_KEY_ENV_VAR, raising=False)
        (global_dir / "telemetry.toml").write_text(f'pipe_id_key = "${{env:{_KEY_ENV_VAR}}}"\n')

        with pytest.raises(TelemetryConfigValidationError, match="pipe_id_key"):
            load_telemetry_config(secrets_provider=EnvSecretsProvider())

    @pytest.mark.parametrize("is_variable_set", [True, False])
    def test_doctor_takes_a_key_named_by_a_placeholder_as_a_well_formed_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, is_variable_set: bool
    ) -> None:
        """Doctor reads the file as written: a secret named through a placeholder, as the docs advise, is well formed."""
        if is_variable_set:
            monkeypatch.setenv(_KEY_ENV_VAR, "e" * PIPE_ID_KEY_MIN_LENGTH)
        else:
            monkeypatch.delenv(_KEY_ENV_VAR, raising=False)
        (tmp_path / "telemetry.toml").write_text(f'pipe_id_key = "${{env:{_KEY_ENV_VAR}}}"\n')

        assert check_telemetry_config(config_dir=tmp_path).is_healthy is True

    def test_a_refused_key_is_never_quoted_in_the_error(self, global_dir: Path) -> None:
        """A key refused as too short is still a secret: neither the report nor the error it was raised from quotes it."""
        short_key = "SHORT-SECRET-KEY-VALUE"
        (global_dir / "telemetry.toml").write_text(f'pipe_id_key = "{short_key}"\n')

        with pytest.raises(TelemetryConfigValidationError, match="too short") as exc_info:
            load_telemetry_config(secrets_provider=EnvSecretsProvider())

        assert short_key not in str(exc_info.value)
        assert short_key not in str(exc_info.value.__cause__)
