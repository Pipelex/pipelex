from typing import ClassVar


class MethodLockTestData:
    """An invented locked dependency, and the `methods.lock` files a calling method could carry for it; nothing here is real."""

    ADDRESS: ClassVar[str] = "github.com/invented/locked-lib/scoring"
    ADDRESS_IN_OTHER_CASE: ClassVar[str] = "github.com/Invented/Locked-Lib/scoring"
    OTHER_ADDRESS: ClassVar[str] = "github.com/invented/other-lib/ranking"
    LOCKED_VERSION: ClassVar[str] = "1.0.0"
    FETCHED_VERSION: ClassVar[str] = "1.2.0"
    LOCKED_DIGEST: ClassVar[str] = "sha256:" + "a" * 64
    FETCHED_DIGEST: ClassVar[str] = "sha256:" + "b" * 64

    BUNDLE: ClassVar[str] = 'domain = "lock_tests"\n'

    @classmethod
    def lock_naming(cls, *, address: str, digest: str, version: str = LOCKED_VERSION) -> str:
        """A `methods.lock` holding one entry, for `address` at `version` with the tree digest `digest`."""
        return f'["{address}"]\nversion = "{version}"\ndigest  = "{digest}"\nsource  = "https://github.com/invented/locked-lib.git"\n'

    @classmethod
    def legacy_lock_naming(cls, *, address: str) -> str:
        """A `methods.lock` written before tree digests, its entry recording a `hash`."""
        return f'["{address}"]\nversion = "1.0.0"\nhash    = "sha256:{"c" * 64}"\nsource  = "https://github.com/invented/locked-lib.git"\n'
