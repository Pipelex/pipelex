# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from enum import StrEnum
from typing import Any, Dict

from pipelex.cogt.exceptions import CogtError, MissingDependencyError
from pipelex.tools.config.models import ConfigModel
from pipelex.tools.environment import EnvVarNotFoundError, get_required_env
from pipelex.tools.utils.json_utils import load_json_dict_from_path


class VertexAICredentialsError(CogtError):
    pass


class VertexAIKeyMethod(StrEnum):
    SECRET_PROVIDER = "secret_provider"
    ENV = "env"


class VertexAIConfig(ConfigModel):
    project_id: str
    region: str

    def get_api_key(self) -> str:
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

        try:
            gcp_credentials_file_path = get_required_env("GCP_CREDENTIALS_FILE_PATH")
        except EnvVarNotFoundError as exc:
            raise VertexAICredentialsError("GCP_CREDENTIALS_FILE_PATH environment variable not found") from exc

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
