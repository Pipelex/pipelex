import pytest

from pipelex.tools.misc.hash_utils import hash_md5_to_int


class TestHashMd5ToInt:
    @pytest.mark.parametrize(
        ("input_string", "expected"),
        [
            # Known MD5 hashes converted to int
            ("hello", 0x5D41402ABC4B2A76B9719D911017C592),
            ("", 0xD41D8CD98F00B204E9800998ECF8427E),
            ("test", 0x098F6BCD4621D373CADE4E832627B4F6),
        ],
    )
    def test_hash_md5_to_int(self, input_string: str, expected: int) -> None:
        """Test MD5 hashing produces expected integer values."""
        assert hash_md5_to_int(input_string) == expected

    def test_hash_md5_to_int_deterministic(self) -> None:
        """Test that the same input always produces the same output."""
        input_string = "deterministic_test"
        result1 = hash_md5_to_int(input_string)
        result2 = hash_md5_to_int(input_string)
        assert result1 == result2

    def test_hash_md5_to_int_different_inputs_produce_different_values(self) -> None:
        """Test that different inputs produce different integer values."""
        int1 = hash_md5_to_int("input_a")
        int2 = hash_md5_to_int("input_b")
        assert int1 != int2

    def test_hash_md5_to_int_is_128_bit(self) -> None:
        """Test that the result is a 128-bit integer (MD5 produces 128 bits)."""
        result = hash_md5_to_int("any_input")
        assert 0 <= result < 2**128
