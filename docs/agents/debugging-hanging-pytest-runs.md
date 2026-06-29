# Playbook: debugging a hanging pytest run in one shot

**Audience.** Future-me (or any agent) the next time a `make agent-test` / `pytest -n auto` run in this repo hangs without finishing. The common causes here are xdist worker crash-and-replace cycles and fixture-teardown hangs; the iteration loop below generalizes to any hanging suite.

!!! note "This playbook covers the core `pipelex` suite"
    Core `pipelex` has no `temporalio` dependency and spawns no Temporal processes — the Temporal distributed-execution backend is a separate, external product with its own test suite. If a hang traces into `temporalio` or a `temporal-sdk-python` process, it is coming from that separate suite, not from anything in this repo, and this playbook does not apply.

**Why this exists.** It is easy to burn ~30 minutes across multiple test runs that all hang or get killed, requiring the user to flag the hang each time. Every individual decision can be defensible while the *iteration loop* is broken. Following the playbook below, the whole thing — code fix, verify unit, find the real failure, fix it, verify again — should finish in one autonomous pass.

---

## The anti-patterns (concrete, in order)

1. **`make agent-test` is silent on success.** Backgrounding it and waiting for a harness notification gives no progress signal — the output file can stay 0 bytes for many minutes. → No way to tell hung from slow.

2. **`-q` buffers harder.** It holds output until session-end. Use `-v` for debug runs.

3. **`| tail -80` buffers too.** Pipe buffering means tail receives nothing until pytest exits. Use a direct file redirect (`> file 2>&1`), not a pipe.

4. **`--timeout=120 --timeout-method=thread` does not bound the run.** A per-test timeout doesn't catch **fixture-teardown hangs** and doesn't catch xdist's **worker-crash-and-replace cycle**, which can loop indefinitely retrying failed tests. You need an outer wall-clock cap too.

5. **Zombie processes between runs.** Leftover `pytest` sessions (PPID=1 after their parents died) accumulate, each holding resources. Compounding contention makes each new run slower and more crash-prone. Blanket-kill before every run.

6. **Concurrent pytest sessions.** Yours plus a leftover from an earlier attempt. `pkill` of one PID does not kill the tree; do a blanket `pkill -9 -f pytest` first.

7. **`while kill -0 $PID; do sleep 10; done`** is bounded by pytest's own runtime — i.e., not bounded at all when pytest hangs. No outer wall-clock cap.

8. **Grepping for `FAILED tests/` misses the actual error.** The smoking gun is often a specific error message buried deep in a long log, sometimes inside a non-pytest log line — not on a `FAILED` line. Grep for the error **class name** directly from the start.

9. **Trusting xdist output as the source of truth.** Worker crashes (`node down: Not properly terminated`) plus worker replacement make it impossible to tell a real bug from xdist flakiness. The truth comes from running serially.

---

## The right iteration loop

### Before any test run

```bash
pkill -9 -f "pytest" 2>/dev/null
sleep 1
ps -ef | grep -E "pytest" | grep -v grep | wc -l   # must print 0
```

If that doesn't print 0, escalate (a process is hung in uninterruptible I/O — investigate before continuing).

### For first-pass change verification

Run *only the tests directly touched by the change*, serially, with `-x` (stop at first failure) and a short per-test timeout:

```bash
.venv/bin/pytest -x --timeout=30 -v tests/path/to/specific_test.py
```

Fast, fail-loud, no buffering questions.

### For broader verification

Run unit-only with a per-test timeout and direct file redirect (no pipe), under an outer wall-clock cap:

```bash
timeout 480 .venv/bin/pytest --timeout=120 --timeout-method=thread -q \
  -m "not (inference or llm or img_gen or extract or search) and not pipelex_api" \
  tests/unit/ > /tmp/pytest_unit.log 2>&1
echo "exit=$?"   # 0=pass, 1=fail, 124=outer timeout fired
```

Or background it with `run_in_background: true` and `wait $PID` so the harness notifies on exit. The outer `timeout` is what catches a fixture-teardown hang or an xdist worker-replace loop that `--timeout` cannot.

### When the run hangs anyway

- **Read the live log** (`tail -50 /tmp/pytest_unit.log`) — direct-redirect means progress is visible as it happens. With `-v` you see the last test name that started.
- **Check active processes** — `ps -ef | grep pytest` shows which xdist worker is alive and how long it's been running.
- **Don't poll.** If you've wrapped in `timeout`, the outer cap will kill it; let the harness notification fire.

### When the run completes with FAILED

Grep for the **error class name**, not the formatted message:

```bash
grep -B 2 -A 10 "YourSpecificErrorClass" /tmp/pytest_unit.log
```

The formatted message can show up anywhere, including inside log lines that aren't pytest `FAILED` markers. The error class name is greppable, stable, and points straight at the cause.

If the failures look infrastructure-related (worker crashes, "node down", "replacing crashed worker"), **re-run the failing slice serially** with no xdist:

```bash
.venv/bin/pytest --timeout=60 --tb=short -q tests/path/that/failed/
```

If serial passes, the original failure was xdist contention — not your code. If serial fails, it's a real bug, and you now have a clean traceback to read (no xdist obscuring it).

---

## Iteration template (the whole thing in one go)

```bash
# 0. Clean state
pkill -9 -f "pytest" 2>/dev/null
sleep 1

# 1. Fast verification of the change
.venv/bin/pytest -x --timeout=30 -v tests/unit/path/touched/ 2>&1 | tail -20

# 2. Broad unit verification, direct redirect, outer wall-clock cap
timeout 480 .venv/bin/pytest --timeout=120 --timeout-method=thread -q \
  -m "not (inference or llm or img_gen or extract or search) and not pipelex_api" \
  tests/unit/ > /tmp/pytest_unit.log 2>&1
echo "exit=$?"  # 0=pass, 1=fail, 124=outer timeout

# 3. If any failures, grep by error class name
grep -B 2 -A 10 "YourErrorClass" /tmp/pytest_unit.log
```

If anything exceeds the outer `timeout`, it gets killed rather than hanging the session.

---

## Why each tool choice matters

| Choice | Why |
|---|---|
| Direct file redirect (`> file 2>&1`) | No pipe buffering; progress is visible live. |
| `-q` only for final accepted runs, NOT debug runs | `-q` buffers everything until session-end. Use `-v` for debug. |
| `--timeout=N --timeout-method=thread` | Per-test cap. `thread` method works in async contexts where `signal` doesn't. |
| Outer shell `timeout N` | Catches **fixture-teardown hangs** and **xdist worker-replace loops** that `--timeout` cannot. |
| `-x` for first-pass debug | Stops at first real failure; gives you a clean traceback fast. |
| Serial (no `-n auto`) for verifying flaky tests | xdist worker crashes mask real failures and add runtime via replacement cycles. Serial is honest. |
| Grep for error **class name**, not message | Messages get embedded in non-pytest log lines; class names don't. |

`make agent-test-debug` (alias `make atd`) packages this loop: clean state, outer wall-clock cap, direct file redirect, and `-v` so each test name lands in the log as it runs.

---

## When to stop iterating and surface to the user

Bail out and ask for help (don't burn more time) when:

- After clean-state + outer-timeout run, the suite still doesn't terminate within 2× its expected duration.
- After serial re-run of the failing slice, you still can't tell whether the failure is your code or a pre-existing flake.
- You've made a code change to fix a test failure and the same test now fails differently — pause and read the new failure carefully before changing more code.

In all cases, write up what you know in 3–4 sentences and surface to the user. Better than spending another 20 minutes on dead ends.
