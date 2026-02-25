from pipelex.cogt.model_backends.backend import PipelexBackend
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract


class BackendCredentialsReport(ConfigModel):
    """Report of credential status for a backend."""

    backend_name: str
    required_vars: list[str]
    missing_vars: list[str]
    placeholder_vars: list[str]
    all_credentials_valid: bool


class CredentialsValidationReport(ConfigModel):
    """Complete report of credentials validation across all backends."""

    backend_reports: dict[str, BackendCredentialsReport]
    all_backends_valid: bool


class BackendCredentialsErrorMsgFactory:
    @classmethod
    def make_one_variable_missing_error_msg(
        cls,
        secrets_provider: SecretsProviderAbstract,
        backend_name: str,
        var_name: str,
    ) -> str:
        """Build an error message for a single missing credential variable.

        Args:
            secrets_provider: The secrets provider being used
            backend_name: Name of the backend with the missing credential
            var_name: Name of the missing variable
        """
        error_msg: str
        if isinstance(secrets_provider, EnvSecretsProvider):
            error_msg = (
                f"Could not get credentials for inference backend '{backend_name}':\n\n"
                f"Credential issue:\n  • '{backend_name}': missing '{var_name}'\n\n"
                "You have two options:\n\n"
                "1. Add the missing environment variable\n"
                f"   Add the variable to your environment or .env file:\n"
                f"   - '{var_name}'=<your_api_key>\n"
                "\n2. Disable this backend\n"
                rf"   Add 'enabled = false' under '\[{backend_name}]' in '.pipelex/inference/backends.toml'" + "\n"
            )
        else:
            error_msg = (
                f"Could not get credentials for inference backend '{backend_name}':\n\n"
                f"Credential issue:\n  • '{backend_name}': missing '{var_name}'\n\n"
                "You have two options:\n\n"
                "1. Provide the missing secret\n"
                f"   Make sure '{var_name}' is available from your secrets provider.\n"
                "\n2. Disable this backend\n"
                rf"   Add 'enabled = false' under '\[{backend_name}]' in '.pipelex/inference/backends.toml'" + "\n"
            )

        # Add pitch for Pipelex Gateway and BYOK (Bring Your Own Keys)
        error_msg += (
            f"\n💡 Tip: Get a free {PipelexBackend.GATEWAY.display_name} API key!\n"
            f"   With {PipelexBackend.GATEWAY.display_name}, you get unified access to multiple AI providers\n"
            "   (OpenAI, Anthropic, Google, Mistral, etc.) with a single API key.\n"
            "   Check the project's 'README.md' for details on obtaining your key.\n"
            "\n🔑 Or bring your own keys:\n"
            "   Set your own provider keys (OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY,\n"
            "   MISTRAL_API_KEY, AZURE_API_KEY, etc.) and enable the corresponding backends\n"
            "   in '.pipelex/inference/backends.toml'.\n"
        )

        return error_msg

    @classmethod
    def make_comprehensive_error_msg(
        cls,
        backend_credential_reports: dict[str, BackendCredentialsReport],
        secrets_provider: SecretsProviderAbstract | None = None,
    ) -> str:
        """Build a comprehensive error message for missing backend credentials.

        Args:
            secrets_provider: The secrets provider being used
            backend_credential_reports: Dict of backend_name -> credential report for backends with issues
        """
        # Build the details section for each backend with issues
        backend_details_lines: list[str] = []
        all_missing_vars: list[str] = []
        all_placeholder_vars: list[str] = []

        for backend_name, report in backend_credential_reports.items():
            issues: list[str] = []
            if report.missing_vars:
                all_missing_vars.extend(report.missing_vars)
                quoted_missing = [f"'{var}'" for var in report.missing_vars]
                issues.append(f"missing: {', '.join(quoted_missing)}")
            if report.placeholder_vars:
                all_placeholder_vars.extend(report.placeholder_vars)
                quoted_placeholders = [f"'{var}'" for var in report.placeholder_vars]
                issues.append(f"unresolved placeholders: {', '.join(quoted_placeholders)}")
            if issues:
                backend_details_lines.append(f"  • '{backend_name}': {'; '.join(issues)}")

        backend_details = "\n".join(backend_details_lines)
        backend_names = list(backend_credential_reports.keys())
        backends_list = ", ".join(f"'{name}'" for name in backend_names)

        error_msg: str
        if isinstance(secrets_provider, EnvSecretsProvider):
            error_msg = (
                f"Could not get credentials for inference backend(s): {backends_list}\n\n"
                f"Credential issues:\n{backend_details}\n\n"
                "You have two options:\n\n"
                "1. Add the missing environment variables\n"
                "   Add the missing variables to your environment or .env file:\n"
            )
            if all_missing_vars:
                for var_name in sorted(set(all_missing_vars)):
                    error_msg += f"   - '{var_name}'=<your_api_key>\n"
            if all_placeholder_vars:
                error_msg += "   (Also replace placeholder values like '${VAR}' with actual keys)\n"

            error_msg += "\n2. Disable unused backends\n   Disable backends you don't need in '.pipelex/inference/backends.toml':\n"
            for backend_name in backend_names:
                error_msg += rf"   - Add 'enabled = false' under '\[{backend_name}]'" + "\n"
        else:
            error_msg = (
                f"Could not get credentials for inference backend(s): {backends_list}\n\n"
                f"Credential issues:\n{backend_details}\n\n"
                "You have two options:\n\n"
                "1. Provide the missing secrets\n"
                "   Make sure the following secrets are available from your secrets provider:\n"
            )
            all_vars = sorted(set(all_missing_vars + all_placeholder_vars))
            for var_name in all_vars:
                error_msg += f"   - '{var_name}'\n"

            error_msg += "\n2. Disable unused backends\n   Disable backends you don't need in '.pipelex/inference/backends.toml':\n"
            for backend_name in backend_names:
                error_msg += rf"   - Add 'enabled = false' under '\[{backend_name}]'" + "\n"

        # Add pitch for Pipelex Gateway and BYOK (Bring Your Own Keys)
        error_msg += (
            f"\n💡 Tip: Get a free {PipelexBackend.GATEWAY.display_name} API key!\n"
            f"   With {PipelexBackend.GATEWAY.display_name}, you get unified access to multiple AI providers\n"
            "   (OpenAI, Anthropic, Google, Mistral, etc.) with a single API key.\n"
            "   Check the project's 'README.md' for details on obtaining your key.\n"
            "\n🔑 Or bring your own keys:\n"
            "   Set your own provider keys (OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY,\n"
            "   MISTRAL_API_KEY, AZURE_API_KEY, etc.) and enable the corresponding backends\n"
            "   in '.pipelex/inference/backends.toml'.\n"
        )

        return error_msg
