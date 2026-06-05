import threading
import time

from pytest_mock import MockerFixture

from pipelex.base_exceptions import PipelexSetupError
from pipelex.pipelex import Pipelex
from pipelex.runtime_bridge.bootstrap import ensure_pipelex_booted


class TestEnsurePipelexBootedConcurrency:
    def test_concurrent_first_calls_boot_once_without_error(self, mocker: MockerFixture) -> None:
        """Two threads hitting a fresh singleton must boot exactly once, no error.

        Without the double-checked lock both threads pass the ``is None`` check
        and both call ``Pipelex.make``; the loser then raises
        ``PipelexSetupError("Pipelex is already initialized")``. The lock must
        serialize them so ``make`` runs once and the sibling re-checks and skips.
        """
        make_calls = 0
        instance_holder: list[object] = []  # empty == not booted, [obj] == booted

        def fake_get_optional_instance() -> object | None:
            return instance_holder[0] if instance_holder else None

        def fake_make(**_kwargs: object) -> object:
            nonlocal make_calls
            make_calls += 1
            if instance_holder:
                # Faithfully reproduce the real make: it raises if a singleton already exists.
                msg = "Pipelex is already initialized"
                raise PipelexSetupError(msg)
            booted = object()
            instance_holder.append(booted)
            # Hold "inside make" so the sibling thread is forced to wait on the
            # lock and re-check, rather than racing the check-then-make.
            time.sleep(0.05)
            return booted

        mocker.patch.object(Pipelex, "get_optional_instance", side_effect=fake_get_optional_instance)
        mocker.patch.object(Pipelex, "make", side_effect=fake_make)

        start_barrier = threading.Barrier(2)
        boot_errors: list[PipelexSetupError] = []

        def worker() -> None:
            start_barrier.wait()
            try:
                ensure_pipelex_booted()
            except PipelexSetupError as exc:
                boot_errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert boot_errors == []
        assert make_calls == 1
        assert len(instance_holder) == 1
