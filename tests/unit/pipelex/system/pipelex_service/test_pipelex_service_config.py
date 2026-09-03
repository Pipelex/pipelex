"""Unit tests for PipelexServiceConfig."""

import os
import pathlib
import tempfile
from pathlib import Path

import pytest

from pipelex.cogt.exceptions import InferenceBackendLibraryValidationError
from pipelex.system.pipelex_service.pipelex_service_config import (
    PIPELEX_SERVICE_CONFIG_FILE_NAME,
    PipelexServiceAgreement,
    PipelexServiceConfig,
    is_pipelex_gateway_enabled,
    load_pipelex_service_config_if_exists,
)


class TestPipelexServiceConfig:
    """Tests for PipelexServiceConfig and related functions."""

    def _write_backends(self, config_dir: Path, *, base: str, override: str | None = None) -> None:
        inference_dir = config_dir / "inference"
        inference_dir.mkdir(parents=True, exist_ok=True)
        (inference_dir / "backends.toml").write_text(base, encoding="utf-8")
        if override is not None:
            (inference_dir / "backends_override.toml").write_text(override, encoding="utf-8")

    @pytest.mark.parametrize(
        ("enabled_value", "expected"),
        [
            ("true", True),
            ("false", False),
            # Not booleans, and exactly what the loader also treats as truthy — the two readers of
            # `backends.toml` must agree, or the boot fetches no gateway specs for a backend the
            # loader then insists is enabled.
            ("1", True),
            ("0", False),
            ('"yes"', True),
        ],
    )
    def test_is_pipelex_gateway_enabled_reads_enabled_the_way_the_loader_does(self, tmp_path: Path, enabled_value: str, expected: bool) -> None:
        """A `pipelex_gateway` table with a non-boolean `enabled` is enabled iff the loader would load it.

        `InferenceBackendLibrary.load` gates on the raw value's truthiness before it validates
        anything, and `RuntimeBoot` decides whether to fetch the gateway's model specs from *this*
        function over the same file. Reading `enabled` as "is the literal `true`" here left `enabled = 1`
        in a state the loader could not name: enabled with no specs, so refused as *"remote model specs
        were not provided"* on a strict boot, and silently dropped from the deck on a lenient one.
        """
        self._write_backends(tmp_path, base=f'[pipelex_gateway]\nenabled = {enabled_value}\napi_key = "x"\n')

        assert is_pipelex_gateway_enabled(config_dir=tmp_path) is expected

    def test_is_pipelex_gateway_enabled_defaults_to_enabled_when_the_key_is_absent(self, tmp_path: Path) -> None:
        """No `enabled` key means enabled — the loader's default too."""
        self._write_backends(tmp_path, base='[pipelex_gateway]\napi_key = "x"\n')

        assert is_pipelex_gateway_enabled(config_dir=tmp_path) is True

    def test_is_pipelex_gateway_enabled_is_false_without_a_gateway_table(self, tmp_path: Path) -> None:
        self._write_backends(tmp_path, base='[openai]\napi_key = "x"\n')

        assert is_pipelex_gateway_enabled(config_dir=tmp_path) is False

    def test_is_pipelex_gateway_enabled_is_false_without_a_base_file(self, tmp_path: Path) -> None:
        """An override cannot stand in for the base: no document, no gateway."""
        inference_dir = tmp_path / "inference"
        inference_dir.mkdir(parents=True)
        (inference_dir / "backends_override.toml").write_text("[pipelex_gateway]\nenabled = true\n", encoding="utf-8")

        assert is_pipelex_gateway_enabled(config_dir=tmp_path) is False

    @pytest.mark.parametrize(
        ("base_enabled", "override_enabled", "expected"),
        [
            ("true", "false", False),
            ("false", "true", True),
            # The override is read with the same truthiness as the base.
            ("false", "1", True),
            ("true", "0", False),
        ],
    )
    def test_is_pipelex_gateway_enabled_reads_the_override_over_the_base(
        self, tmp_path: Path, base_enabled: str, override_enabled: str, expected: bool
    ) -> None:
        """The personal override is the loader's document too, so the gate must see it."""
        self._write_backends(
            tmp_path,
            base=f'[pipelex_gateway]\nenabled = {base_enabled}\napi_key = "x"\n',
            override=f"[pipelex_gateway]\nenabled = {override_enabled}\n",
        )

        assert is_pipelex_gateway_enabled(config_dir=tmp_path) is expected

    def test_is_pipelex_gateway_enabled_refuses_an_override_that_does_not_parse_with_the_librarys_class(self, tmp_path: Path) -> None:
        """A parse error must reach the boot as the library's refusal, which names the file, not as a raw `TomlError`."""
        inference_dir = tmp_path / "inference"
        inference_dir.mkdir()
        (inference_dir / "backends.toml").write_text("[pipelex_gateway]\nenabled = true\n")
        override_path = inference_dir / "backends_override.toml"
        override_path.write_text("[pipelex_gateway\nenabled = false\n")

        with pytest.raises(InferenceBackendLibraryValidationError) as refused:
            is_pipelex_gateway_enabled(config_dir=tmp_path)

        assert str(override_path) in str(refused.value)

    def test_gateway_config_default_terms_not_accepted(self) -> None:
        """Test that gateway terms_accepted defaults to False."""
        config = PipelexServiceAgreement()
        assert config.terms_accepted is False

    def test_gateway_config_terms_accepted(self) -> None:
        """Test gateway config with terms_accepted = True."""
        config = PipelexServiceAgreement(terms_accepted=True)
        assert config.terms_accepted is True

    def test_pipelex_service_config_with_gateway(self) -> None:
        """Test PipelexServiceConfig with custom gateway config."""
        config = PipelexServiceConfig(agreement=PipelexServiceAgreement(terms_accepted=True))
        assert config.agreement.terms_accepted is True

    def test_load_pipelex_service_config_if_exists_returns_none(self) -> None:
        """Test load_pipelex_service_config_if_exists returns None when file doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = load_pipelex_service_config_if_exists(config_dir=pathlib.Path(temp_dir))
            assert config is None

    def test_load_pipelex_service_config_if_exists_returns_config(self) -> None:
        """Test load_pipelex_service_config_if_exists returns config when file exists."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_content = """[agreement]
terms_accepted = false
"""
            config_path = os.path.join(temp_dir, PIPELEX_SERVICE_CONFIG_FILE_NAME)
            pathlib.Path(config_path).write_text(config_content, encoding="utf-8")

            config = load_pipelex_service_config_if_exists(config_dir=pathlib.Path(temp_dir))
            assert config is not None
            assert config.agreement.terms_accepted is False
