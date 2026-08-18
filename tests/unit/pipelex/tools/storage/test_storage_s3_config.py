from typing import Literal

import pytest

from pipelex.tools.storage.exceptions import StorageConfigError
from pipelex.tools.storage.storage_config import StorageS3Config
from pipelex.urls import URLs


def make_s3_config(
    uri_format: str = "s3-assets/{hash}",
    bucket_name: str = "my-bucket",
    region: str = "eu-west-1",
    signed_urls_lifespan_seconds: int | Literal["disabled"] = 3600,
) -> StorageS3Config:
    return StorageS3Config(
        uri_format=uri_format,
        bucket_name=bucket_name,
        region=region,
        signed_urls_lifespan_seconds=signed_urls_lifespan_seconds,
    )


class TestStorageS3Config:
    def test_lazy_validate_valid_config_passes_silently(self):
        """A fully valid S3 config must pass lazy_validate without raising."""
        config = make_s3_config()
        config.lazy_validate()

    @pytest.mark.parametrize(
        ("uri_format", "bucket_name", "region", "expected_fragment"),
        [
            pytest.param("", "my-bucket", "eu-west-1", "- set a value for uri_format", id="empty-uri-format"),
            pytest.param("assets/myhash/file", "my-bucket", "eu-west-1", "- uri_format must contain a {hash} placeholder", id="uri-no-braced-hash"),
            pytest.param("assets/{{hash}}", "my-bucket", "eu-west-1", "- uri_format must contain a {hash} placeholder", id="uri-escaped-hash"),
            pytest.param("assets/{hash", "my-bucket", "eu-west-1", "- uri_format is not a valid format string", id="uri-malformed-format"),
            pytest.param(
                "assets/{hash}/{tenant}", "my-bucket", "eu-west-1", "- uri_format placeholder '{tenant}' is not supported", id="uri-unsupported"
            ),
            pytest.param("assets/{hash:.0}", "my-bucket", "eu-west-1", "- the {hash} placeholder must be plain", id="uri-hash-format-spec"),
            # A format spec on a non-hash field is just as dangerous: {primary_id:.0} truncates to "" (collisions),
            # and a huge width like {primary_id:1000000000} would allocate a ~1GB string if it ever reached a
            # test rendering — so it must be rejected at parse time, before any format() call.
            pytest.param(
                "assets/{hash}/{primary_id:.0}",
                "my-bucket",
                "eu-west-1",
                "- uri_format placeholder '{primary_id}' must be plain",
                id="uri-field-truncate-spec",
            ),
            pytest.param(
                "assets/{hash}/{primary_id:1000000000}",
                "my-bucket",
                "eu-west-1",
                "- uri_format placeholder '{primary_id}' must be plain",
                id="uri-field-huge-width",
            ),
            pytest.param(
                # `{primary_id!r}` rather than the retired `{secondary_id!r}`:
                # this case is about a CONVERSION on a supported placeholder, so
                # it must use a name the supported set still contains — an
                # unsupported name is refused by a different check first, and
                # this case would then pass for the wrong reason.
                "assets/{hash}/{primary_id!r}",
                "my-bucket",
                "eu-west-1",
                "- uri_format placeholder '{primary_id}' must be plain",
                id="uri-field-conversion",
            ),
            pytest.param(
                "assets/{hash}/{primary_id.foo}",
                "my-bucket",
                "eu-west-1",
                "- uri_format placeholder '{primary_id.foo}' must be plain",
                id="uri-field-attr-access",
            ),
            pytest.param(
                "assets/{hash}/{extension[0]}",
                "my-bucket",
                "eu-west-1",
                "- uri_format placeholder '{extension[0]}' must be plain",
                id="uri-field-index-access",
            ),
            pytest.param("s3-assets/{hash}", "", "eu-west-1", "- set a value for bucket_name", id="empty-bucket-name"),
            pytest.param("s3-assets/{hash}", "my.bucket", "eu-west-1", "- bucket_name cannot contain a dot", id="bucket-with-dot"),
            pytest.param("s3-assets/{hash}", "my/bucket", "eu-west-1", "- bucket_name cannot contain a slash", id="bucket-with-slash"),
            pytest.param("s3-assets/{hash}", "my-bucket", "", "- set a value for region", id="empty-region"),
        ],
    )
    def test_lazy_validate_single_fault(
        self,
        uri_format: str,
        bucket_name: str,
        region: str,
        expected_fragment: str,
    ):
        """Each individual config fault must raise a StorageConfigError naming the fault and pointing to the docs."""
        config = make_s3_config(uri_format=uri_format, bucket_name=bucket_name, region=region)
        with pytest.raises(StorageConfigError) as exc_info:
            config.lazy_validate()
        message = str(exc_info.value)
        assert expected_fragment in message
        assert URLs.documentation in message

    def test_lazy_validate_multiple_faults_raise_one_error_listing_all(self):
        """All faults must be aggregated into a single StorageConfigError that lists every fix line and the docs URL."""
        config = make_s3_config(uri_format="", bucket_name="", region="")
        with pytest.raises(StorageConfigError) as exc_info:
            config.lazy_validate()
        message = str(exc_info.value)
        assert "You have enabled storage on S3" in message
        assert "- set a value for uri_format" in message
        assert "- set a value for bucket_name" in message
        assert "- set a value for region" in message
        assert URLs.documentation in message

    @pytest.mark.parametrize(
        ("lifespan_setting", "expected_lifespan"),
        [
            pytest.param(3600, 3600, id="int-passthrough"),
            pytest.param("disabled", None, id="disabled-maps-to-none"),
        ],
    )
    def test_signed_urls_lifespan(
        self,
        lifespan_setting: int | Literal["disabled"],
        expected_lifespan: int | None,
    ):
        """signed_urls_lifespan passes integers through and maps the 'disabled' literal to None."""
        config = make_s3_config(signed_urls_lifespan_seconds=lifespan_setting)
        assert config.signed_urls_lifespan == expected_lifespan

    @pytest.mark.parametrize("lifespan_setting", [pytest.param(0, id="zero"), pytest.param(-300, id="negative")])
    def test_lazy_validate_rejects_non_positive_signed_urls_lifespan(self, lifespan_setting: int):
        """A zero or negative lifespan produces immediately-dead signed URLs, so lazy_validate must reject it."""
        config = make_s3_config(signed_urls_lifespan_seconds=lifespan_setting)
        with pytest.raises(StorageConfigError) as exc_info:
            config.lazy_validate()
        assert "- signed_urls_lifespan_seconds must be a positive number of seconds, or 'disabled'" in str(exc_info.value)
