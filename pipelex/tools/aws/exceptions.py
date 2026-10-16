from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.system.exceptions import CredentialsError


class AwsCredentialsError(CredentialsError):
    """Raised when the AWS credentials the configuration selects are not set."""

    error_code = PipelexErrorCode.CONFIG_CREDENTIAL_MISSING
