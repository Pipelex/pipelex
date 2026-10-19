from pipelex.cogt.exceptions import CogtError
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.system.exceptions import CredentialsError


class AzureCredentialsError(CredentialsError):
    """An Azure backend with no API key configured."""

    error_code = PipelexErrorCode.CONFIG_CREDENTIAL_MISSING


class AzureWorkerConfigurationError(CogtError):
    """An Azure backend missing a setting its worker requires, such as its ``api_version``."""

    error_code = PipelexErrorCode.CONFIG_INVALID
