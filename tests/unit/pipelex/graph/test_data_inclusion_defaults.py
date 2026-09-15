"""Regression guard for the shipped graph data-inclusion defaults.

The text and HTML renderings of every traced stuff are built through Rich on the execution path, at a cost that
grows with text volume times nesting depth; on a Temporal worker that cost trips the deadlock detector. They are
therefore opt-in, and this test pins the packaged defaults so a flip back is a deliberate change, not a drift.
"""

from pathlib import Path

import tomli

PIPELEX_REPO_ROOT = Path(__file__).resolve().parents[4]
PACKAGE_DEFAULT_TOML = PIPELEX_REPO_ROOT / "pipelex" / "pipelex.toml"


class TestShippedDataInclusionDefaults:
    def test_renderings_are_opt_in_and_json_stays_on(self) -> None:
        with PACKAGE_DEFAULT_TOML.open("rb") as toml_file:
            shipped = tomli.load(toml_file)
        data_inclusion = shipped["interpreter"]["pipeline_execution"]["graph"]["data_inclusion"]
        assert data_inclusion["stuff_text_content"] is False
        assert data_inclusion["stuff_html_content"] is False
        assert data_inclusion["stuff_json_content"] is True
