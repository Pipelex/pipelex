from pipelex.config import get_config
from pipelex.tools.storage.storage_config import StorageMethod


class TestStorageConfigIntegration:
    """Integration tests for storage config values."""

    def test_config_has_local_uri_format(self) -> None:
        """Test that local storage config has uri_format defined."""
        storage_config = get_config().pipelex.storage_config
        assert storage_config.local is not None
        assert storage_config.local.uri_format is not None
        assert "{primary_id}" in storage_config.local.uri_format
        assert "{secondary_id}" in storage_config.local.uri_format
        assert "{hash}" in storage_config.local.uri_format
        assert "{extension}" in storage_config.local.uri_format

    def test_config_has_in_memory_uri_format(self) -> None:
        """Test that in-memory storage config has uri_format defined."""
        storage_config = get_config().pipelex.storage_config
        assert storage_config.in_memory is not None
        assert storage_config.in_memory.uri_format is not None
        assert "{primary_id}" in storage_config.in_memory.uri_format
        assert "{secondary_id}" in storage_config.in_memory.uri_format
        assert "{hash}" in storage_config.in_memory.uri_format
        assert "{extension}" in storage_config.in_memory.uri_format

    def test_uri_format_property_returns_correct_format_for_local(self) -> None:
        """Test that the uri_format property returns the correct format when method is local."""
        storage_config = get_config().pipelex.storage_config
        match storage_config.method:
            case StorageMethod.LOCAL:
                assert storage_config.local is not None
                assert storage_config.uri_format == storage_config.local.uri_format
            case StorageMethod.IN_MEMORY:
                assert storage_config.in_memory is not None
                assert storage_config.uri_format == storage_config.in_memory.uri_format
            case StorageMethod.S3:
                assert storage_config.s3 is not None
                assert storage_config.uri_format == storage_config.s3.uri_format
            case StorageMethod.GCP:
                assert storage_config.gcp is not None
                assert storage_config.uri_format == storage_config.gcp.uri_format
            case _:
                # External method token (D1): no built-in sub-config to compare against.
                pass
