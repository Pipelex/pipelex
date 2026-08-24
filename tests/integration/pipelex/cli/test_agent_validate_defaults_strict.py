from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pipelex.cli.agent_cli.commands.validate._validate_core import validate_bundle_core

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


class TestAgentValidateDefaultsStrict:
    def test_agent_validate_defaults_to_strict(self, agent_signature_bundle_dir: Path) -> None:
        # Signatures are never an error (D-B): the strict agent CLI core does not raise on a reached
        # signature — it returns a valid-but-not-runnable envelope. The bundle command's exit-code gate
        # (not this core) turns is_runnable=False into a non-zero exit unless --allow-signatures.
        result = asyncio.run(
            validate_bundle_core(
                bundle_path=agent_signature_bundle_dir / "bundle.mthds",
                library_dirs=[agent_signature_bundle_dir],
            )
        )
        assert result["is_valid"] is True
        assert result["pending_signatures"] == ["agent_sigcli.agent_sig"]
        assert result["is_runnable"] is False
        # Strict mode excludes the signature pipe from the sweep — it is absent from validated_pipes.
        pipe_refs = {entry["pipe_ref"] for entry in result["validated_pipes"]}
        assert "agent_sigcli.agent_sig" not in pipe_refs

    def test_agent_validate_allow_signatures_succeeds(self, agent_signature_bundle_dir: Path) -> None:
        # With allow_signatures=True the same bundle validates — signatures dry-run as mocks.
        result = asyncio.run(
            validate_bundle_core(
                bundle_path=agent_signature_bundle_dir / "bundle.mthds",
                library_dirs=[agent_signature_bundle_dir],
                allow_signatures=True,
            )
        )
        assert result["success"] is True
        pipe_refs = {entry["pipe_ref"] for entry in result["validated_pipes"]}
        assert "agent_sigcli.agent_sig" in pipe_refs
        assert "agent_sigcli.agent_seq" in pipe_refs
        # A lenient success that still carries an unimplemented signature is NOT runnable, and the
        # envelope says so explicitly via is_runnable (derived from the pending_signatures set).
        assert result["pending_signatures"] == ["agent_sigcli.agent_sig"]
        assert result["is_runnable"] is False
