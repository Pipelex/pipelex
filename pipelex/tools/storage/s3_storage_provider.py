import base64
import importlib.util
from typing import Any
from urllib.parse import quote

from typing_extensions import override

from pipelex.system.exceptions import MissingDependencyError
from pipelex.tools.storage.exceptions import (
    StorageFileNotFoundError,
    StorageS3Error,
)
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract, StoredData

# What S3 answers a conditional write whose condition fails: `412` when the key holds an object (`If-None-Match: *`),
# `409 ConditionalRequestConflict` when another conditional write to the same key is in flight.
_PRECONDITION_FAILED_CODES = frozenset({"412", "PreconditionFailed"})
_CONDITIONAL_CONFLICT_CODES = frozenset({"409", "ConditionalRequestConflict"})


def checksum_sha256_header_value(*, sha256_hex: str) -> str:
    """The `x-amz-checksum-sha256` value of bytes whose SHA-256 is `sha256_hex`: the raw digest in base64.

    Raises:
        ValueError: `sha256_hex` is not hexadecimal.
    """
    return base64.b64encode(bytes.fromhex(sha256_hex)).decode("ascii")


class S3StorageProvider(StorageProviderAbstract):
    """Storage provider implementation for AWS S3 storage.

    Files are stored in an S3 bucket with keys being path strings.
    Uses aiobotocore for async S3 operations.
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
        """Check if aiobotocore is installed.

        Raises:
            MissingDependencyError: If aiobotocore is not installed.
        """
        if importlib.util.find_spec("aiobotocore") is None:
            lib_name = "aiobotocore"
            lib_extra_name = "s3"
            msg = "aiobotocore is required for S3 storage."
            raise MissingDependencyError(
                lib_name,
                lib_extra_name,
                msg,
            )

    def _get_session(self) -> Any:
        """Get or create the aiobotocore session (lazy initialization).

        Returns:
            The aiobotocore AioSession.
        """
        self._check_dependency()

        if self._session is None:
            from aiobotocore.session import get_session  # ruff: ignore[import-outside-top-level] - optional dependency, lazy import

            self._session = get_session()
        return self._session

    def _get_client_config(self) -> dict[str, Any]:
        """Get the configuration for creating S3 clients.

        Returns:
            Dictionary of client configuration parameters.
        """
        from aiobotocore.config import AioConfig  # ruff: ignore[import-outside-top-level] - optional dependency, lazy import

        endpoint_url = f"https://s3.{self._region}.amazonaws.com"
        # botocore addresses path-style whenever an endpoint is given, which puts every link on the region's
        # shared host. A content security policy can allow a bucket only by its own host, so pin the virtual
        # style: `<bucket>.s3.<region>.amazonaws.com`. botocore still falls back to path-style for a bucket
        # name that cannot be a hostname, a dotted one included.
        config = AioConfig(signature_version="s3v4", s3={"addressing_style": "virtual"})

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
            StorageS3Error: If the S3 operation fails (any ClientError or BotoCoreError).
        """
        from botocore.exceptions import (  # ruff: ignore[import-outside-top-level] - optional dependency, lazy import
            BotoCoreError,
            ClientError,
        )

        session = self._get_session()
        client_config = self._get_client_config()

        async with session.create_client(**client_config) as client:
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
            except BotoCoreError as exc:
                msg = f"S3 backend error for key '{key}': {type(exc).__name__}"
                raise StorageS3Error(msg) from exc

    @override
    async def _load_head(self, key: str, *, nb_bytes: int) -> bytes:
        """Load the first bytes of an S3 object with a ranged GET, instead of the whole object.

        Args:
            key: Storage key (without scheme prefix).
            nb_bytes: How many leading bytes to read. An object shorter than this is read whole.

        Returns:
            At most `nb_bytes` leading bytes of the object.

        Raises:
            StorageFileNotFoundError: If the object does not exist.
            StorageS3Error: If the S3 operation fails (any other ClientError or BotoCoreError).
        """
        from botocore.exceptions import (  # ruff: ignore[import-outside-top-level] - optional dependency, lazy import
            BotoCoreError,
            ClientError,
        )

        session = self._get_session()
        client_config = self._get_client_config()

        async with session.create_client(**client_config) as client:
            try:
                # The Range header's end offset is inclusive.
                response = await client.get_object(Bucket=self._bucket_name, Key=key, Range=f"bytes=0-{nb_bytes - 1}")
                async with response["Body"] as stream:
                    data: bytes = await stream.read()
                return data[:nb_bytes]
            except client.exceptions.NoSuchKey as exc:
                msg = f"Object not found in S3: '{key}'"
                raise StorageFileNotFoundError(msg) from exc
            except client.exceptions.NoSuchBucket as exc:
                msg = f"Bucket not found in S3: '{self._bucket_name}'"
                raise StorageS3Error(msg) from exc
            except ClientError as exc:
                error_code = (exc.response.get("Error") or {}).get("Code", "Unknown")
                if error_code == "InvalidRange":
                    # S3 refuses any range over an empty object: its head is empty.
                    return b""
                if error_code == "NoSuchKey":
                    msg = f"Object not found in S3: '{key}'"
                    raise StorageFileNotFoundError(msg) from exc
                msg = f"S3 ClientError ({error_code}) for key '{key}'"
                raise StorageS3Error(msg) from exc
            except BotoCoreError as exc:
                msg = f"S3 backend error for key '{key}': {type(exc).__name__}"
                raise StorageS3Error(msg) from exc

    @override
    async def _load_size(self, key: str) -> int:
        """The size of an S3 object, read with a HEAD request instead of its bytes.

        Args:
            key: Storage key (without scheme prefix).

        Returns:
            The object's `ContentLength`.

        Raises:
            StorageFileNotFoundError: If the object does not exist.
            StorageS3Error: If the S3 operation fails (any other ClientError or BotoCoreError).
        """
        from botocore.exceptions import (  # ruff: ignore[import-outside-top-level] - optional dependency, lazy import
            BotoCoreError,
            ClientError,
        )

        session = self._get_session()
        client_config = self._get_client_config()

        async with session.create_client(**client_config) as client:
            try:
                response = await client.head_object(Bucket=self._bucket_name, Key=key)
            except ClientError as exc:
                error_code = (exc.response.get("Error") or {}).get("Code", "Unknown")
                # A HEAD answer has no body, so a missing object comes back as the bare status code.
                if error_code in {"404", "NoSuchKey", "NotFound"}:
                    msg = f"Object not found in S3: '{key}'"
                    raise StorageFileNotFoundError(msg) from exc
                msg = f"S3 ClientError ({error_code}) for key '{key}'"
                raise StorageS3Error(msg) from exc
            except BotoCoreError as exc:
                msg = f"S3 backend error for key '{key}': {type(exc).__name__}"
                raise StorageS3Error(msg) from exc
            content_length: int = response["ContentLength"]
            return content_length

    @override
    async def _store(self, data: bytes, *, key: str, content_type: str | None) -> None:
        """Store bytes to an S3 object.

        Args:
            data: The bytes to store.
            key: Storage key (without scheme prefix).
            content_type: Optional MIME type for the object.

        Raises:
            StorageS3Error: If the S3 operation fails (any ClientError or BotoCoreError).
        """
        from botocore.exceptions import (  # ruff: ignore[import-outside-top-level] - optional dependency, lazy import
            BotoCoreError,
            ClientError,
        )

        session = self._get_session()
        client_config = self._get_client_config()

        async with session.create_client(**client_config) as client:
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
            except BotoCoreError as exc:
                msg = f"S3 backend error for key '{key}': {type(exc).__name__}"
                raise StorageS3Error(msg) from exc

    @override
    async def _store_if_absent(self, *, data: bytes, key: str, content_type: str | None, checksum_sha256_hex: str | None) -> bool:
        """Create an S3 object unless one exists at the key, with S3 checking the condition and the checksum.

        The PUT carries `If-None-Match: *`, so S3 writes it only when the key holds no object and answers `412`
        otherwise, which is the key already held. With a checksum, it carries the SHA-256 as `x-amz-checksum-sha256`,
        and S3 refuses a body whose hash differs, so the object holds exactly the bytes the checksum names. A `409`
        means another conditional write to the key is in flight: the key is looked up once that request is refused,
        and the object found there, which that other write created, counts as held.

        Args:
            data: The bytes to store, already checked against their checksum.
            key: Storage key (without scheme prefix).
            content_type: Optional MIME type for the object.
            checksum_sha256_hex: The SHA-256 of `data` in lowercase hexadecimal, sent for S3 to check, or None.

        Returns:
            True when this call created the object, False when the key already held one.

        Raises:
            StorageS3Error: If the S3 operation fails (any other ClientError, a `409` whose key still holds nothing, or a
                BotoCoreError).
        """
        from botocore.exceptions import (  # ruff: ignore[import-outside-top-level] - optional dependency, lazy import
            BotoCoreError,
            ClientError,
        )

        session = self._get_session()
        client_config = self._get_client_config()

        conditional_conflict: ClientError | None = None
        async with session.create_client(**client_config) as client:
            try:
                put_params: dict[str, Any] = {
                    "Bucket": self._bucket_name,
                    "Key": key,
                    "Body": data,
                    "IfNoneMatch": "*",
                }
                if content_type:
                    put_params["ContentType"] = content_type
                if checksum_sha256_hex is not None:
                    put_params["ChecksumSHA256"] = checksum_sha256_header_value(sha256_hex=checksum_sha256_hex)
                await client.put_object(**put_params)
            except client.exceptions.NoSuchBucket as exc:
                msg = f"Bucket not found in S3: '{self._bucket_name}'"
                raise StorageS3Error(msg) from exc
            except ClientError as exc:
                error_code = (exc.response.get("Error") or {}).get("Code", "Unknown")
                if error_code in _PRECONDITION_FAILED_CODES:
                    return False
                if error_code not in _CONDITIONAL_CONFLICT_CODES:
                    msg = f"S3 ClientError ({error_code}) for key '{key}'"
                    raise StorageS3Error(msg) from exc
                conditional_conflict = exc
            except BotoCoreError as exc:
                msg = f"S3 backend error for key '{key}': {type(exc).__name__}"
                raise StorageS3Error(msg) from exc
        if conditional_conflict is None:
            return True
        try:
            await self._load_size(key)
        except StorageFileNotFoundError:
            msg = f"S3 ClientError (ConditionalRequestConflict) for key '{key}', which still holds no object"
            raise StorageS3Error(msg) from conditional_conflict
        return False

    def _make_public_url(self, key: str) -> str:
        """Build an unsigned public URL for an S3 object, on the same host and path a signed one would name.

        The URL is virtual-hosted on the bucket's regional host, except for a bucket name that cannot be a
        hostname: a dotted name breaks the `*.s3.<region>.amazonaws.com` wildcard certificate over HTTPS, and a
        legacy name with uppercase letters or an underscore is no hostname at all, so its URL is path-style on
        the regional host. botocore's own test decides, so the two forms cannot disagree. The key is
        percent-encoded as botocore signs it, since a caller's own upload can name a key holding a space,
        a `#` or a `?`.

        Args:
            key: Storage key (without scheme prefix).

        Returns:
            Public URL for the object.
        """
        from botocore.utils import check_dns_name  # ruff: ignore[import-outside-top-level] - optional dependency, lazy import

        encoded_key = quote(key, safe="/~")
        if check_dns_name(self._bucket_name):
            return f"https://{self._bucket_name}.s3.{self._region}.amazonaws.com/{encoded_key}"
        return f"https://s3.{self._region}.amazonaws.com/{self._bucket_name}/{encoded_key}"

    @override
    async def public_url(self, uri: str) -> str | None:
        """Return a URL for this storage URI.

        Args:
            uri: Full URI including pipelex-storage:// scheme.

        Returns:
            Presigned URL if signed_urls_lifespan is configured, otherwise a public URL.
        """
        from botocore.exceptions import (  # ruff: ignore[import-outside-top-level] - optional dependency, lazy import
            BotoCoreError,
            ClientError,
        )

        key = self._strip_scheme(uri)

        if self._signed_urls_lifespan is None:
            return self._make_public_url(key)

        session = self._get_session()
        client_config = self._get_client_config()

        async with session.create_client(**client_config) as client:
            try:
                presigned_url: str = await client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self._bucket_name, "Key": key},
                    ExpiresIn=self._signed_urls_lifespan,
                )
                return presigned_url
            except (BotoCoreError, ClientError):
                # ClientError (signing rejected) and BotoCoreError (transport failure) both
                # fall back to the public URL — same "if signing fails, serve unsigned" semantics.
                return self._make_public_url(key)
