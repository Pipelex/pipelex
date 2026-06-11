"""Best-effort teardown contract of ``scoped_library_for_crate``.

The teardown in the ``finally`` must neither mask the body's in-flight exception nor
fail an otherwise-successful call: ``LibraryManager`` forgets the entry pop-first even
when the library's own teardown raises, so suppressing the teardown error is safe.
"""

import pytest
from pytest_mock import MockerFixture

from pipelex.hub import get_library_manager
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.runtime_bridge.primitives.scoped_library import scoped_library_for_crate


def _run_scope_with_failing_body(fake_crate: LibraryCrate, captured_library_ids: list[str]) -> None:
    with scoped_library_for_crate(fake_crate, library_id_prefix="test_scope") as library_id:
        assert library_id is not None
        captured_library_ids.append(library_id)
        msg = "body boom"
        raise ValueError(msg)


class TestScopedLibraryBestEffortTeardown:
    def test_teardown_failure_does_not_fail_successful_body(self, mocker: MockerFixture) -> None:
        fake_crate = mocker.MagicMock(spec=LibraryCrate)
        library_manager = get_library_manager()
        mocker.patch.object(library_manager, "load_from_crate", return_value=None)
        teardown_mock = mocker.patch.object(library_manager, "teardown", side_effect=RuntimeError("teardown boom"))

        scoped_library_id: str | None = None
        with scoped_library_for_crate(fake_crate, library_id_prefix="test_scope") as library_id:
            assert library_id is not None
            scoped_library_id = library_id

        assert teardown_mock.call_count == 1

        # The mocked teardown left the scoped entry registered on the singleton — clean it up.
        mocker.stopall()
        assert scoped_library_id is not None
        library_manager.teardown(library_id=scoped_library_id)

    def test_teardown_failure_does_not_mask_body_exception(self, mocker: MockerFixture) -> None:
        fake_crate = mocker.MagicMock(spec=LibraryCrate)
        library_manager = get_library_manager()
        mocker.patch.object(library_manager, "load_from_crate", return_value=None)
        teardown_mock = mocker.patch.object(library_manager, "teardown", side_effect=RuntimeError("teardown boom"))

        captured_library_ids: list[str] = []
        with pytest.raises(ValueError, match="body boom"):
            _run_scope_with_failing_body(fake_crate, captured_library_ids)

        assert teardown_mock.call_count == 1

        # The mocked teardown left the scoped entry registered on the singleton — clean it up.
        mocker.stopall()
        assert len(captured_library_ids) == 1
        library_manager.teardown(library_id=captured_library_ids[0])
