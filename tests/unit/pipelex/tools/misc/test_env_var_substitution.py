from pathlib import Path

import pytest

from pipelex.tools.environment import EnvVarNotFoundError, substitute_env_vars
from pipelex.tools.misc.toml_utils import (
    TOMLValidationError,
    failable_load_toml_from_path,
    load_toml_from_path,
)


class TestEnvVarSubstitution:
    def testsubstitute_env_vars_basic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test basic environment variable substitution."""
        monkeypatch.setenv("TEST_VAR", "test_value")
        monkeypatch.setenv("ANOTHER_VAR", "another_value")

        content = 'key1 = "${TEST_VAR}"\nkey2 = "${ANOTHER_VAR}"'
        result = substitute_env_vars(content)

        assert result == 'key1 = "test_value"\nkey2 = "another_value"'

    def testsubstitute_env_vars_with_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test environment variable substitution with default values."""
        monkeypatch.setenv("EXISTING_VAR", "existing_value")

        content = 'key1 = "${EXISTING_VAR:default1}"\nkey2 = "${NONEXISTENT_VAR:default2}"'
        result = substitute_env_vars(content)

        assert result == 'key1 = "existing_value"\nkey2 = "default2"'

    def testsubstitute_env_vars_missing_required(self) -> None:
        """Test that missing required environment variable raises proper error."""
        content = 'key = "${NONEXISTENT_REQUIRED_VAR}"'

        with pytest.raises(EnvVarNotFoundError) as exc_info:
            substitute_env_vars(content)

        assert "Environment variable 'NONEXISTENT_REQUIRED_VAR' is required but not set" in str(exc_info.value)

    def testsubstitute_env_vars_complex_content(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test substitution in complex TOML content."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://azure.example.com")
        monkeypatch.setenv("API_KEY", "secret123")

        content = """[azure_openai]
endpoint = "${AZURE_ENDPOINT}"
api_key = "${API_KEY}"

[openai]
endpoint = "${OPENAI_ENDPOINT:https://api.openai.com/v1}"
api_key = "${OPENAI_KEY:default_key}"
"""
        result = substitute_env_vars(content)

        expected = """[azure_openai]
endpoint = "https://azure.example.com"
api_key = "secret123"

[openai]
endpoint = "https://api.openai.com/v1"
api_key = "default_key"
"""
        assert result == expected

    def test_load_toml_with_env_substitution_enabled(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading TOML with environment variable substitution enabled."""
        monkeypatch.setenv("DB_HOST", "localhost")
        monkeypatch.setenv("DB_PORT", "5432")

        toml_content = """database_host = "${DB_HOST}"
database_port = "${DB_PORT}"
database_name = "${DB_NAME:test_db}"
"""
        toml_file = tmp_path / "config.toml"
        toml_file.write_text(toml_content)

        result = load_toml_from_path(str(toml_file), is_env_var_substitution_enabled=True)

        assert result["database_host"] == "localhost"
        assert result["database_port"] == "5432"
        assert result["database_name"] == "test_db"

    def test_load_toml_with_env_substitution_disabled(self, tmp_path: Path) -> None:
        """Test loading TOML with environment variable substitution disabled (default)."""
        toml_content = """database_host = "${DB_HOST}"
database_port = "${DB_PORT}"
"""
        toml_file = tmp_path / "config.toml"
        toml_file.write_text(toml_content)

        result = load_toml_from_path(str(toml_file), is_env_var_substitution_enabled=False)

        # Should keep the placeholders as-is
        assert result["database_host"] == "${DB_HOST}"
        assert result["database_port"] == "${DB_PORT}"

    def test_load_toml_with_env_substitution_missing_var(self, tmp_path: Path) -> None:
        """Test loading TOML with missing required environment variable."""
        toml_content = """database_host = "${MISSING_VAR}"
"""
        toml_file = tmp_path / "config.toml"
        toml_file.write_text(toml_content)

        with pytest.raises(TOMLValidationError) as exc_info:
            load_toml_from_path(str(toml_file), is_env_var_substitution_enabled=True)

        error_msg = str(exc_info.value)
        assert "Environment variable substitution failed" in error_msg
        assert "MISSING_VAR" in error_msg

    def test_failable_load_with_env_substitution(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test failable loading with environment variable substitution."""
        monkeypatch.setenv("TEST_VALUE", "success")

        toml_content = """status = "${TEST_VALUE}"
"""
        toml_file = tmp_path / "config.toml"
        toml_file.write_text(toml_content)

        result = failable_load_toml_from_path(str(toml_file), is_env_var_substitution_enabled=True)

        assert result is not None
        assert result["status"] == "success"

    def test_failable_load_with_missing_env_var(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Test failable loading with missing environment variable returns None."""
        toml_content = """status = "${MISSING_VAR}"
"""
        toml_file = tmp_path / "config.toml"
        toml_file.write_text(toml_content)

        result = failable_load_toml_from_path(str(toml_file), is_env_var_substitution_enabled=True)

        assert result is None

        # Check that an error message was printed
        captured = capsys.readouterr()
        assert "Failed to parse TOML file" in captured.out
        assert "MISSING_VAR" in captured.out

    def testsubstitute_env_vars_with_special_chars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test substitution with special characters in values."""
        monkeypatch.setenv("SPECIAL_VAR", "value!@#$%^&*()")

        content = 'key = "${SPECIAL_VAR}"'
        result = substitute_env_vars(content)

        assert result == 'key = "value!@#$%^&*()"'

    def testsubstitute_env_vars_preserves_non_placeholders(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that non-placeholder strings are preserved."""
        monkeypatch.setenv("REAL_VAR", "replaced")

        content = """key1 = "${REAL_VAR}"
key2 = "not a ${placeholder"
key3 = "also not a placeholder}"
key4 = "$not_a_placeholder"
"""
        result = substitute_env_vars(content)

        expected = """key1 = "replaced"
key2 = "not a ${placeholder"
key3 = "also not a placeholder}"
key4 = "$not_a_placeholder"
"""
        assert result == expected

    def test_real_world_providers_toml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test with a real-world providers.toml example."""
        monkeypatch.setenv("AZURE_API_BASE", "https://my-azure.openai.azure.com")

        toml_content = """[pipelex_inference]
endpoint = "https://inference.pipelex.com/v1"

[azure_openai]
endpoint = "${AZURE_API_BASE}"

[blackboxai]
endpoint = "https://api.blackbox.ai/v1"
"""
        toml_file = tmp_path / "providers.toml"
        toml_file.write_text(toml_content)

        result = load_toml_from_path(str(toml_file), is_env_var_substitution_enabled=True)

        assert result["pipelex_inference"]["endpoint"] == "https://inference.pipelex.com/v1"
        assert result["azure_openai"]["endpoint"] == "https://my-azure.openai.azure.com"
        assert result["blackboxai"]["endpoint"] == "https://api.blackbox.ai/v1"
