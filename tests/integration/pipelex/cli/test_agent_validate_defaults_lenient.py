from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pipelex.cli.agent_cli.commands.validate._validate_core import validate_bundle_core  # noqa: PLC2701

if TYPE_CHECKING:
    from collections.abc import Iterator

_BUNDLE_WITH_SIGNATURE = """
domain = "agent_sigcli"

[concept]
AgentDoc = "A document used in agent CLI signature tests."
AgentSummary = "A summary used in agent CLI signature tests."

[pipe.agent_seq]
type = "PipeSequence"
description = "Sequence with a signature step."
inputs = { doc = "AgentDoc" }
output = "AgentSummary"
steps = [ { pipe = "agent_sig", result = "summary" } ]

[pipe.agent_sig]
type = "PipeSignature"
description = "Signature placeholder."
inputs = { doc = "AgentDoc" }
output = "AgentSummary"
"""


@pytest.fixture
def agent_signature_bundle_dir() -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir)
        (path / "bundle.mthds").write_text(_BUNDLE_WITH_SIGNATURE)
        yield path


class TestAgentValidateDefaultsLenient:
    def test_agent_validate_defaults_to_lenient(self, agent_signature_bundle_dir: Path) -> None:
        # The agent CLI's validate_bundle_core defaults to lenient — succeeds even when the
        # bundle contains a signature reachable from another pipe.
        result = asyncio.run(
            validate_bundle_core(
                bundle_path=agent_signature_bundle_dir / "bundle.mthds",
                library_dirs=[agent_signature_bundle_dir],
            )
        )
        assert result["success"] is True
        pipe_codes = {entry["pipe_code"] for entry in result["validated_pipes"]}
        assert "agent_sigcli.agent_sig" in pipe_codes
        assert "agent_sigcli.agent_seq" in pipe_codes
