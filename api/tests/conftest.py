import os

# Set a placeholder for COMPLETION_CALLBACK_SECRET so tests that exercise /start
# never depend on the developer's shell env. CAVEAT: `make` test targets export
# every `.env` key NAME into the child env (including commented-out ones) as
# EMPTY strings, and `setdefault` cannot replace an existing empty value — so
# tests that verify the callback signature must pin the secret themselves via
# `mocker.patch.dict(os.environ, ...)` (see tests/unit/test_protocol_conformance.py).
os.environ.setdefault("COMPLETION_CALLBACK_SECRET", "test-placeholder-completion-callback-secret")

pytest_plugins = [
    "pipelex.test_extras.shared_pytest_plugins",
]
