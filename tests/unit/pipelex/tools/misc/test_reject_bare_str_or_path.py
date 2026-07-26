"""Unit tests for ``reject_bare_str_or_path`` — the guard that stops a bare ``str``/``Path`` from
being passed where a ``Sequence[str | Path]`` is expected (where it would be iterated
character-by-character) — and for its wiring into the public functions that take such a sequence.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from pipelex.interpreter_hub import resolve_library_dirs
from pipelex.tools.misc.file_utils import reject_bare_str_or_path
from pipelex.tools.misc.toml_utils import load_toml_from_path_and_merge_with_overrides


class TestRejectBareStrOrPath:
    @pytest.mark.parametrize(
        "bad_value",
        [
            "/fake/mylib",
            Path("/fake/mylib"),
        ],
    )
    def test_rejects_bare_str_or_path(self, bad_value: object) -> None:
        """A bare ``str`` or ``Path`` is rejected with a ``TypeError`` that names the param and hints the fix."""
        with pytest.raises(TypeError) as exc_info:
            reject_bare_str_or_path(bad_value, param_name="library_dirs")
        message = str(exc_info.value)
        assert "library_dirs" in message
        assert "[" in message  # the message tells the caller to wrap the value in a list

    @pytest.mark.parametrize(
        "good_value",
        [
            None,
            [],
            [Path("/fake/a"), Path("/fake/b")],
            ("/fake/a", "/fake/b"),
        ],
    )
    def test_passes_through_sequences_and_none(self, good_value: object) -> None:
        """``None`` and any real sequence of paths fall through untouched (no raise)."""
        reject_bare_str_or_path(good_value, param_name="library_dirs")

    @pytest.mark.parametrize(
        "func",
        [
            resolve_library_dirs,
            load_toml_from_path_and_merge_with_overrides,
        ],
    )
    def test_public_sequence_consumers_reject_bare_string(self, func: Callable[[str], object]) -> None:
        """Each public function taking ``Sequence[str | Path]`` rejects a bare string at its boundary.

        Pins the guard wiring so a future refactor that drops a call is caught. A bare ``str`` is
        statically a valid ``Sequence[str | Path]`` (the footgun), so no type-ignore is needed here.
        """
        with pytest.raises(TypeError):
            func("/fake/mylib")
