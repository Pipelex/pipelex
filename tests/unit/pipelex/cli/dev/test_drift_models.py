"""Unit tests for the drift manifest and ack models: parsing, validation, atomic ack I/O."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.cli.dev_cli.commands.drift.exceptions import DriftAckError, DriftManifestError
from pipelex.cli.dev_cli.commands.drift.models import (
    DriftAck,
    ack_file_path,
    load_all_acks,
    load_manifest,
    save_ack,
)

if TYPE_CHECKING:
    from pathlib import Path

VALID_MANIFEST = """
version = 1

[contracts.config-docs]
description = "Config docs must track the config model."
triggers = ["pipelex/system/configuration/**/*.py", "pipelex/pipelex.toml"]
review = ["docs/configuration/**/*.md"]
verify_commands = ["make tb"]

[contracts.cli-docs]
description = "CLI docs must track the CLI surface."
triggers = ["pipelex/cli/**/*.py"]
exclude = ["pipelex/cli/dev_cli/**"]
review = ["docs/tools/cli/", "pipelex/cli/agent_cli/CLAUDE.md"]
"""


def _write_manifest(repo_root: Path, *, content: str) -> None:
    (repo_root / "drift.toml").write_text(content)


def _sample_ack(contract_id: str = "config-docs") -> DriftAck:
    return DriftAck(
        contract=contract_id,
        digest="sha256:4e03f2a1",
        reviewed_by="louis",
        reviewed_at="2026-07-03T14:12:09Z",
        rationale="Initial review.",
        trigger_files={"pipelex/pipelex.toml": "blob:99ffee"},
    )


class TestDriftModels:
    def test_load_manifest_happy_path(self, tmp_path: Path) -> None:
        _write_manifest(tmp_path, content=VALID_MANIFEST)
        manifest = load_manifest(tmp_path)
        assert manifest.version == 1
        assert set(manifest.contracts) == {"config-docs", "cli-docs"}
        config_docs = manifest.contracts["config-docs"]
        assert config_docs.description == "Config docs must track the config model."
        assert config_docs.exclude == []
        assert config_docs.verify_commands == ["make tb"]
        cli_docs = manifest.contracts["cli-docs"]
        assert cli_docs.exclude == ["pipelex/cli/dev_cli/**"]
        assert cli_docs.verify_commands == []

    def test_load_manifest_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(DriftManifestError, match=r"drift\.toml"):
            load_manifest(tmp_path)

    def test_load_manifest_malformed_toml(self, tmp_path: Path) -> None:
        _write_manifest(tmp_path, content="version = [unclosed")
        with pytest.raises(DriftManifestError):
            load_manifest(tmp_path)

    def test_load_manifest_invalid_contract_id_charset(self, tmp_path: Path) -> None:
        """Contract ids become filenames and TOML keys — restrict them to [a-z0-9-]+."""
        _write_manifest(
            tmp_path,
            content="""
version = 1

[contracts."Bad_ID"]
description = "Nope."
triggers = ["a.py"]
review = ["docs/a.md"]
""",
        )
        with pytest.raises(DriftManifestError, match="Bad_ID"):
            load_manifest(tmp_path)

    def test_load_manifest_unknown_field_rejected(self, tmp_path: Path) -> None:
        _write_manifest(
            tmp_path,
            content="""
version = 1

[contracts.config-docs]
description = "Config docs."
triggers = ["a.py"]
review = ["docs/a.md"]
unknown_field = "typo"
""",
        )
        with pytest.raises(DriftManifestError, match="unknown_field"):
            load_manifest(tmp_path)

    def test_load_manifest_missing_required_field(self, tmp_path: Path) -> None:
        _write_manifest(
            tmp_path,
            content="""
version = 1

[contracts.config-docs]
triggers = ["a.py"]
review = ["docs/a.md"]
""",
        )
        with pytest.raises(DriftManifestError, match="description"):
            load_manifest(tmp_path)

    def test_load_manifest_empty_triggers_rejected(self, tmp_path: Path) -> None:
        _write_manifest(
            tmp_path,
            content="""
version = 1

[contracts.config-docs]
description = "Config docs."
triggers = []
review = ["docs/a.md"]
""",
        )
        with pytest.raises(DriftManifestError):
            load_manifest(tmp_path)

    def test_ack_round_trip(self, tmp_path: Path) -> None:
        ack = _sample_ack()
        save_ack(ack, repo_root=tmp_path)
        ack_path = ack_file_path(tmp_path, contract_id="config-docs")
        assert ack_path == tmp_path / ".drift" / "acks" / "config-docs.toml"
        assert ack_path.is_file()
        loaded = load_all_acks(tmp_path)
        assert loaded == {"config-docs": ack}

    def test_save_ack_leaves_no_temp_file(self, tmp_path: Path) -> None:
        """The atomic write must not leave a temp file behind in .drift/acks/."""
        save_ack(_sample_ack(), repo_root=tmp_path)
        leftovers = [path.name for path in (tmp_path / ".drift" / "acks").iterdir() if path.suffix != ".toml"]
        assert leftovers == []

    def test_save_ack_overwrites_existing(self, tmp_path: Path) -> None:
        save_ack(_sample_ack(), repo_root=tmp_path)
        updated = _sample_ack().model_copy(update={"rationale": "Second review.", "digest": "sha256:deadbeef"})
        save_ack(updated, repo_root=tmp_path)
        loaded = load_all_acks(tmp_path)
        assert loaded["config-docs"].rationale == "Second review."
        assert loaded["config-docs"].digest == "sha256:deadbeef"

    def test_load_all_acks_empty_when_no_dir(self, tmp_path: Path) -> None:
        assert load_all_acks(tmp_path) == {}

    def test_load_all_acks_corrupt_ack_is_hard_error(self, tmp_path: Path) -> None:
        acks_dir = tmp_path / ".drift" / "acks"
        acks_dir.mkdir(parents=True)
        (acks_dir / "config-docs.toml").write_text("contract = [broken")
        with pytest.raises(DriftAckError, match="config-docs"):
            load_all_acks(tmp_path)
