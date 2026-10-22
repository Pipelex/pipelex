import base64
import hashlib
import inspect
from pathlib import Path
from typing import Any, NamedTuple

import pytest
from aiobotocore.session import AioSession, get_session
from pytest_mock import MockerFixture

from pipelex.tools.storage.s3_storage_provider import S3StorageProvider

# botocore reads these at session creation; any of them set on the developer's machine could change the request
_AWS_ENV_VARS_TO_CLEAR = (
    "AWS_PROFILE",
    "AWS_DEFAULT_PROFILE",
    "AWS_SESSION_TOKEN",
    "AWS_SECURITY_TOKEN",
    "AWS_DEFAULT_REGION",
    "AWS_REGION",
    "AWS_ENDPOINT_URL",
    "AWS_ENDPOINT_URL_S3",
    "AWS_REQUEST_CHECKSUM_CALCULATION",
    "AWS_RESPONSE_CHECKSUM_VALIDATION",
)
CHECKSUM_TEST_BUCKET = "pipelex-app-dev"
CHECKSUM_TEST_REGION = "eu-west-3"
PAYLOAD = b"the bytes a run generated"
PAYLOAD_SHA256_BASE64 = base64.b64encode(hashlib.sha256(PAYLOAD).digest()).decode("ascii")


class _RequestCapturedError(Exception):
    """Raised by the capturing hook, so the request is read as botocore would send it and never sent."""


class _CapturedRequest(NamedTuple):
    headers: dict[str, str]
    body: bytes


async def _read_body(body: Any) -> bytes:
    if body is None:
        return b""
    if isinstance(body, bytes | bytearray):
        return bytes(body)
    read_result = body.read()
    if inspect.isawaitable(read_result):
        read_result = await read_result
    return bytes(read_result)


@pytest.mark.asyncio(loop_scope="class")
class TestS3StorageProviderChecksumOnTheWire:
    @pytest.fixture
    def isolated_aws_environment(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Give botocore dummy credentials and keep the developer's own AWS configuration out of the test."""
        for env_var in _AWS_ENV_VARS_TO_CLEAR:
            monkeypatch.delenv(env_var, raising=False)
        empty_aws_file = tmp_path / "empty_aws_file"
        empty_aws_file.write_text("")
        monkeypatch.setenv("AWS_CONFIG_FILE", str(empty_aws_file))
        monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(empty_aws_file))
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIDEXAMPLE")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "dummy-secret-for-local-signing")

    @pytest.fixture
    def captured_requests(self, mocker: MockerFixture, isolated_aws_environment: None) -> list[_CapturedRequest]:  # ruff: ignore[unused-method-argument]
        """The `PutObject` requests the provider's clients would send, signed by real botocore and stopped before they leave.

        Mocking `put_object` shows only the parameters the provider passes; whether botocore turns them into a checksum S3
        checks, and whether it hashes the body once more to sign it, is botocore's doing, so these tests read the request
        itself. Nothing reaches the network.
        """
        captured: list[_CapturedRequest] = []
        session: AioSession = get_session()

        async def capture(request: Any, **_kwargs: Any) -> None:
            headers = {
                str(name).lower(): value.decode("ascii") if isinstance(value, bytes) else str(value) for name, value in request.headers.items()
            }
            captured.append(_CapturedRequest(headers=headers, body=await _read_body(request.body)))
            raise _RequestCapturedError

        session.register("before-send.s3.PutObject", capture)
        mocker.patch("aiobotocore.session.get_session", return_value=session)
        return captured

    @staticmethod
    def _make_provider() -> S3StorageProvider:
        return S3StorageProvider(bucket_name=CHECKSUM_TEST_BUCKET, region=CHECKSUM_TEST_REGION, signed_urls_lifespan=None)

    async def test_a_callers_digest_goes_as_a_signed_header_and_the_body_is_not_hashed_again(self, captured_requests: list[_CapturedRequest]) -> None:
        with pytest.raises(_RequestCapturedError):
            await self._make_provider().store(
                data=PAYLOAD,
                key="scope/generated/abc/report.pdf",
                content_type="application/pdf",
                checksum_sha256_hex=hashlib.sha256(PAYLOAD).hexdigest(),
            )

        request = captured_requests[-1]
        assert request.headers["x-amz-checksum-sha256"] == PAYLOAD_SHA256_BASE64
        assert request.headers["x-amz-sdk-checksum-algorithm"] == "SHA256"
        # The signature covers the checksum, and botocore did not hash the body to sign it.
        assert "x-amz-checksum-sha256" in request.headers["authorization"]
        assert request.headers["x-amz-content-sha256"] == "UNSIGNED-PAYLOAD"
        assert "x-amz-trailer" not in request.headers
        assert request.body == PAYLOAD

    async def test_without_a_digest_botocore_sends_the_sha256_as_a_trailer(self, captured_requests: list[_CapturedRequest]) -> None:
        with pytest.raises(_RequestCapturedError):
            await self._make_provider().store(data=PAYLOAD, key="scope/assets/upload.txt", content_type="text/plain")

        request = captured_requests[-1]
        assert request.headers["x-amz-sdk-checksum-algorithm"] == "SHA256"
        assert request.headers["x-amz-trailer"] == "x-amz-checksum-sha256"
        assert f"x-amz-checksum-sha256:{PAYLOAD_SHA256_BASE64}".encode("ascii") in request.body

    async def test_a_create_only_write_carries_the_checksum_beside_its_condition(self, captured_requests: list[_CapturedRequest]) -> None:
        with pytest.raises(_RequestCapturedError):
            await self._make_provider().store_if_absent(data=PAYLOAD, key="scope/blobs/one", checksum_sha256_hex=hashlib.sha256(PAYLOAD).hexdigest())

        request = captured_requests[-1]
        assert request.headers["if-none-match"] == "*"
        assert request.headers["x-amz-checksum-sha256"] == PAYLOAD_SHA256_BASE64
        assert request.headers["x-amz-content-sha256"] == "UNSIGNED-PAYLOAD"
