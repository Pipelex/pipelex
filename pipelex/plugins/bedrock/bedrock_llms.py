from typing import Any, cast

from pipelex.cogt.exceptions import MissingDependencyError
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.config import get_config
from pipelex.plugins.plugin_sdk_registry import Plugin
from pipelex.tools.aws.aws_config import AwsCredentialsError


async def bedrock_list_available_models(
    plugin: Plugin,  # noqa: ARG001
    backend: InferenceBackend,  # noqa: ARG001
) -> list[dict[str, Any]]:
    """List available Bedrock foundation models.

    Args:
        plugin: The plugin configuration (unused, kept for interface consistency)
        backend: The inference backend configuration (unused, kept for interface consistency)

    Returns:
        List of model summaries from Bedrock

    Raises:
        AwsCredentialsError: If AWS credentials cannot be retrieved
        MissingDependencyError: If boto3 is not installed
    """
    try:
        aws_config = get_config().pipelex.aws_config
        aws_access_key_id, aws_secret_access_key, aws_region = aws_config.get_aws_access_keys()
    except AwsCredentialsError as exc:
        msg = f"Error getting AWS credentials for Bedrock: {exc}"
        raise AwsCredentialsError(msg) from exc

    try:
        import boto3  # noqa: PLC0415
    except ImportError as exc:
        lib_name = "boto3,aioboto3"
        lib_extra_name = "bedrock"
        msg = "The boto3 and aioboto3 SDKs are required to use Bedrock models."
        raise MissingDependencyError(
            lib_name,
            lib_extra_name,
            msg,
        ) from exc

    # Create bedrock client
    bedrock_client: Any = boto3.client(  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
        "bedrock",
        region_name=aws_region,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
    )

    # List foundation models
    response: dict[str, Any] = bedrock_client.list_foundation_models()  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]

    return cast("list[dict[str, Any]]", response.get("modelSummaries", []))  # pyright: ignore[reportUnknownArgumentType,reportUnknownMemberType]
