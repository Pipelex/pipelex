"""Unit test for ``load_libraries_and_activate`` rejecting a bare path string.

Regression for the public-helper footgun (PR #960): because ``str`` satisfies
``Sequence[str | Path]`` (``Sequence`` is covariant), a bare path string used to be accepted by
type checkers and iterated character-by-character — turning ``"/fake/mylib"`` into the directories
``"/"``, ``"t"``, ``"m"``, ``"p"``, … and scanning the filesystem root. The guard now rejects it
before any library is opened, so this stays a pure unit test (no scan, no leaked library).
"""

import pytest

from pipelex.pipeline.execution_seams import load_libraries_and_activate


class TestLoadLibrariesAndActivate:
    def test_rejects_bare_string(self) -> None:
        """A bare path *string* — statically a valid ``Sequence[str | Path]`` — raises ``TypeError``
        before any library work, so the char-by-char filesystem-root scan can never happen.
        """
        with pytest.raises(TypeError):
            load_libraries_and_activate("/fake/mylib")
