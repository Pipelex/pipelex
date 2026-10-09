import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.model_backends.backend_credentials import (
    HOSTED_RUNS_HINT,
    BackendCredentialsErrorMsgFactory,
    BackendCredentialsReport,
)
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract

BYOK_HINT = (
    "\n🔑 Bring your own keys:\n"
    "   Set your own provider keys (OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY,\n"
    "   MISTRAL_API_KEY, AZURE_API_KEY, OPENROUTER_API_KEY, etc.) and enable the corresponding\n"
    "   backends in '.pipelex/inference/backends.toml'.\n"
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
            "   Add 'enabled = false' under '[openai]' in '.pipelex/inference/backends.toml'\n" + BYOK_HINT
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
            "   Add 'enabled = false' under '[anthropic]' in '.pipelex/inference/backends.toml'\n" + BYOK_HINT
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
            "   - Add 'enabled = false' under '[openai]'\n" + BYOK_HINT
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
        assert "   - Add 'enabled = false' under '[mistral]'\n" in error_msg

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
        assert "   - Add 'enabled = false' under '[openai]'\n" in error_msg
        assert "   - Add 'enabled = false' under '[azure]'\n" in error_msg

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
            "   - Add 'enabled = false' under '[anthropic]'\n"
            "   - Add 'enabled = false' under '[bedrock]'\n" + BYOK_HINT
        )
        assert error_msg == expected_msg

    @pytest.mark.parametrize("suggest_hosted_runs", [True, False])
    def test_one_variable_missing_offers_hosted_runs_only_when_asked(self, suggest_hosted_runs: bool):
        """A command-line caller gets the hosted Pipelex API as the last way out, after the BYOK hint; the default leaves it out."""
        error_msg = BackendCredentialsErrorMsgFactory.make_one_variable_missing_error_msg(
            secrets_provider=EnvSecretsProvider(),
            backend_name="openai",
            var_name="OPENAI_API_KEY",
            suggest_hosted_runs=suggest_hosted_runs,
        )
        assert error_msg.endswith(BYOK_HINT + HOSTED_RUNS_HINT) is suggest_hosted_runs
        assert ("pipelex login" in error_msg) is suggest_hosted_runs

    @pytest.mark.parametrize("suggest_hosted_runs", [True, False])
    def test_comprehensive_offers_hosted_runs_only_when_asked(self, suggest_hosted_runs: bool):
        """The doctor's report offers the hosted Pipelex API after the BYOK hint; the default leaves it out."""
        reports = {"openai": make_report(backend_name="openai", missing_vars=["OPENAI_API_KEY"], placeholder_vars=[])}
        error_msg = BackendCredentialsErrorMsgFactory.make_comprehensive_error_msg(
            backend_credential_reports=reports,
            secrets_provider=EnvSecretsProvider(),
            suggest_hosted_runs=suggest_hosted_runs,
        )
        assert error_msg.endswith(BYOK_HINT + HOSTED_RUNS_HINT) is suggest_hosted_runs
        assert ("--hosted" in error_msg) is suggest_hosted_runs

    def test_hosted_runs_hint_names_the_login_and_the_setting(self):
        assert "pipelex login" in HOSTED_RUNS_HINT
        assert 'execution = "hosted"' in HOSTED_RUNS_HINT

    @pytest.mark.parametrize("secrets_provider_kind", ["env", "generic_mock"])
    def test_every_message_names_the_table_as_written_with_no_markup_escape(self, mocker: MockerFixture, secrets_provider_kind: str):
        r"""The messages are plain text: a Rich escape in them reached the user as `\[openai]` wherever nothing read them as markup."""
        secrets_provider: SecretsProviderAbstract
        if secrets_provider_kind == "env":
            secrets_provider = EnvSecretsProvider()
        else:
            secrets_provider = mocker.MagicMock(spec=SecretsProviderAbstract)
        reports = {"openai": make_report(backend_name="openai", missing_vars=["OPENAI_API_KEY"], placeholder_vars=[])}
        messages = [
            BackendCredentialsErrorMsgFactory.make_one_variable_missing_error_msg(
                secrets_provider=secrets_provider, backend_name="openai", var_name="OPENAI_API_KEY", suggest_hosted_runs=True
            ),
            BackendCredentialsErrorMsgFactory.make_comprehensive_error_msg(
                backend_credential_reports=reports, secrets_provider=secrets_provider, suggest_hosted_runs=True
            ),
        ]
        for message in messages:
            assert "under '[openai]'" in message
            assert "\\" not in message
