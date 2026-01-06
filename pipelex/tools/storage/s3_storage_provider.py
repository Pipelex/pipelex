import importlib.util
from typing import Any

from typing_extensions import override

from pipelex.system.exceptions import MissingDependencyError
from pipelex.tools.storage.exceptions import (
    StorageFileNotFoundError,
    StorageS3Error,
)
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract


class S3StorageProvider(StorageProviderAbstract):
    """Storage provider implementation for AWS S3 storage.

    Files are stored in an S3 bucket with keys being path strings.
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
        self._s3_client: Any = None

    def _get_client(self) -> Any:
        """Get or create the S3 client (lazy initialization).

        Returns:
            The boto3 S3 client.

        Raises:
            MissingDependencyError: If boto3 is not installed.
        """
        if self._s3_client is None:
            if importlib.util.find_spec("boto3") is None:
                lib_name = "boto3"
                lib_extra_name = "s3"
                msg = "boto3 is required for S3 storage."
                raise MissingDependencyError(
                    lib_name,
                    lib_extra_name,
                    msg,
                )

            import boto3  # noqa: PLC0415 - optional dependency, lazy import

            self._s3_client = boto3.client("s3", region_name=self._region)  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
        return self._s3_client  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType]

    @override
    def _load(self, key: str) -> bytes:
        """Load bytes from an S3 object.

        Args:
            key: Storage key (without scheme prefix).

        Returns:
            The object contents as bytes.

        Raises:
            StorageFileNotFoundError: If the object does not exist.
            StorageS3Error: If the S3 operation fails.
        """
        client = self._get_client()

        try:
            response = client.get_object(Bucket=self._bucket_name, Key=key)
            data: bytes = response["Body"].read()
            return data
        except client.exceptions.NoSuchKey as exc:
            msg = f"Object not found in S3: '{key}'"
            raise StorageFileNotFoundError(msg) from exc
        except client.exceptions.NoSuchBucket as exc:
            msg = f"Bucket not found in S3: '{self._bucket_name}'"
            raise StorageS3Error(msg) from exc

    @override
    def _store(self, data: bytes, *, key: str, content_type: str | None) -> None:
        """Store bytes to an S3 object.

        Args:
            data: The bytes to store.
            key: Storage key (without scheme prefix).
            content_type: Optional MIME type for the object.

        Raises:
            StorageS3Error: If the S3 operation fails.
        """
        client = self._get_client()

        try:
            put_params: dict[str, Any] = {
                "Bucket": self._bucket_name,
                "Key": key,
                "Body": data,
            }
            if content_type:
                put_params["ContentType"] = content_type
            client.put_object(**put_params)
        except client.exceptions.NoSuchBucket as exc:
            msg = f"Bucket not found in S3: '{self._bucket_name}'"
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
    def display_link(self, uri: str) -> str | None:
        """Return a URL for this storage URI.

        Args:
            uri: Full URI including pipelex-storage:// scheme.

        Returns:
            Presigned URL if signed_urls_lifespan is configured, otherwise a public URL.
        """
        key = self._strip_scheme(uri)

        if self._signed_urls_lifespan is None:
            return self._make_public_url(key)

        client = self._get_client()

        try:
            presigned_url: str = client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket_name, "Key": key},
                ExpiresIn=self._signed_urls_lifespan,
            )
            return presigned_url
        except client.exceptions.ClientError:
            return self._make_public_url(key)
