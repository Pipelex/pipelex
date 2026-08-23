# Full-suite pytest can hang AFTER the summary line (leaked non-daemon threads)

On 2026-08-23 a full `make test` run printed its complete summary (`1 failed, 10984 passed … in 0:12:24`) and then never exited. A `sample` of the process showed the main thread in `Py_Finalize -> atexit_callfuncs -> threading._shutdown -> ThreadHandle_join`, waiting forever on non-daemon worker threads, all parked in `lock_PyThread_acquire_lock` (the `queue.Queue.get()` consumer shape). The last test output before the summary came from `tests/integration/pipelex/system/pipelex_service/test_setup_with_cache.py` telemetry tests, so the prime suspect is a telemetry/analytics consumer thread created during a setup test and never flushed/joined. py-spy could not name the threads (requires root on macOS).

The hang is intermittent — the two checkpoint `make test` runs on the same branch exited normally — and predates the Engine-hints diff (which touches no threading or telemetry code). `make agent-test-debug` already guards against this class with an outer wall-clock timeout; plain `make test` does not.

Suggested fix direction (deferred): make the telemetry client used in setup tests either daemon-threaded or explicitly shut down in the test/fixture teardown; or add the outer timeout to `make test` the way `agent-test-debug` has one.
