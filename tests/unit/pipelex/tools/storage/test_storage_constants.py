from pipelex.tools.storage.storage_provider_abstract import PIPELEX_STORAGE_SCHEME


class TestStorageConstants:
    """Unit tests for storage module constants."""

    def test_pipelex_storage_scheme_constant_value(self) -> None:
        """Test that PIPELEX_STORAGE_SCHEME has the expected value."""
        assert PIPELEX_STORAGE_SCHEME == "pipelex-storage://"

    def test_pipelex_storage_scheme_ends_with_colon_slash_slash(self) -> None:
        """Test that the scheme follows URI convention with :// suffix."""
        assert PIPELEX_STORAGE_SCHEME.endswith("://")

    def test_pipelex_storage_scheme_is_lowercase(self) -> None:
        """Test that the scheme is lowercase (URI scheme convention)."""
        assert PIPELEX_STORAGE_SCHEME.lower() == PIPELEX_STORAGE_SCHEME
