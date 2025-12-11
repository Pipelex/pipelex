import pytest

from pipelex.tools.misc.hash_utils import hash_sha256


class TestHashSha256:
    @pytest.mark.parametrize(
        ("input_string", "length", "expected"),
        [
            # Known SHA256 hashes (first N chars)
            ("hello", None, "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"),
            ("hello", 8, "2cf24dba"),
            ("hello", 16, "2cf24dba5fb0a30e"),
            ("hello", 64, "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"),
            # Empty string
            ("", None, "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
            ("", 8, "e3b0c442"),
            # Short length
            ("test", 1, "9"),
            # Zero length edge case
            ("test", 0, ""),
        ],
    )
    def test_hash_sha256(self, input_string: str, length: int | None, expected: str) -> None:
        """Test SHA256 hashing with various inputs and truncation lengths."""
        assert hash_sha256(input_string, length) == expected

    def test_hash_sha256_deterministic(self) -> None:
        """Test that the same input always produces the same output."""
        input_string = "deterministic_test"
        result1 = hash_sha256(input_string)
        result2 = hash_sha256(input_string)
        assert result1 == result2

    def test_hash_sha256_different_inputs_produce_different_hashes(self) -> None:
        """Test that different inputs produce different hashes."""
        hash1 = hash_sha256("input_a")
        hash2 = hash_sha256("input_b")
        assert hash1 != hash2

    def test_hash_sha256_full_length_is_64_chars(self) -> None:
        """Test that full SHA256 hex digest is 64 characters."""
        result = hash_sha256("any_input")
        assert len(result) == 64
