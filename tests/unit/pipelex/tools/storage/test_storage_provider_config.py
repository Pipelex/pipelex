from typing import Any, Callable

import pytest
from pydantic import BaseModel, ValidationError

from pipelex.tools.storage.exceptions import StorageConfigError
from pipelex.tools.storage.storage_config import (
    StorageConfig,
    StorageGcpConfig,
    StorageInMemoryConfig,
    StorageLocalConfig,
    StorageMethod,
    StorageProviderConfig,
    StorageS3Config,
)

LOCAL_URI_FORMAT = "local-assets/{hash}"
IN_MEMORY_URI_FORMAT = "memory-assets/{hash}"
S3_URI_FORMAT = "s3-assets/{hash}"
GCP_URI_FORMAT = "gcp-assets/{hash}"
LOCAL_STORAGE_PATH = "/opt/pipelex-test-storage"


def make_local_config() -> StorageLocalConfig:
    return StorageLocalConfig(uri_format=LOCAL_URI_FORMAT, local_storage_path=LOCAL_STORAGE_PATH)


def make_in_memory_config() -> StorageInMemoryConfig:
    return StorageInMemoryConfig(uri_format=IN_MEMORY_URI_FORMAT)


def make_s3_config() -> StorageS3Config:
    return StorageS3Config(
        uri_format=S3_URI_FORMAT,
        bucket_name="my-bucket",
        region="eu-west-1",
        signed_urls_lifespan_seconds=3600,
    )


def make_gcp_config() -> StorageGcpConfig:
    return StorageGcpConfig(
        uri_format=GCP_URI_FORMAT,
        bucket_name="my-bucket",
        project_id="my-project",
        signed_urls_lifespan_seconds=3600,
    )


class TestStorageProviderConfig:
    @pytest.mark.parametrize(
        ("method", "field_name", "sub_config_factory"),
        [
            pytest.param(StorageMethod.LOCAL, "local", make_local_config, id="local"),
            pytest.param(StorageMethod.IN_MEMORY, "in_memory", make_in_memory_config, id="in-memory"),
            pytest.param(StorageMethod.S3, "s3", make_s3_config, id="s3"),
            pytest.param(StorageMethod.GCP, "gcp", make_gcp_config, id="gcp"),
        ],
    )
    def test_validator_accepts_method_with_matching_sub_config(
        self,
        method: StorageMethod,
        field_name: str,
        sub_config_factory: Callable[[], BaseModel],
    ):
        """Each storage method constructs fine when its matching sub-config is provided."""
        kwargs: dict[str, Any] = {"method": method, field_name: sub_config_factory()}
        provider_config = StorageProviderConfig(**kwargs)
        assert provider_config.method == method
        assert getattr(provider_config, field_name) is kwargs[field_name]

    @pytest.mark.parametrize(
        ("method", "expected_message"),
        [
            pytest.param(StorageMethod.LOCAL, "local config is required when method is local", id="local"),
            pytest.param(StorageMethod.IN_MEMORY, "in_memory config is required when method is in_memory", id="in-memory"),
            pytest.param(StorageMethod.S3, "s3 config is required when method is s3", id="s3"),
            pytest.param(StorageMethod.GCP, "gcp config is required when method is gcp", id="gcp"),
        ],
    )
    def test_validator_rejects_method_without_matching_sub_config(
        self,
        method: StorageMethod,
        expected_message: str,
    ):
        """Construction raises a StorageConfigError (unwrapped by pydantic) naming the required section."""
        with pytest.raises(StorageConfigError) as exc_info:
            StorageProviderConfig(method=method)
        assert expected_message in str(exc_info.value)

    def test_method_is_open_str_token(self):
        """D1: method is an open str token stored verbatim. A built-in name is a plain string (equal to its
        StorageMethod value), and an unknown/external name is accepted at parse — its installability is
        validated later at registry lookup, not at parse — so a config naming an out-of-tree provider loads.
        """
        provider_config = StorageProviderConfig.model_validate({"method": "local", "local": make_local_config()})
        assert provider_config.method == "local"
        assert provider_config.method == StorageMethod.LOCAL
        external_config = StorageProviderConfig.model_validate({"method": "azure"})
        assert external_config.method == "azure"

    @pytest.mark.parametrize(
        ("method", "field_name", "sub_config_factory", "expected_uri_format"),
        [
            pytest.param(StorageMethod.LOCAL, "local", make_local_config, LOCAL_URI_FORMAT, id="local"),
            pytest.param(StorageMethod.IN_MEMORY, "in_memory", make_in_memory_config, IN_MEMORY_URI_FORMAT, id="in-memory"),
            pytest.param(StorageMethod.S3, "s3", make_s3_config, S3_URI_FORMAT, id="s3"),
            pytest.param(StorageMethod.GCP, "gcp", make_gcp_config, GCP_URI_FORMAT, id="gcp"),
        ],
    )
    def test_uri_format_returns_matching_sub_config_format(
        self,
        method: StorageMethod,
        field_name: str,
        sub_config_factory: Callable[[], BaseModel],
        expected_uri_format: str,
    ):
        """The uri_format property dispatches on method and returns the matching sub-config's uri_format."""
        kwargs: dict[str, Any] = {"method": method, field_name: sub_config_factory()}
        provider_config = StorageProviderConfig(**kwargs)
        assert provider_config.uri_format == expected_uri_format

    @pytest.mark.parametrize(
        ("method", "expected_message"),
        [
            pytest.param(StorageMethod.LOCAL, "local config is required to access uri_format", id="local"),
            pytest.param(StorageMethod.IN_MEMORY, "in_memory config is required to access uri_format", id="in-memory"),
            pytest.param(StorageMethod.S3, "s3 config is required to access uri_format", id="s3"),
            pytest.param(StorageMethod.GCP, "gcp config is required to access uri_format", id="gcp"),
        ],
    )
    def test_uri_format_raises_when_matching_sub_config_is_none(
        self,
        method: StorageMethod,
        expected_message: str,
    ):
        """The uri_format error branches are normally unreachable (the model validator guards construction),
        so we build via model_construct to bypass validation and pin each per-method error message.
        """
        provider_config = StorageProviderConfig.model_construct(method=method)
        with pytest.raises(StorageConfigError) as exc_info:
            _ = provider_config.uri_format
        assert expected_message in str(exc_info.value)

    def test_storage_path_returns_local_storage_path(self):
        """storage_path returns the local sub-config's local_storage_path."""
        provider_config = StorageProviderConfig(method=StorageMethod.LOCAL, local=make_local_config())
        assert provider_config.storage_path == LOCAL_STORAGE_PATH

    def test_storage_path_raises_for_non_local_method_even_with_local_config(self):
        """storage_path dispatches on method: a non-local method raises even when a local sub-config is set."""
        provider_config = StorageProviderConfig(
            method=StorageMethod.S3,
            s3=make_s3_config(),
            local=make_local_config(),
        )
        with pytest.raises(StorageConfigError) as exc_info:
            _ = provider_config.storage_path
        assert "storage_path is only available when method is local" in str(exc_info.value)

    def test_storage_path_raises_when_local_config_is_none(self):
        """The missing-local-config branch is normally unreachable (the model validator guards construction),
        so we build via model_construct to bypass validation and pin its error message.
        """
        provider_config = StorageProviderConfig.model_construct(method=StorageMethod.LOCAL)
        with pytest.raises(StorageConfigError) as exc_info:
            _ = provider_config.storage_path
        assert "local config is required to access storage_path" in str(exc_info.value)

    def test_storage_config_boolean_flags_are_required(self):
        """StorageConfig requires both boolean flags: omitting them fails validation with 'missing' errors."""
        with pytest.raises(ValidationError) as exc_info:
            StorageConfig.model_validate({"method": "in_memory", "in_memory": make_in_memory_config()})
        missing_fields = {error["loc"][0] for error in exc_info.value.errors() if error["type"] == "missing"}
        assert missing_fields == {"is_fetch_remote_content_enabled", "is_upload_local_content_enabled"}

    def test_storage_config_boolean_flags_round_trip_through_model_dump(self):
        """The boolean flags survive a model_dump round-trip with their exact values."""
        storage_config = StorageConfig(
            method=StorageMethod.IN_MEMORY,
            in_memory=make_in_memory_config(),
            is_fetch_remote_content_enabled=True,
            is_upload_local_content_enabled=False,
        )
        dumped = storage_config.model_dump()
        assert dumped["is_fetch_remote_content_enabled"] is True
        assert dumped["is_upload_local_content_enabled"] is False
        rebuilt = StorageConfig.model_validate(dumped, strict=False)
        assert rebuilt == storage_config
