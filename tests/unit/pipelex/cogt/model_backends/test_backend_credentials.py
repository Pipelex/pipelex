import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.model_backends.backend_credentials import (
    BackendCredentialsErrorMsgFactory,
    BackendCredentialsReport,
    CredentialsValidationReport,
)
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract

GATEWAY_PITCH = (
    "\n💡 Tip: Get a free Pipelex Gateway API key!\n"
    "   With Pipelex Gateway, you get unified access to multiple AI providers\n"
    "   (OpenAI, Anthropic, Google, Mistral, etc.) with a single API key.\n"
    "   Check the project's 'README.md' for details on obtaining your key.\n"
    "\n🔑 Or bring your own keys:\n"
    "   Set your own provider keys (OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY,\n"
    "   MISTRAL_API_KEY, AZURE_API_KEY, etc.) and enable the corresponding backends\n"
    "   in '.pipelex/inference/backends.toml'.\n"
)


def make_report(
    backend_name: str,
    missing_vars: list[str],
    placeholder_vars: list[str],
) -> BackendCredentialsReport:
    return BackendCredentialsReport(
        backend_name=backend_name,
        required_vars=sorted(set(missing_vars) | set(placeholder_vars)),
        missing_vars=missing_vars,
        placeholder_vars=placeholder_vars,
        all_credentials_valid=not (missing_vars or placeholder_vars),
    )


class TestBackendCredentials:
    def test_backend_credentials_report_round_trip(self):
        """BackendCredentialsReport holds its constructed field values."""
        report = BackendCredentialsReport(
            backend_name="openai",
            required_vars=["OPENAI_API_KEY", "OPENAI_ORG_ID"],
            missing_vars=["OPENAI_API_KEY"],
            placeholder_vars=["OPENAI_ORG_ID"],
            all_credentials_valid=False,
        )
        assert report.backend_name == "openai"
        assert report.required_vars == ["OPENAI_API_KEY", "OPENAI_ORG_ID"]
        assert report.missing_vars == ["OPENAI_API_KEY"]
        assert report.placeholder_vars == ["OPENAI_ORG_ID"]
        assert report.all_credentials_valid is False

    def test_credentials_validation_report_round_trip(self):
        """CredentialsValidationReport holds its constructed field values."""
        valid_report = make_report(backend_name="anthropic", missing_vars=[], placeholder_vars=[])
        invalid_report = make_report(backend_name="openai", missing_vars=["OPENAI_API_KEY"], placeholder_vars=[])
        validation_report = CredentialsValidationReport(
            backend_reports={"anthropic": valid_report, "openai": invalid_report},
            all_backends_valid=False,
        )
        assert validation_report.backend_reports["anthropic"] == valid_report
        assert validation_report.backend_reports["openai"] == invalid_report
        assert validation_report.backend_reports["anthropic"].all_credentials_valid is True
        assert validation_report.all_backends_valid is False

    def test_one_variable_missing_env_provider(self):
        """The env-provider branch tells the user to add the variable to the environment or .env file."""
        error_msg = BackendCredentialsErrorMsgFactory.make_one_variable_missing_error_msg(
            secrets_provider=EnvSecretsProvider(),
            backend_name="openai",
            var_name="OPENAI_API_KEY",
        )
        expected_msg = (
            "Could not get credentials for inference backend 'openai':\n\n"
            "Credential issue:\n  • 'openai': missing 'OPENAI_API_KEY'\n\n"
            "You have two options:\n\n"
            "1. Add the missing environment variable\n"
            "   Add the variable to your environment or .env file:\n"
            "   - 'OPENAI_API_KEY'=<your_api_key>\n"
            "\n2. Disable this backend\n"
            "   Add 'enabled = false' under '\\[openai]' in '.pipelex/inference/backends.toml'\n" + GATEWAY_PITCH
        )
        assert error_msg == expected_msg

    def test_one_variable_missing_generic_provider(self, mocker: MockerFixture):
        """A non-env secrets provider gets the 'secrets provider' wording instead of .env guidance."""
        generic_provider = mocker.MagicMock(spec=SecretsProviderAbstract)
        error_msg = BackendCredentialsErrorMsgFactory.make_one_variable_missing_error_msg(
            secrets_provider=generic_provider,
            backend_name="anthropic",
            var_name="ANTHROPIC_API_KEY",
        )
        expected_msg = (
            "Could not get credentials for inference backend 'anthropic':\n\n"
            "Credential issue:\n  • 'anthropic': missing 'ANTHROPIC_API_KEY'\n\n"
            "You have two options:\n\n"
            "1. Provide the missing secret\n"
            "   Make sure 'ANTHROPIC_API_KEY' is available from your secrets provider.\n"
            "\n2. Disable this backend\n"
            "   Add 'enabled = false' under '\\[anthropic]' in '.pipelex/inference/backends.toml'\n" + GATEWAY_PITCH
        )
        assert error_msg == expected_msg
        assert ".env file" not in error_msg

    def test_comprehensive_env_missing_vars_only(self):
        """Env branch with only missing vars lists them sorted with the api-key hint and no placeholder note."""
        reports = {"openai": make_report(backend_name="openai", missing_vars=["OPENAI_API_KEY", "AZURE_API_KEY"], placeholder_vars=[])}
        error_msg = BackendCredentialsErrorMsgFactory.make_comprehensive_error_msg(
            backend_credential_reports=reports,
            secrets_provider=EnvSecretsProvider(),
        )
        expected_msg = (
            "Could not get credentials for inference backend(s): 'openai'\n\n"
            "Credential issues:\n  • 'openai': missing: 'OPENAI_API_KEY', 'AZURE_API_KEY'\n\n"
            "You have two options:\n\n"
            "1. Add the missing environment variables\n"
            "   Add the missing variables to your environment or .env file:\n"
            "   - 'AZURE_API_KEY'=<your_api_key>\n"
            "   - 'OPENAI_API_KEY'=<your_api_key>\n"
            "\n2. Disable unused backends\n"
            "   Disable backends you don't need in '.pipelex/inference/backends.toml':\n"
            "   - Add 'enabled = false' under '\\[openai]'\n" + GATEWAY_PITCH
        )
        assert error_msg == expected_msg

    def test_comprehensive_env_placeholder_vars_only(self):
        """Env branch with only placeholder vars flags unresolved placeholders and adds the replacement hint."""
        reports = {"mistral": make_report(backend_name="mistral", missing_vars=[], placeholder_vars=["MISTRAL_API_KEY"])}
        error_msg = BackendCredentialsErrorMsgFactory.make_comprehensive_error_msg(
            backend_credential_reports=reports,
            secrets_provider=EnvSecretsProvider(),
        )
        assert "  • 'mistral': unresolved placeholders: 'MISTRAL_API_KEY'" in error_msg
        assert "   (Also replace placeholder values like '${VAR}' with actual keys)\n" in error_msg
        assert "=<your_api_key>" not in error_msg
        assert "   - Add 'enabled = false' under '\\[mistral]'\n" in error_msg

    def test_comprehensive_env_both_kinds_one_backend(self):
        """Missing and placeholder issues on one backend are joined with a semicolon on its detail line."""
        reports = {"openai": make_report(backend_name="openai", missing_vars=["VAR_AAA"], placeholder_vars=["VAR_BBB"])}
        error_msg = BackendCredentialsErrorMsgFactory.make_comprehensive_error_msg(
            backend_credential_reports=reports,
            secrets_provider=EnvSecretsProvider(),
        )
        assert "  • 'openai': missing: 'VAR_AAA'; unresolved placeholders: 'VAR_BBB'" in error_msg
        assert "   - 'VAR_AAA'=<your_api_key>\n" in error_msg
        assert "   (Also replace placeholder values like '${VAR}' with actual keys)\n" in error_msg

    def test_comprehensive_env_multiple_backends_dedupes_and_sorts(self):
        """Each backend gets a disable line; duplicate missing vars across backends are deduped and sorted."""
        reports = {
            "openai": make_report(backend_name="openai", missing_vars=["SHARED_KEY", "OPENAI_API_KEY"], placeholder_vars=[]),
            "azure": make_report(backend_name="azure", missing_vars=["SHARED_KEY", "AZURE_API_KEY"], placeholder_vars=[]),
        }
        error_msg = BackendCredentialsErrorMsgFactory.make_comprehensive_error_msg(
            backend_credential_reports=reports,
            secrets_provider=EnvSecretsProvider(),
        )
        assert "Could not get credentials for inference backend(s): 'openai', 'azure'" in error_msg
        assert error_msg.count("   - 'SHARED_KEY'=<your_api_key>\n") == 1
        azure_var_pos = error_msg.index("   - 'AZURE_API_KEY'=<your_api_key>\n")
        openai_var_pos = error_msg.index("   - 'OPENAI_API_KEY'=<your_api_key>\n")
        shared_var_pos = error_msg.index("   - 'SHARED_KEY'=<your_api_key>\n")
        assert azure_var_pos < openai_var_pos < shared_var_pos
        assert "   - Add 'enabled = false' under '\\[openai]'\n" in error_msg
        assert "   - Add 'enabled = false' under '\\[azure]'\n" in error_msg

    @pytest.mark.parametrize("provider_kind", ["none", "generic_mock"])
    def test_comprehensive_non_env_provider(self, mocker: MockerFixture, provider_kind: str):
        """Non-env branch asks to provide secrets and merges missing + placeholder vars into one sorted list."""
        secrets_provider: SecretsProviderAbstract | None
        if provider_kind == "none":
            secrets_provider = None
        else:
            secrets_provider = mocker.MagicMock(spec=SecretsProviderAbstract)
        reports = {
            "anthropic": make_report(backend_name="anthropic", missing_vars=["ANTHROPIC_API_KEY"], placeholder_vars=[]),
            "bedrock": make_report(backend_name="bedrock", missing_vars=[], placeholder_vars=["AWS_REGION"]),
        }
        error_msg = BackendCredentialsErrorMsgFactory.make_comprehensive_error_msg(
            backend_credential_reports=reports,
            secrets_provider=secrets_provider,
        )
        expected_msg = (
            "Could not get credentials for inference backend(s): 'anthropic', 'bedrock'\n\n"
            "Credential issues:\n"
            "  • 'anthropic': missing: 'ANTHROPIC_API_KEY'\n"
            "  • 'bedrock': unresolved placeholders: 'AWS_REGION'\n\n"
            "You have two options:\n\n"
            "1. Provide the missing secrets\n"
            "   Make sure the following secrets are available from your secrets provider:\n"
            "   - 'ANTHROPIC_API_KEY'\n"
            "   - 'AWS_REGION'\n"
            "\n2. Disable unused backends\n"
            "   Disable backends you don't need in '.pipelex/inference/backends.toml':\n"
            "   - Add 'enabled = false' under '\\[anthropic]'\n"
            "   - Add 'enabled = false' under '\\[bedrock]'\n" + GATEWAY_PITCH
        )
        assert error_msg == expected_msg
