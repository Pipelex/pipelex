import pytest

from pipelex.tools.storage.exceptions import StorageConfigError
from pipelex.tools.storage.storage_config import StorageLocalConfig
from pipelex.urls import URLs


def make_local_config(
    uri_format: str = "local-assets/{hash}",
    local_storage_path: str = ".pipelex/storage",
) -> StorageLocalConfig:
    return StorageLocalConfig(uri_format=uri_format, local_storage_path=local_storage_path)


class TestStorageLocalConfig:
    def test_lazy_validate_valid_config_passes_silently(self):
        """A fully valid local config must pass lazy_validate without raising."""
        config = make_local_config()
        config.lazy_validate()

    @pytest.mark.parametrize(
        ("uri_format", "local_storage_path", "expected_fragment"),
        [
            pytest.param("", ".pipelex/storage", "- set a value for uri_format", id="empty-uri-format"),
            pytest.param("assets/no-placeholder/file", ".pipelex/storage", "- uri_format must contain a {hash} placeholder", id="uri-no-hash"),
            pytest.param("assets/myhash/file", ".pipelex/storage", "- uri_format must contain a {hash} placeholder", id="uri-bare-hash"),
            pytest.param("local-assets/{hash}", "", "- set a value for local_storage_path", id="empty-storage-path"),
        ],
    )
    def test_lazy_validate_single_fault(
        self,
        uri_format: str,
        local_storage_path: str,
        expected_fragment: str,
    ):
        """Each individual config fault must raise a StorageConfigError naming the fault and pointing to the docs."""
        config = make_local_config(uri_format=uri_format, local_storage_path=local_storage_path)
        with pytest.raises(StorageConfigError) as exc_info:
            config.lazy_validate()
        message = str(exc_info.value)
        assert "You have enabled storage on local" in message
        assert expected_fragment in message
        assert URLs.documentation in message

    def test_lazy_validate_multiple_faults_raise_one_error_listing_all(self):
        """All faults must be aggregated into a single StorageConfigError that lists every fix line and the docs URL."""
        config = make_local_config(uri_format="", local_storage_path="")
        with pytest.raises(StorageConfigError) as exc_info:
            config.lazy_validate()
        message = str(exc_info.value)
        assert "You have enabled storage on local" in message
        assert "- set a value for uri_format" in message
        assert "- set a value for local_storage_path" in message
        assert URLs.documentation in message
