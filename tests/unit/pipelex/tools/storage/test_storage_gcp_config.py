from typing import Literal

import pytest

from pipelex.tools.storage.exceptions import StorageConfigError
from pipelex.tools.storage.storage_config import StorageGcpConfig
from pipelex.urls import URLs


def make_gcp_config(
    uri_format: str = "gcp-assets/{hash}",
    bucket_name: str = "my-bucket",
    project_id: str = "my-project",
    signed_urls_lifespan_seconds: int | Literal["disabled"] = 3600,
) -> StorageGcpConfig:
    return StorageGcpConfig(
        uri_format=uri_format,
        bucket_name=bucket_name,
        project_id=project_id,
        signed_urls_lifespan_seconds=signed_urls_lifespan_seconds,
    )


class TestStorageGcpConfig:
    def test_lazy_validate_valid_config_passes_silently(self):
        """A fully valid GCP config must pass lazy_validate without raising."""
        config = make_gcp_config()
        config.lazy_validate()

    @pytest.mark.parametrize(
        ("uri_format", "bucket_name", "project_id", "expected_fragment"),
        [
            pytest.param("", "my-bucket", "my-project", "- set a value for uri_format", id="empty-uri-format"),
            pytest.param("assets/no-placeholder/file", "my-bucket", "my-project", "- uri_format must contain a {hash} placeholder", id="uri-no-hash"),
            pytest.param("assets/myhash/file", "my-bucket", "my-project", "- uri_format must contain a {hash} placeholder", id="uri-bare-hash"),
            pytest.param("gcp-assets/{hash}", "", "my-project", "- set a value for bucket_name", id="empty-bucket-name"),
            pytest.param("gcp-assets/{hash}", "my.bucket", "my-project", "- bucket_name cannot contain a dot", id="bucket-with-dot"),
            pytest.param("gcp-assets/{hash}", "my/bucket", "my-project", "- bucket_name cannot contain a slash", id="bucket-with-slash"),
            pytest.param("gcp-assets/{hash}", "my-bucket", "", "- set a value for project_id", id="empty-project-id"),
        ],
    )
    def test_lazy_validate_single_fault(
        self,
        uri_format: str,
        bucket_name: str,
        project_id: str,
        expected_fragment: str,
    ):
        """Each individual config fault must raise a StorageConfigError naming the fault and pointing to the docs.

        The bare-hash row pins that a 'hash' substring without braces is rejected: only the literal '{hash}'
        placeholder gives uri_format.format() a substitution slot, matching the S3 validation.
        """
        config = make_gcp_config(uri_format=uri_format, bucket_name=bucket_name, project_id=project_id)
        with pytest.raises(StorageConfigError) as exc_info:
            config.lazy_validate()
        message = str(exc_info.value)
        assert "You have enabled storage on GCP" in message
        assert expected_fragment in message
        assert URLs.documentation in message

    def test_lazy_validate_multiple_faults_raise_one_error_listing_all(self):
        """All faults must be aggregated into a single StorageConfigError that lists every fix line and the docs URL."""
        config = make_gcp_config(uri_format="", bucket_name="", project_id="")
        with pytest.raises(StorageConfigError) as exc_info:
            config.lazy_validate()
        message = str(exc_info.value)
        assert "You have enabled storage on GCP" in message
        assert "- set a value for uri_format" in message
        assert "- set a value for bucket_name" in message
        assert "- set a value for project_id" in message
        assert URLs.documentation in message

    @pytest.mark.parametrize(
        ("lifespan_setting", "expected_lifespan"),
        [
            pytest.param(3600, 3600, id="int-passthrough"),
            pytest.param(0, 0, id="zero-passthrough"),
            pytest.param("disabled", None, id="disabled-maps-to-none"),
        ],
    )
    def test_signed_urls_lifespan(
        self,
        lifespan_setting: int | Literal["disabled"],
        expected_lifespan: int | None,
    ):
        """signed_urls_lifespan passes integers through and maps the 'disabled' literal to None."""
        config = make_gcp_config(signed_urls_lifespan_seconds=lifespan_setting)
        assert config.signed_urls_lifespan == expected_lifespan
