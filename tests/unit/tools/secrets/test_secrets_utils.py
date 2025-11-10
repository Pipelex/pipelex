import os
from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.tools.secrets.secrets_errors import SecretNotFoundError
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract
from pipelex.tools.secrets.secrets_utils import UnknownVarPrefixError, VarFallbackPatternError, VarNotFoundError, substitute_vars


@pytest.fixture
def mock_secrets_provider(mocker: MockerFixture) -> Any:
    """Mock secrets provider for testing."""
    return mocker.Mock(spec=SecretsProviderAbstract)


class TestSubstituteVars:
    def test_simple_secret_substitution(self, mock_secrets_provider: Any) -> None:
        mock_secrets_provider.get_secret.return_value = "secret_value"

        result = substitute_vars("Hello ${API_KEY}", mock_secrets_provider)

        assert result == "Hello secret_value"
        mock_secrets_provider.get_secret.assert_called_once_with(secret_id="API_KEY")

    def test_explicit_env_substitution(self, mocker: MockerFixture, mock_secrets_provider: Any) -> None:
        mocker.patch.dict(os.environ, {"TEST_VAR": "env_value"})
        result = substitute_vars("Value: ${env:TEST_VAR}", mock_secrets_provider)

        assert result == "Value: env_value"

    def test_explicit_secret_substitution(self, mock_secrets_provider: Any) -> None:
        mock_secrets_provider.get_secret.return_value = "secret_value"

        result = substitute_vars("Value: ${secret:API_KEY}", mock_secrets_provider)

        assert result == "Value: secret_value"
        mock_secrets_provider.get_secret.assert_called_once_with(secret_id="API_KEY")

    def test_fallback_env_to_secret(self, mock_secrets_provider: Any) -> None:
        mock_secrets_provider.get_secret.return_value = "secret_fallback"

        result = substitute_vars("Value: ${env:MISSING_VAR|secret:FALLBACK_KEY}", mock_secrets_provider)

        assert result == "Value: secret_fallback"
        mock_secrets_provider.get_secret.assert_called_once_with(secret_id="FALLBACK_KEY")

    def test_env_takes_precedence_in_fallback(self, mocker: MockerFixture, mock_secrets_provider: Any) -> None:
        mocker.patch.dict(os.environ, {"EXISTING_VAR": "env_value"})

        result = substitute_vars("Value: ${env:EXISTING_VAR|secret:FALLBACK_KEY}", mock_secrets_provider)

        assert result == "Value: env_value"
        # Secret should not be called since env var was found
        mock_secrets_provider.get_secret.assert_not_called()

    def test_fallback_secret_to_env(self, mocker: MockerFixture, mock_secrets_provider: Any) -> None:
        """Test fallback from secret to env when secret doesn't exist."""
        mock_secrets_provider.get_secret.side_effect = SecretNotFoundError("Secret not found")
        mocker.patch.dict(os.environ, {"FALLBACK_ENV": "env_fallback"})

        result = substitute_vars("Value: ${secret:MISSING_SECRET|env:FALLBACK_ENV}", mock_secrets_provider)

        assert result == "Value: env_fallback"
        mock_secrets_provider.get_secret.assert_called_once_with(secret_id="MISSING_SECRET")

    def test_secret_takes_precedence_in_reverse_fallback(self, mocker: MockerFixture, mock_secrets_provider: Any) -> None:
        """Test that secret takes precedence when both secret and env are available in reverse order."""
        mock_secrets_provider.get_secret.return_value = "secret_value"
        mocker.patch.dict(os.environ, {"EXISTING_VAR": "env_value"})

        result = substitute_vars("Value: ${secret:EXISTING_SECRET|env:EXISTING_VAR}", mock_secrets_provider)

        assert result == "Value: secret_value"
        mock_secrets_provider.get_secret.assert_called_once_with(secret_id="EXISTING_SECRET")

    def test_multiple_substitutions(self, mocker: MockerFixture, mock_secrets_provider: Any) -> None:
        """Test multiple variable substitutions in the same content."""
        mock_secrets_provider.get_secret.side_effect = lambda secret_id: f"secret_{secret_id}"  # pyright: ignore[reportUnknownLambdaType]
        mocker.patch.dict(os.environ, {"ENV_VAR": "env_value"})

        content = "API: ${API_KEY}, DB: ${env:ENV_VAR}, Token: ${secret:TOKEN}"
        result = substitute_vars(content, mock_secrets_provider)

        assert result == "API: secret_API_KEY, DB: env_value, Token: secret_TOKEN"

    def test_no_placeholders(self, mock_secrets_provider: Any) -> None:
        """Test content with no placeholders remains unchanged."""
        content = "This is just plain text with no variables"
        result = substitute_vars(content, mock_secrets_provider)
        assert result == content

    def test_missing_env_var_raises_error(self, mock_secrets_provider: Any) -> None:
        """Test that missing required env var raises VarNotFoundError."""
        with pytest.raises(VarNotFoundError, match="Environment variable 'MISSING_VAR' is required but not set"):
            substitute_vars("Value: ${env:MISSING_VAR}", mock_secrets_provider)

    def test_missing_secret_raises_error(self, mock_secrets_provider: Any) -> None:
        """Test that missing required secret raises error."""
        mock_secrets_provider.get_secret.side_effect = SecretNotFoundError("Secret not found")

        with pytest.raises(VarNotFoundError, match="Could not get variable 'MISSING_SECRET': Secret not found"):
            substitute_vars("Value: ${secret:MISSING_SECRET}", mock_secrets_provider)

    def test_missing_default_secret_raises_error(self, mock_secrets_provider: Any) -> None:
        """Test that missing default secret (no prefix) raises error."""
        mock_secrets_provider.get_secret.side_effect = SecretNotFoundError("Secret not found")

        with pytest.raises(VarNotFoundError, match="Could not get variable 'MISSING_SECRET': Secret not found"):
            substitute_vars("Value: ${MISSING_SECRET}", mock_secrets_provider)

    def test_fallback_both_missing_raises_error(self, mock_secrets_provider: Any) -> None:
        mock_secrets_provider.get_secret.side_effect = SecretNotFoundError("Secret not found")

        with pytest.raises(VarFallbackPatternError, match="Could not get variable from fallback pattern: env:MISSING_ENV\\|secret:MISSING_SECRET"):
            substitute_vars("Value: ${env:MISSING_ENV|secret:MISSING_SECRET}", mock_secrets_provider)

    def test_reverse_fallback_both_missing_raises_error(self, mock_secrets_provider: Any) -> None:
        """Test that when both secret and env are missing in reverse order, error is raised."""
        mock_secrets_provider.get_secret.side_effect = SecretNotFoundError("Secret not found")

        with pytest.raises(VarFallbackPatternError, match="Could not get variable from fallback pattern: secret:MISSING_SECRET\\|env:MISSING_ENV"):
            substitute_vars("Value: ${secret:MISSING_SECRET|env:MISSING_ENV}", mock_secrets_provider)

    def test_complex_variable_names(self, mocker: MockerFixture, mock_secrets_provider: Any) -> None:
        """Test complex variable names with underscores, numbers, etc."""
        mock_secrets_provider.get_secret.return_value = "complex_secret"
        mocker.patch.dict(os.environ, {"API_KEY_V2": "complex_env"})

        result = substitute_vars("${env:API_KEY_V2} and ${DB_PASSWORD_123}", mock_secrets_provider)

        assert result == "complex_env and complex_secret"

    def test_whitespace_handling(self, mock_secrets_provider: Any) -> None:
        """Test that whitespace around variable names is handled correctly."""
        mock_secrets_provider.get_secret.return_value = "secret_value"

        # Note: whitespace should be preserved as part of the variable name
        result = substitute_vars("Value: ${ API_KEY }", mock_secrets_provider)

        assert result == "Value: secret_value"
        mock_secrets_provider.get_secret.assert_called_once_with(secret_id=" API_KEY ")

    def test_nested_braces_not_matched(self, mock_secrets_provider: Any) -> None:
        """Test that nested braces are not matched by the pattern."""
        # The content has nested braces that should not be matched as a single variable
        # But ${nested} should be matched as a valid variable
        mock_secrets_provider.get_secret.return_value = "secret_nested"

        content = "This ${has ${nested} braces} should not match"
        result = substitute_vars(content, mock_secrets_provider)

        # The ${nested} part should be substituted, but ${has ... should not be matched
        # because it contains a $ character which breaks the pattern
        assert result == "This ${has secret_nested braces} should not match"
        mock_secrets_provider.get_secret.assert_called_once_with(secret_id="nested")

    def test_multiline_content(self, mocker: MockerFixture, mock_secrets_provider: Any) -> None:
        """Test substitution in multiline content."""
        mock_secrets_provider.get_secret.return_value = "secret_value"
        mocker.patch.dict(os.environ, {"HOME": "/home/user"})

        content = """Line 1: ${API_KEY}
Line 2: Some text
Line 3: ${env:HOME}"""
        result = substitute_vars(content, mock_secrets_provider)

        expected = """Line 1: secret_value
Line 2: Some text
Line 3: /home/user"""
        assert result == expected

    def test_pattern_does_not_match_across_newlines(self, mock_secrets_provider: Any) -> None:
        """Test that the pattern doesn't match variables that span multiple lines."""
        content = """This ${VAR
NAME} should not match"""
        result = substitute_vars(content, mock_secrets_provider)
        # Should remain unchanged
        assert result == content

    def test_pattern_does_not_match_with_quotes(self, mock_secrets_provider: Any) -> None:
        """Test that the pattern doesn't match variables containing quotes."""
        content = "This ${VAR\"NAME} and ${VAR'NAME} should not match"
        result = substitute_vars(content, mock_secrets_provider)
        # Should remain unchanged
        assert result == content

    def test_unknown_prefix_raises_error(self, mock_secrets_provider: Any) -> None:
        """Test that unknown prefix raises UnknownVarPrefixError."""
        with pytest.raises(UnknownVarPrefixError, match="Unknown variable prefix: 'foo'"):
            substitute_vars("Value: ${foo:BAR}", mock_secrets_provider)
