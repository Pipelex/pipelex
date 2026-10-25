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

    # Each case: a topic, the fetched copy as (its version, the tag the reference pins, the tag the copy was fetched at),
    # the fragments the refusal's message holds, and those it must not hold. The lock records LOCKED_VERSION.
    MISMATCH_MESSAGE_CASES: ClassVar[list[tuple[str, tuple[str, str | None, str | None], list[str], list[str]]]] = [
        (
            "an unpinned reference fetched another version",
            ("1.2.0", None, None),
            ["The lock records another version than the one fetched", "pin the reference to the locked version", "record version 1.2.0"],
            ["installed copy"],
        ),
        (
            "the reference pins another version, fetched at that tag",
            ("1.2.0", "v1.2.0", "v1.2.0"),
            ["The reference pins the tag v1.2.0, another version than the lock records", "pin the reference to the locked version"],
            ["installed copy"],
        ),
        (
            "the reference pins the locked version, an installed copy of another was used",
            ("1.2.0", "v1.0.0", None),
            [
                "The reference pins the tag v1.0.0, but an installed copy of version 1.2.0, fetched earlier at the repository's default branch",
                "remove that installed copy so the pinned tag is fetched",
            ],
            ["pin the reference to the locked version", "pin the reference to it"],
        ),
        (
            "the reference pins a third version, an installed copy fetched at another tag was used",
            ("1.2.0", "v2.0.0", "v1.2.0"),
            [
                "The reference pins the tag v2.0.0, but an installed copy of version 1.2.0, fetched earlier at the tag v1.2.0",
                "remove that installed copy so the pinned tag is fetched",
                "The pinned tag does not name the locked version 1.0.0 either",
            ],
            [],
        ),
        (
            "the locked version, another tree",
            ("1.0.0", None, None),
            [],
            ["pin the reference", "installed copy"],
        ),
    ]

    @classmethod
    def lock_naming(cls, *, address: str, digest: str, version: str = LOCKED_VERSION) -> str:
        """A `methods.lock` holding one entry, for `address` at `version` with the tree digest `digest`."""
        return f'["{address}"]\nversion = "{version}"\ndigest  = "{digest}"\nsource  = "https://github.com/invented/locked-lib.git"\n'

    @classmethod
    def legacy_lock_naming(cls, *, address: str) -> str:
        """A `methods.lock` written before tree digests, its entry recording a `hash`."""
        return f'["{address}"]\nversion = "1.0.0"\nhash    = "sha256:{"c" * 64}"\nsource  = "https://github.com/invented/locked-lib.git"\n'
