from typing import Any, Dict, Tuple

from pipelex.cogt.exceptions import CogtError, MissingDependencyError
from pipelex.tools.config.config_model import ConfigModel
from pipelex.tools.exceptions import CredentialsError
from pipelex.tools.misc.json_utils import load_json_dict_from_path
from pipelex.types import StrEnum


class VertexAIConfigError(CogtError):
    pass


class VertexAICredentialsError(CredentialsError):
    pass


class VertexAIExtraField(StrEnum):
    GCP_PROJECT_ID = "gcp_project_id"
    GCP_LOCATION = "gcp_location"
    GCP_CREDENTIALS_FILE_PATH = "gcp_credentials_file_path"


class VertexAIFactory(ConfigModel):
    @classmethod
    def make_endpoint_and_api_key(
        cls,
        extra_config: Dict[str, Any],
    ) -> Tuple[str, str]:
        """Configure and return endpoint, and API key."""
        gcp_project_id = extra_config.get(VertexAIExtraField.GCP_PROJECT_ID)
        if not gcp_project_id:
            raise VertexAIConfigError("GCP project ID is not set in VertexAI config")

        gcp_location = extra_config.get(VertexAIExtraField.GCP_LOCATION)
        if not gcp_location:
            raise VertexAIConfigError("GCP location is not set in VertexAI config")

        endpoint = cls._make_endpoint(gcp_project_id=gcp_project_id, gcp_location=gcp_location)

        gcp_credentials_file_path = extra_config.get(VertexAIExtraField.GCP_CREDENTIALS_FILE_PATH)
        if not gcp_credentials_file_path:
            raise VertexAIConfigError("GCP credentials file path is not set in VertexAI config")

        api_key = cls._make_api_key(gcp_credentials_file_path=gcp_credentials_file_path)

        return endpoint, api_key

    @classmethod
    def _make_endpoint(cls, gcp_project_id: str, gcp_location: str) -> str:
        return f"https://{gcp_location}-aiplatform.googleapis.com/v1beta1/projects/{gcp_project_id}/locations/{gcp_location}/endpoints/openapi"

    @classmethod
    def _make_api_key(cls, gcp_credentials_file_path: str) -> str:
        """Get GCP credentials and return access token."""
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.service_account import Credentials
        except ImportError as exc:
            raise MissingDependencyError(
                "google-auth-oauthlib",
                "google",
                (
                    "The google-auth-oauthlib SDK is required to use Google connection. "
                    "You can install it with 'pip install pipelex[google]', or use this model via another provider "
                    "(such as Azure OpenAI, OpenAI, anthropic or bedrock)."
                ),
            ) from exc

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
