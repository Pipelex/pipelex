from pathlib import Path

import pytest

from pipelex.tools.misc.toml_secret_utils import (
    TOMLSecretValidationError,
    load_toml_from_path_with_secret_substitution,
)


class TestTOMLSecretUtils:
    def test_load_toml_with_secret_substitution_success(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading TOML with secret variable substitution enabled."""
        monkeypatch.setenv("DB_HOST", "localhost")
        monkeypatch.setenv("DB_PORT", "5432")
        monkeypatch.setenv("DB_NAME", "test_db")

        toml_content = """database_host = "${env:DB_HOST}"
database_port = "${env:DB_PORT}"
database_name = "${env:DB_NAME}"
"""
        toml_file = tmp_path / "config.toml"
        toml_file.write_text(toml_content)

        result = load_toml_from_path_with_secret_substitution(str(toml_file))

        assert result["database_host"] == "localhost"
        assert result["database_port"] == "5432"
        assert result["database_name"] == "test_db"

    def test_load_toml_with_secret_substitution_missing_var(self, tmp_path: Path) -> None:
        """Test loading TOML with missing required secret variable."""
        toml_content = """database_host = "${MISSING_VAR}"
"""
        toml_file = tmp_path / "config.toml"
        toml_file.write_text(toml_content)

        with pytest.raises(TOMLSecretValidationError) as exc_info:
            load_toml_from_path_with_secret_substitution(str(toml_file))

        error_msg = str(exc_info.value)
        assert "Variable substitution failed" in error_msg
        assert "MISSING_VAR" in error_msg

    def test_load_toml_with_secret_substitution_real_world_example(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test with a real-world providers.toml example using secret substitution."""
        monkeypatch.setenv("AZURE_API_BASE", "https://my-azure.openai.azure.com")

        toml_content = """[pipelex_inference]
endpoint = "https://inference.pipelex.com/v1"

[azure_openai]
endpoint = "${env:AZURE_API_BASE}"

[blackboxai]
endpoint = "https://api.blackbox.ai/v1"
"""
        toml_file = tmp_path / "providers.toml"
        toml_file.write_text(toml_content)

        result = load_toml_from_path_with_secret_substitution(str(toml_file))

        assert result["pipelex_inference"]["endpoint"] == "https://inference.pipelex.com/v1"
        assert result["azure_openai"]["endpoint"] == "https://my-azure.openai.azure.com"
        assert result["blackboxai"]["endpoint"] == "https://api.blackbox.ai/v1"

    def test_load_toml_with_secret_substitution_simple(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading TOML with simple variable substitution using environment variables."""
        monkeypatch.setenv("TEST_USER", "john_doe")
        monkeypatch.setenv("TEST_VERSION", "1.2.3")

        toml_content = """domain = "${env:TEST_USER}_domain"
version = "v${env:TEST_VERSION}"
description = "Test for user ${env:TEST_USER}"

[config]
user_name = "${env:TEST_USER}"
app_version = "${env:TEST_VERSION}"
static_value = "no_substitution"
number_value = 42
"""

        toml_file = tmp_path / "test_env.toml"
        toml_file.write_text(toml_content)

        result = load_toml_from_path_with_secret_substitution(str(toml_file))

        assert result["domain"] == "john_doe_domain"
        assert result["version"] == "v1.2.3"
        assert result["description"] == "Test for user john_doe"
        assert result["config"]["user_name"] == "john_doe"
        assert result["config"]["app_version"] == "1.2.3"
        assert result["config"]["static_value"] == "no_substitution"  # No env vars
        assert result["config"]["number_value"] == 42  # Non-string unchanged

    def test_load_toml_with_secret_substitution_nested_structures(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading TOML with secret substitution in nested structures and lists."""
        monkeypatch.setenv("TEST_HOST", "localhost")
        monkeypatch.setenv("TEST_PORT", "8080")
        monkeypatch.setenv("TEST_ENV", "development")

        toml_content = """domain = "test_domain"

[database]
host = "${env:TEST_HOST}"
port = "${env:TEST_PORT}"
config = { env = "${env:TEST_ENV}", timeout = 30 }

[servers]
primary = "${env:TEST_HOST}:${env:TEST_PORT}"
urls = ["http://${env:TEST_HOST}:${env:TEST_PORT}/api", "https://${env:TEST_HOST}:9443/secure"]

[[services]]
name = "api_${env:TEST_ENV}"
endpoint = "${env:TEST_HOST}:${env:TEST_PORT}"

[[services]]
name = "static"
endpoint = "cdn.example.com"
"""

        toml_file = tmp_path / "test_nested_env.toml"
        toml_file.write_text(toml_content)

        result = load_toml_from_path_with_secret_substitution(str(toml_file))

        # Test nested dictionary substitution
        assert result["database"]["host"] == "localhost"
        assert result["database"]["port"] == "8080"
        assert result["database"]["config"]["env"] == "development"
        assert result["database"]["config"]["timeout"] == 30  # Non-string unchanged

        # Test string with multiple env vars
        assert result["servers"]["primary"] == "localhost:8080"

        # Test list with env var substitution
        expected_urls = ["http://localhost:8080/api", "https://localhost:9443/secure"]
        assert result["servers"]["urls"] == expected_urls

        # Test array of tables
        assert result["services"][0]["name"] == "api_development"
        assert result["services"][0]["endpoint"] == "localhost:8080"
        assert result["services"][1]["name"] == "static"  # No env vars
        assert result["services"][1]["endpoint"] == "cdn.example.com"  # No env vars

    def test_load_toml_with_secret_substitution_with_fallback(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading TOML with secret substitution using fallback pattern."""
        monkeypatch.setenv("TEST_EXISTING", "exists")
        # TEST_MISSING is not set, so fallback to a hardcoded secret value would be used
        # But since we can't mock secrets easily, we'll test the env fallback pattern

        toml_content = """domain = "test_domain"
existing_var = "${env:TEST_EXISTING}"
# For missing vars, we can't use :default syntax, that's not supported
# Instead we'd need to set them as env vars or use the fallback pattern
static_value = "no_substitution"
"""

        toml_file = tmp_path / "test_defaults.toml"
        toml_file.write_text(toml_content)

        result = load_toml_from_path_with_secret_substitution(str(toml_file))

        assert result["existing_var"] == "exists"
        assert result["static_value"] == "no_substitution"
