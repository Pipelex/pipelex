"""Fixtures for human-CLI E2E tests.

Re-exports the hermetic-HOME subprocess harness of the agent-CLI E2E suite so human-CLI
subprocess tests (e.g. ``pipelex fix bundle``) run against the same isolated config tree,
and builds the empty home the hosted-setup subprocess tests start from.
"""

from __future__ import annotations

import stat
from typing import TYPE_CHECKING

import pytest

from tests.e2e.agent_cli.conftest import (  # ruff: ignore[unused-import] - fixtures re-exported for this directory
    hermetic_home,
    offline_subprocess_env,
)
from tests.helpers.login_browser import TEST_KEY

if TYPE_CHECKING:
    from pathlib import Path

# Stands in for the `code` and `cursor` CLIs, reporting the Pipelex extension as installed, so init's offer to
# install it neither prompts nor touches a real editor.
_IDE_SHADOW_SCRIPT = '#!/bin/sh\nif [ "$1" = "--list-extensions" ]; then\n    echo "Pipelex.pipelex"\nfi\nexit 0\n'


@pytest.fixture
def fresh_home_env(tmp_path: Path) -> dict[str, str]:
    """An empty `HOME`, no `PIPELEX_HOME`, a Pipelex API key, and an unreachable hosted API should anything call it."""
    home = tmp_path / "home"
    home.mkdir()
    shadow_dir = tmp_path / "ide_shadow"
    shadow_dir.mkdir()
    for command in ("code", "cursor"):
        script = shadow_dir / command
        script.write_text(_IDE_SHADOW_SCRIPT, encoding="utf-8")
        script.chmod(stat.S_IRWXU)
    return {
        "HOME": str(home),
        "PATH": f"{shadow_dir}:/usr/bin:/bin",
        "RUN_MODE": "ci_test",
        "PIPELEX_API_KEY": TEST_KEY,
        "PIPELEX_BASE_URL": "http://127.0.0.1:9",
        "PIPELEX_APP_URL": "http://127.0.0.1:9",
    }
