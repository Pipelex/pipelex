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

    def test_load_toml_with_env_substitution_disabled(self, tmp_path: Path) -> None:
        """Test loading TOML with environment variable substitution disabled (default)."""
        toml_content = """database_host = "${DB_HOST}"
database_port = "${DB_PORT}"
"""
        toml_file = tmp_path / "config.toml"
        toml_file.write_text(toml_content)

        result = load_toml_from_path(str(toml_file))

        # Should keep the placeholders as-is
        assert result["database_host"] == "${DB_HOST}"
        assert result["database_port"] == "${DB_PORT}"

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
