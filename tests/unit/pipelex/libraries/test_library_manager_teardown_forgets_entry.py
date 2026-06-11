"""Guards for ``LibraryManager`` teardown bookkeeping when ``library.teardown()`` raises.

Today every sub-teardown is a plain dict reassignment that cannot raise, so the raising
path is unreachable — but "teardown never raises" is an accident, not a contract. If a
future ``Library.teardown`` does real work and raises, the manager must still forget the
entry: a kept entry would turn ``open_fresh_library`` into a deterministic re-raise on
every rerun of that library id on this worker (permanent worker-local poison).
"""

import pytest
from pytest_mock import MockerFixture

from pipelex.libraries.exceptions import LibraryError
from pipelex.libraries.library import Library
from pipelex.libraries.library_manager import LibraryManager

_POISONED_LIBRARY_ID = "poisoned_lib"


class TestLibraryManagerTeardownForgetsEntry:
    def test_teardown_forgets_entry_when_library_teardown_raises(self, mocker: MockerFixture) -> None:
        """The entry must be forgotten even when ``library.teardown()`` raises."""
        manager = LibraryManager()
        manager.open_library(library_id=_POISONED_LIBRARY_ID)
        mocker.patch.object(Library, "teardown", side_effect=RuntimeError("boom"))

        with pytest.raises(RuntimeError, match="boom"):
            manager.teardown(library_id=_POISONED_LIBRARY_ID)

        # The entry must be gone: a second teardown reports a missing library
        # instead of re-raising the poisoned library's teardown error.
        with pytest.raises(LibraryError):
            manager.teardown(library_id=_POISONED_LIBRARY_ID)

    def test_open_fresh_library_proceeds_when_stale_teardown_raises(self, mocker: MockerFixture) -> None:
        """A raising stale teardown must not fail the fresh open itself — worker-local
        leak state must never decide whether a fresh run's setup succeeds (M1 class).
        """
        manager = LibraryManager()
        _library_id, poisoned_library = manager.open_library(library_id=_POISONED_LIBRARY_ID)
        mocker.patch.object(Library, "teardown", side_effect=RuntimeError("boom"))

        fresh_library = manager.open_fresh_library(library_id=_POISONED_LIBRARY_ID)

        assert fresh_library is not poisoned_library
        assert manager.get_library(library_id=_POISONED_LIBRARY_ID) is fresh_library

    def test_open_fresh_library_recovers_after_raising_teardown(self, mocker: MockerFixture) -> None:
        """A raising teardown must not poison subsequent ``open_fresh_library`` calls."""
        manager = LibraryManager()
        _library_id, poisoned_library = manager.open_library(library_id=_POISONED_LIBRARY_ID)
        mocker.patch.object(Library, "teardown", side_effect=RuntimeError("boom"))

        with pytest.raises(RuntimeError, match="boom"):
            manager.teardown(library_id=_POISONED_LIBRARY_ID)

        mocker.stopall()
        fresh_library = manager.open_fresh_library(library_id=_POISONED_LIBRARY_ID)
        assert fresh_library is not poisoned_library
        assert manager.get_library(library_id=_POISONED_LIBRARY_ID) is fresh_library

    def test_full_teardown_forgets_all_entries_when_a_library_teardown_raises(self, mocker: MockerFixture) -> None:
        """The full-teardown branch (``library_id=None``) shares the forget-even-on-raise contract,
        AND attempts every library's own teardown — a raise from one library must not skip the
        resource-closing of the others.
        """
        manager = LibraryManager()
        manager.open_library(library_id="lib_a")
        manager.open_library(library_id="lib_b")
        teardown_mock = mocker.patch.object(Library, "teardown", side_effect=RuntimeError("boom"))

        with pytest.raises(RuntimeError, match="boom"):
            manager.teardown()

        # Every library's teardown must have been ATTEMPTED, not just the first raising one.
        assert teardown_mock.call_count == 2, "a raising teardown must not skip the remaining libraries' teardowns"

        # And ALL entries must be gone — a raising teardown mid-loop must not strand the
        # remaining libraries (or the bookkeeping maps) in the manager.
        mocker.stopall()
        with pytest.raises(LibraryError):
            manager.teardown(library_id="lib_a")
        with pytest.raises(LibraryError):
            manager.teardown(library_id="lib_b")
