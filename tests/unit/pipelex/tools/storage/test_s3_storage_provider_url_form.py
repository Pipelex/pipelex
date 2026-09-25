from pathlib import Path
from urllib.parse import urlsplit

import pytest

from pipelex.tools.storage.s3_storage_provider import S3StorageProvider
from pipelex.tools.storage.storage_provider_abstract import PIPELEX_STORAGE_SCHEME

# botocore reads these at session creation; any of them set on the developer's machine could change the addressing
_AWS_ENV_VARS_TO_CLEAR = (
    "AWS_PROFILE",
    "AWS_DEFAULT_PROFILE",
    "AWS_SESSION_TOKEN",
    "AWS_SECURITY_TOKEN",
    "AWS_DEFAULT_REGION",
    "AWS_REGION",
    "AWS_ENDPOINT_URL",
    "AWS_ENDPOINT_URL_S3",
    "AWS_USE_DUALSTACK_ENDPOINT",
    "AWS_USE_FIPS_ENDPOINT",
    "AWS_S3_US_EAST_1_REGIONAL_ENDPOINT",
)
URL_FORM_TEST_REGION = "us-west-2"
URL_FORM_PLAIN_BUCKET = "pipelex-app-dev"
URL_FORM_DOTTED_BUCKET = "my.dotted.bucket"
# Only a legacy us-east-1 bucket can carry uppercase letters or an underscore; botocore signs it path-style
URL_FORM_LEGACY_BUCKET = "Legacy_Bucket"
URL_FORM_PLAIN_KEY = "runs/abc/moodboard.png"
# A caller's own upload can name its key freely: botocore percent-encodes what a URL would misread
URL_FORM_SPECIAL_KEY = "org/uploads/My Photo+#1?.png"


@pytest.mark.asyncio(loop_scope="class")
class TestS3StorageProviderUrlForm:
    """The host a link names, presigned through real botocore rather than a mock.

    Presigning is computed locally and makes no network call, so dummy credentials are enough.
    A content security policy names an origin, so the host is the contract: a bucket's own host
    can be allowed alone, the shared regional endpoint cannot.
    """

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
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "dummy-secret-for-local-presigning")

    @classmethod
    def _make_provider(cls, *, bucket_name: str, signed_urls_lifespan: int | None) -> S3StorageProvider:
        return S3StorageProvider(
            bucket_name=bucket_name,
            region=URL_FORM_TEST_REGION,
            signed_urls_lifespan=signed_urls_lifespan,
        )

    @pytest.mark.usefixtures("isolated_aws_environment")
    async def test_signed_url_is_on_the_bucket_regional_host(self) -> None:
        """A presigned link names the bucket's own regional host, not the region's shared endpoint."""
        key = "runs/abc/moodboard.png"
        provider = self._make_provider(bucket_name=URL_FORM_PLAIN_BUCKET, signed_urls_lifespan=3600)

        signed_url = await provider.public_url(uri=f"{PIPELEX_STORAGE_SCHEME}{key}")

        assert signed_url is not None
        parsed = urlsplit(signed_url)
        assert parsed.scheme == "https"
        assert parsed.netloc == f"{URL_FORM_PLAIN_BUCKET}.s3.{URL_FORM_TEST_REGION}.amazonaws.com"
        assert parsed.path == f"/{key}"
        assert "X-Amz-Signature=" in parsed.query

    @pytest.mark.usefixtures("isolated_aws_environment")
    async def test_signed_url_for_a_dotted_bucket_is_path_style_on_the_regional_host(self) -> None:
        """A dotted bucket name breaks the wildcard certificate, so its link stays path-style on the regional host."""
        key = "runs/abc/moodboard.png"
        provider = self._make_provider(bucket_name=URL_FORM_DOTTED_BUCKET, signed_urls_lifespan=3600)

        signed_url = await provider.public_url(uri=f"{PIPELEX_STORAGE_SCHEME}{key}")

        assert signed_url is not None
        parsed = urlsplit(signed_url)
        assert parsed.scheme == "https"
        assert parsed.netloc == f"s3.{URL_FORM_TEST_REGION}.amazonaws.com"
        assert parsed.path == f"/{URL_FORM_DOTTED_BUCKET}/{key}"

    @pytest.mark.parametrize("bucket_name", [URL_FORM_PLAIN_BUCKET, URL_FORM_DOTTED_BUCKET, URL_FORM_LEGACY_BUCKET])
    @pytest.mark.parametrize("key", [URL_FORM_PLAIN_KEY, URL_FORM_SPECIAL_KEY])
    @pytest.mark.usefixtures("isolated_aws_environment")
    async def test_signed_and_unsigned_urls_name_the_same_host_and_path(self, bucket_name: str, key: str) -> None:
        """An unsigned link never names a host or a path the signed link would not."""
        uri = f"{PIPELEX_STORAGE_SCHEME}{key}"
        signing_provider = self._make_provider(bucket_name=bucket_name, signed_urls_lifespan=3600)
        unsigned_provider = self._make_provider(bucket_name=bucket_name, signed_urls_lifespan=None)

        signed_url = await signing_provider.public_url(uri=uri)
        unsigned_url = await unsigned_provider.public_url(uri=uri)

        assert signed_url is not None
        assert unsigned_url is not None
        parsed_signed = urlsplit(signed_url)
        parsed_unsigned = urlsplit(unsigned_url)
        assert (parsed_unsigned.scheme, parsed_unsigned.netloc, parsed_unsigned.path) == (
            parsed_signed.scheme,
            parsed_signed.netloc,
            parsed_signed.path,
        )
        assert parsed_unsigned.query == ""
        assert parsed_unsigned.fragment == ""
