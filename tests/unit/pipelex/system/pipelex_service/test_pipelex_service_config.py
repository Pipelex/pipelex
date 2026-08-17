"""Unit tests for PipelexServiceConfig."""

import os
import pathlib
import tempfile
from pathlib import Path

import pytest

from pipelex.system.pipelex_service.pipelex_service_config import (
    PIPELEX_SERVICE_CONFIG_FILE_NAME,
    PipelexServiceAgreement,
    PipelexServiceConfig,
    is_pipelex_gateway_enabled,
    load_pipelex_service_config_if_exists,
)


class TestPipelexServiceConfig:
    """Tests for PipelexServiceConfig and related functions."""

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
        backends_file = tmp_path / "backends.toml"
        backends_file.write_text(f'[pipelex_gateway]\nenabled = {enabled_value}\napi_key = "x"\n', encoding="utf-8")

        assert is_pipelex_gateway_enabled(backends_file_path=backends_file) is expected

    def test_is_pipelex_gateway_enabled_defaults_to_enabled_when_the_key_is_absent(self, tmp_path: Path) -> None:
        """No `enabled` key means enabled — the loader's default too."""
        backends_file = tmp_path / "backends.toml"
        backends_file.write_text('[pipelex_gateway]\napi_key = "x"\n', encoding="utf-8")

        assert is_pipelex_gateway_enabled(backends_file_path=backends_file) is True

    def test_is_pipelex_gateway_enabled_is_false_without_a_gateway_table(self, tmp_path: Path) -> None:
        backends_file = tmp_path / "backends.toml"
        backends_file.write_text('[openai]\napi_key = "x"\n', encoding="utf-8")

        assert is_pipelex_gateway_enabled(backends_file_path=backends_file) is False

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
