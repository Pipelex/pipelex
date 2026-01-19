import hashlib


def hash_sha256(data: str | bytes, length: int | None = None) -> str:
    """Hash the data using truncated SHA256.

    Uses the first `length` characters of SHA256 hex digest, which provides
    collision resistance for practical purposes while being compact.

    Args:
        data: The string or bytes to hash.
        length: The length of the hash to return.

    Returns:
        First `length` characters of SHA256 hex digest if length is provided, otherwise the full hash.
    """
    data_bytes = data.encode("utf-8") if isinstance(data, str) else data
    the_hash = hashlib.sha256(data_bytes).hexdigest()
    if length is not None:
        return the_hash[:length]
    return the_hash


def hash_md5_to_int(string: str) -> int:
    """Convert a string to an integer using MD5 hash (deterministic).

    Uses MD5 hash to generate a consistent integer from the input string.
    This is useful for creating deterministic numeric identifiers from strings.

    Args:
        string: The string to hash.

    Returns:
        A 128-bit integer derived from the MD5 hash of the input string.
    """
    return int(hashlib.md5(string.encode("utf-8")).hexdigest(), 16)  # noqa: S324
