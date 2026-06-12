import pytest

from pipelex.tools.storage.exceptions import StorageConfigError
from pipelex.tools.storage.storage_config import StorageInMemoryConfig
from pipelex.urls import URLs


class TestStorageInMemoryConfig:
    def test_lazy_validate_valid_config_passes_silently(self):
        """A valid in-memory config must pass lazy_validate without raising."""
        config = StorageInMemoryConfig(uri_format="memory-assets/{hash}")
        config.lazy_validate()

    @pytest.mark.parametrize(
        ("uri_format", "expected_fragment"),
        [
            pytest.param("", "- set a value for uri_format", id="empty-uri-format"),
            pytest.param("assets/no-placeholder/file", "- uri_format must contain a {hash} placeholder", id="uri-no-hash"),
            pytest.param("assets/myhash/file", "- uri_format must contain a {hash} placeholder", id="uri-bare-hash"),
            pytest.param("assets/{{hash}}/file", "- uri_format must contain a {hash} placeholder", id="uri-escaped-hash"),
            pytest.param("assets/{hash/file", "- uri_format is not a valid format string", id="uri-malformed-format"),
        ],
    )
    def test_lazy_validate_single_fault(
        self,
        uri_format: str,
        expected_fragment: str,
    ):
        """Each uri_format fault must raise a StorageConfigError naming the fault and pointing to the docs."""
        config = StorageInMemoryConfig(uri_format=uri_format)
        with pytest.raises(StorageConfigError) as exc_info:
            config.lazy_validate()
        message = str(exc_info.value)
        assert "You have enabled storage on in_memory" in message
        assert expected_fragment in message
        assert URLs.documentation in message
