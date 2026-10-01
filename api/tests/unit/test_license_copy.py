"""The server's `LICENSE` is a copy of the repository's, and must stay one.

A distribution carries license files only from inside its own project directory, and a symlink would
dangle in the sdist, so `pipelex-api` ships a real copy of the repository's `LICENSE` beside its
`pyproject.toml`. This keeps the copy from drifting when the original changes.
"""

from pathlib import Path

_MEMBER_ROOT = Path(__file__).resolve().parents[2]
_REPOSITORY_ROOT = _MEMBER_ROOT.parent


class TestLicenseCopy:
    def test_member_license_is_the_repository_license(self) -> None:
        member_license = _MEMBER_ROOT / "LICENSE"
        repository_license = _REPOSITORY_ROOT / "LICENSE"
        assert member_license.read_bytes() == repository_license.read_bytes(), (
            f"{member_license} differs from {repository_license}: copy the repository's LICENSE over it."
        )
