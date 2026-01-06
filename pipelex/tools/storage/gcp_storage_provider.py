import asyncio
import importlib.util
from datetime import timedelta
from pathlib import Path
from typing import Any

from google.api_core.exceptions import GoogleAPIError  # type: ignore[import-untyped]
from typing_extensions import override

from pipelex.system.exceptions import MissingDependencyError
from pipelex.tools.storage.exceptions import (
    StorageFileNotFoundError,
    StorageGcpCredentialsError,
    StorageGcpError,
)
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract


class GcpStorageProvider(StorageProviderAbstract):
    """Storage provider implementation for Google Cloud Storage.

    Files are stored in a GCS bucket with keys being path strings.
    Uses asyncio.to_thread to wrap sync GCS operations.
    """

    def __init__(
        self,
        bucket_name: str,
        project_id: str,
        credentials_file_path: str,
        signed_urls_lifespan: int | None,
    ) -> None:
        """Initialize the GCP storage provider.

        Args:
            bucket_name: The GCS bucket name.
            project_id: The GCP project ID.
            credentials_file_path: Path to the service account credentials JSON file.
            signed_urls_lifespan: Lifespan in seconds for signed URLs, or None if disabled.
        """
        self._bucket_name = bucket_name
        self._project_id = project_id
        self._credentials_file_path = credentials_file_path
        self._signed_urls_lifespan = signed_urls_lifespan
        self._bucket: Any = None

    def _get_bucket(self) -> Any:
        """Get or create the GCS bucket client (lazy initialization).

        Returns:
            The GCS bucket object.

        Raises:
            MissingDependencyError: If google-cloud-storage is not installed.
            StorageGcpCredentialsError: If credentials file is not found.
        """
        if self._bucket is None:
            if importlib.util.find_spec("google.cloud.storage") is None:
                lib_name = "google-cloud-storage"
                lib_extra_name = "gcp-storage"
                msg = "google-cloud-storage is required for GCP storage."
                raise MissingDependencyError(
                    lib_name,
                    lib_extra_name,
                    msg,
                )

            from google.cloud import storage  # type: ignore[import-untyped]  # noqa: PLC0415

            credentials_path = Path(self._credentials_file_path)
            if not credentials_path.exists():
                msg = f"GCP credentials file not found: '{self._credentials_file_path}'"
                raise StorageGcpCredentialsError(msg)

            client = storage.Client.from_service_account_json(  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType]
                self._credentials_file_path,
                project=self._project_id,
            )
            self._bucket = client.bucket(self._bucket_name)  # pyright: ignore[reportUnknownMemberType]
        return self._bucket  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType]

    def _load_sync(self, key: str) -> bytes:
        """Synchronous implementation of load for use with to_thread.

        Args:
            key: Storage key (without scheme prefix).

        Returns:
            The object contents as bytes.

        Raises:
            StorageFileNotFoundError: If the object does not exist.
        """
        bucket = self._get_bucket()

        from google.api_core.exceptions import NotFound  # type: ignore[import-untyped]  # noqa: PLC0415

        try:
            blob = bucket.blob(key)
            if not blob.exists():
                msg = f"Object not found in GCS: '{key}'"
                raise StorageFileNotFoundError(msg)
            data: bytes = blob.download_as_bytes()
            return data
        except StorageFileNotFoundError:
            raise
        except NotFound as exc:  # pyright: ignore[reportUnknownVariableType]
            msg = f"Object not found in GCS: '{key}'"
            raise StorageFileNotFoundError(msg) from exc

    @override
    async def _load(self, key: str) -> bytes:
        """Load bytes from a GCS object.

        Args:
            key: Storage key (without scheme prefix).

        Returns:
            The object contents as bytes.

        Raises:
            StorageFileNotFoundError: If the object does not exist.
            StorageGcpError: If the GCS operation fails.
        """
        return await asyncio.to_thread(self._load_sync, key)

    def _store_sync(self, data: bytes, key: str, content_type: str | None) -> None:
        """Synchronous implementation of store for use with to_thread.

        Args:
            data: The bytes to store.
            key: Storage key (without scheme prefix).
            content_type: Optional MIME type for the object.

        Raises:
            StorageGcpError: If the GCS operation fails.
        """
        bucket = self._get_bucket()

        try:
            blob = bucket.blob(key)
            blob.upload_from_string(data, content_type=content_type)
        except GoogleAPIError as exc:  # pyright: ignore[reportUnknownVariableType]
            msg = f"Failed to store object to GCS: '{key}': {exc}"
            raise StorageGcpError(msg) from exc

    @override
    async def _store(self, data: bytes, *, key: str, content_type: str | None) -> None:
        """Store bytes to a GCS object.

        Args:
            data: The bytes to store.
            key: Storage key (without scheme prefix).
            content_type: Optional MIME type for the object.

        Raises:
            StorageGcpError: If the GCS operation fails.
        """
        await asyncio.to_thread(self._store_sync, data, key, content_type)

    def _make_public_url(self, key: str) -> str:
        """Build a public URL for a GCS object.

        Args:
            key: Storage key (without scheme prefix).

        Returns:
            Public URL for the object.
        """
        return f"https://storage.googleapis.com/{self._bucket_name}/{key}"

    def _generate_signed_url_sync(self, key: str) -> str | None:
        """Synchronous implementation of signed URL generation for use with to_thread.

        Args:
            key: Storage key (without scheme prefix).

        Returns:
            Signed URL or public URL if signing fails.
        """
        bucket = self._get_bucket()

        try:
            blob = bucket.blob(key)
            signed_url: str = blob.generate_signed_url(
                expiration=timedelta(seconds=self._signed_urls_lifespan or 0),
                method="GET",
            )
            return signed_url
        except GoogleAPIError:
            return self._make_public_url(key)

    @override
    async def display_link(self, uri: str) -> str | None:
        """Return a URL for this storage URI.

        Args:
            uri: Full URI including pipelex-storage:// scheme.

        Returns:
            Signed URL if signed_urls_lifespan is configured, otherwise a public URL.
        """
        key = self._strip_scheme(uri)

        if self._signed_urls_lifespan is None:
            return self._make_public_url(key)

        return await asyncio.to_thread(self._generate_signed_url_sync, key)
