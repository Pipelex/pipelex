import asyncio
import base64
import importlib.util
import threading
from asyncio import sleep
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack
from typing import Any, ClassVar
from urllib.parse import quote

from typing_extensions import override

from pipelex.errors.error_codes import ErrorCode
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.system.exceptions import MissingDependencyError
from pipelex.tools.misc.async_utils import is_event_loop_running_on_this_thread
from pipelex.tools.storage.exceptions import (
    StorageFileNotFoundError,
    StorageS3Error,
)
from pipelex.tools.storage.storage_provider_abstract import StorageKind, StorageProviderAbstract, StoredData

# How many connections the S3 client of one event loop keeps open at most. Every operation on the loop shares the
# client, so its pool serves every request the loop runs at once: the API server's blob store runs its lookups and its
# reads for one request a bounded number at a time, which its tests hold to this pool, and the pool leaves room for a
# second request doing the same. An operation finding every connection busy waits for one, it is not refused.
S3_MAX_POOL_CONNECTIONS = 32

# The S3 error codes by which S3 refuses the credentials themselves, rather than failing to serve: an operator fixes these.
_S3_CREDENTIAL_REFUSAL_CODES = frozenset({"AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch", "ExpiredToken", "InvalidToken"})


def _code_for_s3_client_error(*, s3_error_code: str) -> ErrorCode:
    """The registry code of an S3 ``ClientError`` that is not a missing object, read from the code S3 answered."""
    if s3_error_code == "NoSuchBucket":
        return PipelexErrorCode.CONFIG_INVALID
    if s3_error_code in _S3_CREDENTIAL_REFUSAL_CODES:
        return PipelexErrorCode.CONFIG_CREDENTIAL_REFUSED
    return PipelexErrorCode.STORAGE_UNAVAILABLE


# What S3 answers a conditional write whose condition fails: `412` when the key holds an object (`If-None-Match: *`),
# `409 ConditionalRequestConflict` when another conditional write to the same key is in flight.
_PRECONDITION_FAILED_CODES = frozenset({"412", "PreconditionFailed"})
_CONDITIONAL_CONFLICT_CODES = frozenset({"409", "ConditionalRequestConflict"})
# S3 documents a `409` on a conditional write as retryable: the write is sent again after each of these pauses, and a
# conflict still answered after the last one is an error.
CONDITIONAL_CONFLICT_RETRY_DELAYS_SECONDS: tuple[float, ...] = (0.1, 0.25, 0.5, 1.0, 2.0)


def checksum_sha256_header_value(*, sha256_hex: str) -> str:
    """The `x-amz-checksum-sha256` value of bytes whose SHA-256 is `sha256_hex`: the raw digest in base64.

    Raises:
        ValueError: `sha256_hex` is not hexadecimal.
    """
    return base64.b64encode(bytes.fromhex(sha256_hex)).decode("ascii")


def _checksum_sha256_put_params(*, checksum_sha256_hex: str | None) -> dict[str, str]:
    """The `PutObject` parameters that make S3 check a write's SHA-256 and keep it beside the object.

    Every write the provider makes carries them, so S3 refuses a body that does not hash to the checksum and stores the
    checksum, which a `HeadObject` with `ChecksumMode=ENABLED` returns as `ChecksumSHA256`. With the digest, it goes as
    the `x-amz-checksum-sha256` header, and the bytes are not hashed again. Without it, `ChecksumAlgorithm` alone makes
    botocore hash the body as it sends it and send the checksum as a trailer of the upload.

    Args:
        checksum_sha256_hex: The SHA-256 of the body in lowercase hexadecimal, or None for botocore to compute it.

    Returns:
        The parameters to add to a `put_object` call.
    """
    params = {"ChecksumAlgorithm": "SHA256"}
    if checksum_sha256_hex is not None:
        params["ChecksumSHA256"] = checksum_sha256_header_value(sha256_hex=checksum_sha256_hex)
    return params


class _LoopClient:
    """The S3 client of one event loop, opened on the loop's first operation and shared by every later one.

    An aiobotocore client and the aiohttp session under it belong to the loop that opened them, so each loop gets a
    client of its own. Its closer is an asynchronous generator iterated once on that loop, which registers it with the
    loop: a loop shutting its asynchronous generators down, as `asyncio.run` does once its tasks have ended, closes the
    closer, which closes the client on its own loop before the loop closes. The provider's teardown closes it sooner, on
    a loop still running.
    """

    def __init__(self, *, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self._opening = asyncio.Lock()
        self._releases = AsyncExitStack()
        self._client: Any = None
        self._closer: AsyncGenerator[None] | None = None
        self.is_closed = False

    async def client(self, *, open_client: Callable[[], AbstractAsyncContextManager[Any]]) -> Any:
        """The loop's client, opened with `open_client` by the first caller, the others on the loop waiting for it.

        A client that failed to open is opened again by the next caller.
        """
        if self._client is None:
            async with self._opening:
                if self._client is None:
                    client = await self._releases.enter_async_context(open_client())
                    closer = self._close_at_loop_shutdown()
                    # The first iteration runs on the loop, which then holds the closer and closes it as it shuts down.
                    await anext(closer)
                    self._closer = closer
                    self._client = client
        return self._client

    async def _close_at_loop_shutdown(self) -> AsyncGenerator[None]:
        try:
            yield
        finally:
            self.is_closed = True
            self._client = None
            await self._releases.aclose()

    async def close(self) -> None:
        """Close the client, on its own loop. Closing it again does nothing."""
        if self._closer is not None:
            await self._closer.aclose()

    def close_soon(self) -> None:
        """Close the client from synchronous code on any thread, as far as its loop allows, without waiting for it.

        On a running loop the close is scheduled there. A loop no longer running is run until the close is done, unless
        this thread runs another loop, which cannot run a second one: that client is left to its loop's own shutdown. A
        closed loop has nothing left to close with, and holds no connection a client of it could still use.
        """
        if self._closer is None or self.loop.is_closed():
            return
        if self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self.close(), self.loop)
        elif not is_event_loop_running_on_this_thread():
            self.loop.run_until_complete(self.close())


class S3StorageProvider(StorageProviderAbstract):
    """Storage provider implementation for AWS S3 storage.

    Files are stored in an S3 bucket with keys being path strings, through aiobotocore. Each event loop that reaches the
    provider opens one S3 client on its first operation, and every operation on that loop shares it, with its pool of
    connections, so an operation pays neither a client build nor a new TLS connection. The client is closed as its loop
    shuts down, or by `teardown`, whichever comes first (`_LoopClient`).
    """

    storage_kind: ClassVar[StorageKind] = "s3"

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
        # Several threads may each run a loop of their own, so the map of each loop's client is guarded.
        self._loop_clients: dict[asyncio.AbstractEventLoop, _LoopClient] = {}
        self._loop_clients_lock = threading.Lock()

    async def _client(self) -> Any:
        """The S3 client of the running event loop, opened on the loop's first operation."""
        loop = asyncio.get_running_loop()
        with self._loop_clients_lock:
            loop_client = self._loop_clients.get(loop)
            if loop_client is None or loop_client.is_closed:
                # A loop that has closed never runs again: its entry is dropped as a new loop arrives, so a process
                # running loop after loop, as a command line running each step under `asyncio.run` does, holds one.
                for closed_loop in [known_loop for known_loop in self._loop_clients if known_loop.is_closed()]:
                    del self._loop_clients[closed_loop]
                loop_client = _LoopClient(loop=loop)
                self._loop_clients[loop] = loop_client
        return await loop_client.client(open_client=self._open_client)

    def _open_client(self) -> AbstractAsyncContextManager[Any]:
        """The context that opens an S3 client on entry and closes it on exit."""
        context: AbstractAsyncContextManager[Any] = self._get_session().create_client(**self._get_client_config())
        return context

    @override
    def teardown(self) -> None:
        """Close the S3 client of every loop still running, or still open, on that loop.

        A client whose loop is running is closed there soon after, without this waiting for it, since this runs as the
        runtime's synchronous teardown, on that very loop when a server shuts down. Any later operation opens a new one.
        """
        with self._loop_clients_lock:
            loop_clients = list(self._loop_clients.values())
            self._loop_clients = {}
        for loop_client in loop_clients:
            loop_client.close_soon()

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
        #
        # Every write carries the body's SHA-256, which S3 checks the body against (`_checksum_sha256_put_params`).
        # When botocore computes it, it goes as a trailer of an upload botocore already leaves unsigned. When the
        # caller gave it, it goes as the signed `x-amz-checksum-sha256` header, and botocore, which recognises only
        # a checksum of its own, would hash the whole body once more just to sign it. Over TLS the signed checksum
        # protects the body as well as a signed payload would, so the payload is never signed.
        config = AioConfig(
            signature_version="s3v4",
            s3={"addressing_style": "virtual", "payload_signing_enabled": False},
            max_pool_connections=S3_MAX_POOL_CONNECTIONS,
        )

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
            NoCredentialsError,
        )

        client = await self._client()
        try:
            response = await client.get_object(Bucket=self._bucket_name, Key=key)
            async with response["Body"] as stream:
                data: bytes = await stream.read()
            # Extract ContentType from S3 response
            content_type: str | None = response.get("ContentType")
            return StoredData(data=data, mime_type=content_type)
        except client.exceptions.NoSuchKey as exc:
            msg = f"Object not found in S3: '{key}'"
            raise StorageFileNotFoundError(msg).with_params(scheme=self.storage_kind) from exc
        except client.exceptions.NoSuchBucket as exc:
            msg = f"Bucket not found in S3: '{self._bucket_name}'"
            raise StorageS3Error(msg).with_error_code(PipelexErrorCode.CONFIG_INVALID) from exc
        except ClientError as exc:
            error_code = (exc.response.get("Error") or {}).get("Code", "Unknown")
            if error_code == "NoSuchKey":
                msg = f"Object not found in S3: '{key}'"
                raise StorageFileNotFoundError(msg).with_params(scheme=self.storage_kind) from exc
            msg = f"S3 ClientError ({error_code}) for key '{key}'"
            raise StorageS3Error(msg).with_error_code(_code_for_s3_client_error(s3_error_code=error_code)) from exc
        except NoCredentialsError as exc:
            msg = f"S3 credentials not found for key '{key}': {type(exc).__name__}"
            raise StorageS3Error(msg).with_error_code(PipelexErrorCode.CONFIG_CREDENTIAL_MISSING) from exc
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
            NoCredentialsError,
        )

        client = await self._client()
        try:
            # The Range header's end offset is inclusive.
            response = await client.get_object(Bucket=self._bucket_name, Key=key, Range=f"bytes=0-{nb_bytes - 1}")
            async with response["Body"] as stream:
                data: bytes = await stream.read()
            return data[:nb_bytes]
        except client.exceptions.NoSuchKey as exc:
            msg = f"Object not found in S3: '{key}'"
            raise StorageFileNotFoundError(msg).with_params(scheme=self.storage_kind) from exc
        except client.exceptions.NoSuchBucket as exc:
            msg = f"Bucket not found in S3: '{self._bucket_name}'"
            raise StorageS3Error(msg).with_error_code(PipelexErrorCode.CONFIG_INVALID) from exc
        except ClientError as exc:
            error_code = (exc.response.get("Error") or {}).get("Code", "Unknown")
            if error_code == "InvalidRange":
                # S3 refuses any range over an empty object: its head is empty.
                return b""
            if error_code == "NoSuchKey":
                msg = f"Object not found in S3: '{key}'"
                raise StorageFileNotFoundError(msg).with_params(scheme=self.storage_kind) from exc
            msg = f"S3 ClientError ({error_code}) for key '{key}'"
            raise StorageS3Error(msg).with_error_code(_code_for_s3_client_error(s3_error_code=error_code)) from exc
        except NoCredentialsError as exc:
            msg = f"S3 credentials not found for key '{key}': {type(exc).__name__}"
            raise StorageS3Error(msg).with_error_code(PipelexErrorCode.CONFIG_CREDENTIAL_MISSING) from exc
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
            NoCredentialsError,
        )

        client = await self._client()
        try:
            response = await client.head_object(Bucket=self._bucket_name, Key=key)
        except ClientError as exc:
            error_code = (exc.response.get("Error") or {}).get("Code", "Unknown")
            # A HEAD answer has no body, so a missing object comes back as the bare status code.
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                msg = f"Object not found in S3: '{key}'"
                raise StorageFileNotFoundError(msg).with_params(scheme=self.storage_kind) from exc
            msg = f"S3 ClientError ({error_code}) for key '{key}'"
            raise StorageS3Error(msg).with_error_code(_code_for_s3_client_error(s3_error_code=error_code)) from exc
        except NoCredentialsError as exc:
            msg = f"S3 credentials not found for key '{key}': {type(exc).__name__}"
            raise StorageS3Error(msg).with_error_code(PipelexErrorCode.CONFIG_CREDENTIAL_MISSING) from exc
        except BotoCoreError as exc:
            msg = f"S3 backend error for key '{key}': {type(exc).__name__}"
            raise StorageS3Error(msg) from exc
        content_length: int = response["ContentLength"]
        return content_length

    @override
    async def _store(self, data: bytes, *, key: str, content_type: str | None, checksum_sha256_hex: str | None) -> None:
        """Store bytes to an S3 object, with S3 checking their SHA-256.

        The PUT carries the SHA-256, so S3 refuses a body that arrived damaged, as a `BadDigest`, and keeps the
        checksum beside the object, where a `HeadObject` with `ChecksumMode=ENABLED` reads it.

        Args:
            data: The bytes to store.
            key: Storage key (without scheme prefix).
            content_type: Optional MIME type for the object.
            checksum_sha256_hex: The SHA-256 of `data` in lowercase hexadecimal, or None for botocore to compute it as
                it sends the bytes.

        Raises:
            StorageS3Error: If the S3 operation fails (any ClientError or BotoCoreError).
        """
        from botocore.exceptions import (  # ruff: ignore[import-outside-top-level] - optional dependency, lazy import
            BotoCoreError,
            ClientError,
            NoCredentialsError,
        )

        client = await self._client()
        try:
            put_params: dict[str, Any] = {
                "Bucket": self._bucket_name,
                "Key": key,
                "Body": data,
            }
            if content_type:
                put_params["ContentType"] = content_type
            put_params.update(_checksum_sha256_put_params(checksum_sha256_hex=checksum_sha256_hex))
            await client.put_object(**put_params)
        except client.exceptions.NoSuchBucket as exc:
            msg = f"Bucket not found in S3: '{self._bucket_name}'"
            raise StorageS3Error(msg).with_error_code(PipelexErrorCode.CONFIG_INVALID) from exc
        except ClientError as exc:
            error_code = (exc.response.get("Error") or {}).get("Code", "Unknown")
            msg = f"S3 ClientError ({error_code}) for key '{key}'"
            raise StorageS3Error(msg).with_error_code(_code_for_s3_client_error(s3_error_code=error_code)) from exc
        except NoCredentialsError as exc:
            msg = f"S3 credentials not found for key '{key}': {type(exc).__name__}"
            raise StorageS3Error(msg).with_error_code(PipelexErrorCode.CONFIG_CREDENTIAL_MISSING) from exc
        except BotoCoreError as exc:
            msg = f"S3 backend error for key '{key}': {type(exc).__name__}"
            raise StorageS3Error(msg) from exc

    @override
    async def _store_if_absent(self, *, data: bytes, key: str, content_type: str | None, checksum_sha256_hex: str | None) -> bool:
        """Create an S3 object unless one exists at the key, with S3 checking the condition and the checksum.

        The PUT carries `If-None-Match: *`, so S3 writes it only when the key holds no object and answers `412`
        otherwise, which is the key already held. It carries the SHA-256, as `x-amz-checksum-sha256` when the caller
        gave it and computed by botocore otherwise, and S3 refuses a body whose hash differs, so the object holds
        exactly the bytes the checksum names, and keeps the checksum beside it.

        A `409 ConditionalRequestConflict` means another operation on the key, a conditional write or a delete, was
        in flight, and S3's answer to it is to retry: the PUT is sent again after a short pause, a bounded number of
        times. The PUT is retried rather than the key looked up, because the other operation may leave the key free,
        when it fails or deletes, and a retried PUT tells every outcome apart: a `412` is the object the other write
        created, held, and a success is this call's own object.

        Args:
            data: The bytes to store, already checked against their checksum.
            key: Storage key (without scheme prefix).
            content_type: Optional MIME type for the object.
            checksum_sha256_hex: The SHA-256 of `data` in lowercase hexadecimal, sent for S3 to check, or None for
                botocore to compute it as it sends the bytes.

        Returns:
            True when this call created the object, False when the key already held one.

        Raises:
            StorageS3Error: If the S3 operation fails (any other ClientError, a `409` still answered once the retries
                ran out, or a BotoCoreError).
        """
        from botocore.exceptions import (  # ruff: ignore[import-outside-top-level] - optional dependency, lazy import
            BotoCoreError,
            ClientError,
        )

        put_params: dict[str, Any] = {
            "Bucket": self._bucket_name,
            "Key": key,
            "Body": data,
            "IfNoneMatch": "*",
        }
        if content_type:
            put_params["ContentType"] = content_type
        put_params.update(_checksum_sha256_put_params(checksum_sha256_hex=checksum_sha256_hex))

        retry_delays = CONDITIONAL_CONFLICT_RETRY_DELAYS_SECONDS
        conditional_conflict: ClientError | None = None
        client = await self._client()
        for index_attempt in range(len(retry_delays) + 1):
            if index_attempt > 0:
                await sleep(retry_delays[index_attempt - 1])
            try:
                await client.put_object(**put_params)
            except client.exceptions.NoSuchBucket as exc:
                msg = f"Bucket not found in S3: '{self._bucket_name}'"
                raise StorageS3Error(msg).with_error_code(PipelexErrorCode.CONFIG_INVALID) from exc
            except ClientError as exc:
                error_code = (exc.response.get("Error") or {}).get("Code", "Unknown")
                if error_code in _PRECONDITION_FAILED_CODES:
                    return False
                if error_code not in _CONDITIONAL_CONFLICT_CODES:
                    msg = f"S3 ClientError ({error_code}) for key '{key}'"
                    raise StorageS3Error(msg).with_error_code(_code_for_s3_client_error(s3_error_code=error_code)) from exc
                conditional_conflict = exc
                continue
            except BotoCoreError as exc:
                msg = f"S3 backend error for key '{key}': {type(exc).__name__}"
                raise StorageS3Error(msg) from exc
            return True
        msg = f"S3 ClientError (ConditionalRequestConflict) for key '{key}' on each of {len(retry_delays) + 1} attempts"
        raise StorageS3Error(msg) from conditional_conflict

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

        client = await self._client()
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
