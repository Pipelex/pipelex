from typing import Any, Dict, Tuple

from pydantic import Field

from pipelex import log
from pipelex.cogt.exceptions import CogtError, MissingDependencyError
from pipelex.tools.config.models import ConfigModel
from pipelex.tools.environment import EnvVarNotFoundError, get_required_env
from pipelex.tools.misc.json_utils import load_json_dict_from_path
from pipelex.tools.secrets.secrets_errors import SecretNotFoundError
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract
from pipelex.types import StrEnum


class VertexAICredentialsError(CogtError):
    pass


class VertexAIKeyMethod(StrEnum):
    SECRET_PROVIDER = "secret_provider"
    ENV = "env"


GCP_PROJECT_ID_VAR_NAME = "GCP_PROJECT_ID"
GCP_REGION_VAR_NAME = "GCP_REGION"
GCP_CREDENTIALS_FILE_PATH_VAR_NAME = "GCP_CREDENTIALS_FILE_PATH"


class VertexAIConfig(ConfigModel):
    api_key_method: VertexAIKeyMethod = Field(strict=False)

    def configure(self, secrets_provider: SecretsProviderAbstract) -> Tuple[str, str]:
        """Configure and return project ID, region, and API key."""
        project_id, region = self._get_project_settings(secrets_provider=secrets_provider)
        api_key = self._get_credentials()
        endpoint = f"https://{region}-aiplatform.googleapis.com/v1beta1/projects/{project_id}/locations/{region}/endpoints/openapi"
        return endpoint, api_key

    def _get_project_settings(self, secrets_provider: SecretsProviderAbstract) -> Tuple[str, str]:
        """Get project ID and region from environment or secrets provider."""
        match self.api_key_method:
            case VertexAIKeyMethod.ENV:
                log.debug("Getting GCP project settings from environment.")
                try:
                    project_id = get_required_env(GCP_PROJECT_ID_VAR_NAME)
                    region = get_required_env(GCP_REGION_VAR_NAME)
                    return project_id, region
                except EnvVarNotFoundError as exc:
                    raise VertexAICredentialsError(f"Error getting GCP project settings from environment: {exc}") from exc
            case VertexAIKeyMethod.SECRET_PROVIDER:
                log.verbose("Getting GCP project settings from secrets provider.")
                try:
                    project_id = secrets_provider.get_secret(secret_id=GCP_PROJECT_ID_VAR_NAME)
                    region = secrets_provider.get_secret(secret_id=GCP_REGION_VAR_NAME)
                    return project_id, region
                except SecretNotFoundError as exc:
                    raise VertexAICredentialsError("Error getting GCP project settings from secrets provider.") from exc

    def _get_credentials(self) -> str:
        """Get GCP credentials and return access token."""
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.service_account import Credentials
        except ImportError as exc:
            raise MissingDependencyError(
                "google-auth-oauthlib",
                "google",
                "The google-auth-oauthlib SDK is required to use Google connection. \
                You can install it with 'pip install pipelex[google]', or use this model via another provider \
                (such as Azure OpenAI, OpenAI, anthropic or bedrock).",
            ) from exc

        match self.api_key_method:
            case VertexAIKeyMethod.ENV:
                log.debug("Getting GCP credentials from environment.")
                try:
                    gcp_credentials_file_path = get_required_env(GCP_CREDENTIALS_FILE_PATH_VAR_NAME)
                except EnvVarNotFoundError as exc:
                    raise VertexAICredentialsError(f"{GCP_CREDENTIALS_FILE_PATH_VAR_NAME} environment variable not found") from exc
            case VertexAIKeyMethod.SECRET_PROVIDER:
                log.verbose("Getting GCP credentials from secrets provider.")
                try:
                    gcp_credentials_file_path = get_required_env(GCP_CREDENTIALS_FILE_PATH_VAR_NAME)
                except EnvVarNotFoundError as exc:
                    raise VertexAICredentialsError(f"{GCP_CREDENTIALS_FILE_PATH_VAR_NAME} environment variable not found") from exc

        try:
            credentials_dict: Dict[str, Any] = load_json_dict_from_path(path=gcp_credentials_file_path)
        except FileNotFoundError as exc:
            raise VertexAICredentialsError(f"File not found: {gcp_credentials_file_path}") from exc

        credentials = Credentials.from_service_account_info(  # pyright: ignore[reportUnknownMemberType]
            credentials_dict, scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        auth_req = Request()
        credentials.refresh(auth_req)  # pyright: ignore[reportUnknownMemberType]
        if not isinstance(credentials.token, str):  # pyright: ignore[reportUnknownMemberType]
            raise VertexAICredentialsError("Token is not a string")
        return credentials.token
