import importlib.util
import inspect
from typing import Any

from typing_extensions import override

from pipelex.system.exceptions import MissingDependencyError
from pipelex.tools.storage.exceptions import (
    StorageFileNotFoundError,
    StorageS3Error,
)
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract, StoredData


class S3StorageProvider(StorageProviderAbstract):
    """Storage provider implementation for AWS S3 storage.

    Files are stored in an S3 bucket with keys being path strings.
    Uses aioboto3 for async S3 operations.
    """

    def __init__(
        self,
        bucket_name: str,
        region: str,
        signed_urls_lifespan: int | None,
    ) -> None:
        """Initialize the S3 storage provider.

        Args:
            bucket_name: The S3 bucket name.
            region: The AWS region.
            signed_urls_lifespan: Lifespan in seconds for signed URLs, or None if disabled.
        """
        self._bucket_name = bucket_name
        self._region = region
        self._signed_urls_lifespan = signed_urls_lifespan
        self._session: Any = None

    def _check_dependency(self) -> None:
        """Check if aioboto3 is installed.

        Raises:
            MissingDependencyError: If aioboto3 is not installed.
        """
        if importlib.util.find_spec("aioboto3") is None:
            lib_name = "aioboto3"
            lib_extra_name = "s3"
            msg = "aioboto3 is required for S3 storage."
            raise MissingDependencyError(
                lib_name,
                lib_extra_name,
                msg,
            )

    def _get_session(self) -> Any:
        """Get or create the aioboto3 session (lazy initialization).

        Returns:
            The aioboto3 Session.
        """
        self._check_dependency()

        if self._session is None:
            import aioboto3  # noqa: PLC0415 - optional dependency, lazy import

            self._session = aioboto3.Session()  # pyright: ignore[reportUnknownMemberType]
        return self._session

    def _get_client_config(self) -> dict[str, Any]:
        """Get the configuration for creating S3 clients.

        Returns:
            Dictionary of client configuration parameters.
        """
        from botocore.config import Config  # noqa: PLC0415 - optional dependency, lazy import

        endpoint_url = f"https://s3.{self._region}.amazonaws.com"
        config = Config(signature_version="s3v4")  # pyright: ignore[reportUnknownArgumentType]

        return {
            "service_name": "s3",
            "region_name": self._region,
            "endpoint_url": endpoint_url,
            "config": config,
        }

    @override
    async def _load_with_metadata(self, key: str) -> StoredData:
        """Load bytes from an S3 object with MIME type metadata.

        Args:
            key: Storage key (without scheme prefix).

        Returns:
            StoredData containing object contents and ContentType.

        Raises:
            StorageFileNotFoundError: If the object does not exist.
            StorageS3Error: If the S3 operation fails.
        """
        from botocore.exceptions import (  # noqa: PLC0415 - optional dependency, lazy import
            ClientError,
            EndpointConnectionError,
            NoCredentialsError,
        )

        session = self._get_session()
        client_config = self._get_client_config()

        async with session.client(**client_config) as client:  # pyright: ignore[reportUnknownMemberType]
            try:
                response = await client.get_object(Bucket=self._bucket_name, Key=key)
                async with response["Body"] as stream:
                    data: bytes = await stream.read()
                # Extract ContentType from S3 response
                content_type: str | None = response.get("ContentType")
                return StoredData(data=data, mime_type=content_type)
            except client.exceptions.NoSuchKey as exc:
                msg = f"Object not found in S3: '{key}'"
                raise StorageFileNotFoundError(msg) from exc
            except client.exceptions.NoSuchBucket as exc:
                msg = f"Bucket not found in S3: '{self._bucket_name}'"
                raise StorageS3Error(msg) from exc
            except ClientError as exc:
                error_code = (exc.response.get("Error") or {}).get("Code", "Unknown")
                if error_code == "NoSuchKey":
                    msg = f"Object not found in S3: '{key}'"
                    raise StorageFileNotFoundError(msg) from exc
                msg = f"S3 ClientError ({error_code}) for key '{key}'"
                raise StorageS3Error(msg) from exc
            except (NoCredentialsError, EndpointConnectionError) as exc:
                msg = f"S3 connectivity/credentials error for key '{key}'"
                raise StorageS3Error(msg) from exc

    @override
    async def _store(self, data: bytes, *, key: str, content_type: str | None) -> None:
        """Store bytes to an S3 object.

        Args:
            data: The bytes to store.
            key: Storage key (without scheme prefix).
            content_type: Optional MIME type for the object.

        Raises:
            StorageS3Error: If the S3 operation fails.
        """
        from botocore.exceptions import (  # noqa: PLC0415 - optional dependency, lazy import
            ClientError,
            EndpointConnectionError,
            NoCredentialsError,
        )

        session = self._get_session()
        client_config = self._get_client_config()

        async with session.client(**client_config) as client:  # pyright: ignore[reportUnknownMemberType]
            try:
                put_params: dict[str, Any] = {
                    "Bucket": self._bucket_name,
                    "Key": key,
                    "Body": data,
                }
                if content_type:
                    put_params["ContentType"] = content_type
                await client.put_object(**put_params)
            except client.exceptions.NoSuchBucket as exc:
                msg = f"Bucket not found in S3: '{self._bucket_name}'"
                raise StorageS3Error(msg) from exc
            except ClientError as exc:
                error_code = (exc.response.get("Error") or {}).get("Code", "Unknown")
                msg = f"S3 ClientError ({error_code}) for key '{key}'"
                raise StorageS3Error(msg) from exc
            except (NoCredentialsError, EndpointConnectionError) as exc:
                msg = f"S3 connectivity/credentials error for key '{key}'"
                raise StorageS3Error(msg) from exc

    def _make_public_url(self, key: str) -> str:
        """Build a public URL for an S3 object.

        Args:
            key: Storage key (without scheme prefix).

        Returns:
            Public URL for the object.
        """
        return f"https://{self._bucket_name}.s3.{self._region}.amazonaws.com/{key}"

    @override
    async def display_link(self, uri: str) -> str | None:
        """Return a URL for this storage URI.

        Args:
            uri: Full URI including pipelex-storage:// scheme.

        Returns:
            Presigned URL if signed_urls_lifespan is configured, otherwise a public URL.
        """
        from botocore.exceptions import ClientError  # noqa: PLC0415 - optional dependency, lazy import

        key = self._strip_scheme(uri)

        if self._signed_urls_lifespan is None:
            return self._make_public_url(key)

        session = self._get_session()
        client_config = self._get_client_config()

        async with session.client(**client_config) as client:  # pyright: ignore[reportUnknownMemberType]
            try:
                # generate_presigned_url may be sync or async depending on aioboto3 version
                maybe_url = client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self._bucket_name, "Key": key},
                    ExpiresIn=self._signed_urls_lifespan,
                )
                presigned_url: str = await maybe_url if inspect.isawaitable(maybe_url) else maybe_url
                return presigned_url
            except ClientError:
                return self._make_public_url(key)
