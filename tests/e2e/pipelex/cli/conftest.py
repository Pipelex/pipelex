"""Fixtures for human-CLI E2E tests.

Re-exports the hermetic-HOME subprocess harness of the agent-CLI E2E suite so human-CLI
subprocess tests (e.g. ``pipelex fix bundle``) run against the same isolated config tree.
"""

from tests.e2e.agent_cli.conftest import (  # noqa: F401 - fixtures re-exported for this directory
    hermetic_home,
    offline_subprocess_env,
)
