import threading
import time
from types import SimpleNamespace

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
            booted = SimpleNamespace(is_ready=True)
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

    def test_reader_arriving_mid_setup_blocks_until_ready(self, mocker: MockerFixture) -> None:
        """A reader arriving while the first boot is mid-setup must block, not adopt a half-built instance.

        Thread A enters a patched ``make`` that registers an instance with ``is_ready=False`` -- the
        half-built window the metaclass exposes -- then completes "setup" and flips ``is_ready=True`` only
        just before returning. Threads B and C start after A has registered, so they hit the lock-free fast
        path against a registered-but-not-ready instance. Gating on ``is_fully_booted()`` (not bare
        presence) must force them onto the lock; they must not return until A finished. ``make`` runs once.
        """
        make_calls = 0
        instance_holder: list[SimpleNamespace] = []
        a_registered = threading.Event()
        a_may_finish = threading.Event()

        def fake_get_optional_instance() -> SimpleNamespace | None:
            return instance_holder[0] if instance_holder else None

        def fake_make(**_kwargs: object) -> SimpleNamespace:
            nonlocal make_calls
            make_calls += 1
            if instance_holder:
                # Faithful to the real make: it raises if a singleton already exists. Surfaces loudly if a
                # reader ever slips past the lock into a second make during the window.
                msg = "Pipelex is already initialized"
                raise PipelexSetupError(msg)
            half_built = SimpleNamespace(is_ready=False)
            instance_holder.append(half_built)  # registered, NOT ready (mirrors pipelex.py construct-then-setup)
            a_registered.set()
            assert a_may_finish.wait(timeout=5.0), "test failed to release thread A"
            half_built.is_ready = True  # mirrors the is_ready flip on make's success tail
            return half_built

        mocker.patch.object(Pipelex, "get_optional_instance", side_effect=fake_get_optional_instance)
        mocker.patch.object(Pipelex, "make", side_effect=fake_make)

        boot_errors: list[PipelexSetupError] = []
        observed_not_ready: list[bool] = []

        def reader() -> None:
            try:
                ensure_pipelex_booted()
            except PipelexSetupError as exc:
                boot_errors.append(exc)
                return
            current = instance_holder[0] if instance_holder else None
            if current is not None and not current.is_ready:
                observed_not_ready.append(True)

        thread_a = threading.Thread(target=reader, daemon=True)
        thread_a.start()
        assert a_registered.wait(timeout=5.0), "thread A never registered the instance"

        thread_b = threading.Thread(target=reader, daemon=True)
        thread_c = threading.Thread(target=reader, daemon=True)
        thread_b.start()
        thread_c.start()
        time.sleep(0.05)  # let B and C reach and block on _boot_lock during A's window
        assert thread_b.is_alive(), "thread B returned before A finished setup -- read a half-built instance"
        assert thread_c.is_alive(), "thread C returned before A finished setup -- read a half-built instance"

        a_may_finish.set()
        for thread in (thread_a, thread_b, thread_c):
            thread.join(timeout=5.0)
            assert not thread.is_alive(), "a worker deadlocked on _boot_lock"

        assert boot_errors == []
        assert make_calls == 1
        assert len(instance_holder) == 1
        assert observed_not_ready == []

    def test_setup_failure_lets_next_thread_reboot(self, mocker: MockerFixture) -> None:
        """A setup failure that deletes the instance must let a thread waiting in the window re-boot.

        Thread A's patched ``make`` registers a half-built instance, signals, waits, then mimics make's
        delete-on-failure (clears the holder) and raises. Thread B arrives during A's window; gating on
        ``is_fully_booted()`` (False throughout) keeps it on the lock, and once A fails and removes the
        instance B re-checks, sees nothing booted, and re-boots to a ready instance -- it must NOT proceed
        against the deleted instance.
        """
        make_calls = 0
        instance_holder: list[SimpleNamespace] = []
        a_registered = threading.Event()
        a_may_finish = threading.Event()

        def fake_get_optional_instance() -> SimpleNamespace | None:
            return instance_holder[0] if instance_holder else None

        def fake_make(**_kwargs: object) -> SimpleNamespace:
            nonlocal make_calls
            make_calls += 1
            if instance_holder:
                msg = "Pipelex is already initialized"
                raise PipelexSetupError(msg)
            if not a_registered.is_set():
                # First call (thread A): register half-built, then fail + delete (mirrors make try/except).
                half_built = SimpleNamespace(is_ready=False)
                instance_holder.append(half_built)
                a_registered.set()
                assert a_may_finish.wait(timeout=5.0), "test failed to release thread A"
                instance_holder.clear()  # mirrors `del MetaSingleton.instances[cls]` on failure
                msg = "boom during setup"
                raise PipelexSetupError(msg)
            # Second call (thread B): clean re-boot.
            ready = SimpleNamespace(is_ready=True)
            instance_holder.append(ready)
            return ready

        mocker.patch.object(Pipelex, "get_optional_instance", side_effect=fake_get_optional_instance)
        mocker.patch.object(Pipelex, "make", side_effect=fake_make)

        results: dict[str, PipelexSetupError | None] = {}

        def reader(name: str) -> None:
            try:
                ensure_pipelex_booted()
                results[name] = None
            except PipelexSetupError as exc:
                results[name] = exc

        thread_a = threading.Thread(target=reader, args=("A",), daemon=True)
        thread_a.start()
        assert a_registered.wait(timeout=5.0), "thread A never registered the instance"

        thread_b = threading.Thread(target=reader, args=("B",), daemon=True)
        thread_b.start()
        time.sleep(0.05)  # let B reach and block on _boot_lock during A's window
        assert thread_b.is_alive(), "thread B returned during A's setup window -- read a doomed instance"

        a_may_finish.set()
        for thread in (thread_a, thread_b):
            thread.join(timeout=5.0)
            assert not thread.is_alive(), "a worker deadlocked on _boot_lock"

        assert isinstance(results["A"], PipelexSetupError)
        assert results["B"] is None
        assert make_calls == 2  # A failed, B succeeded
        assert len(instance_holder) == 1
        assert instance_holder[0].is_ready is True
