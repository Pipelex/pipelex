"""The plugin tutorial writes `targets_api` as a literal, as an out-of-tree plugin must, so the literal follows the runtime's version.

A tutorial whose example declares an older version teaches a plugin that discovery refuses on its first boot.
"""

import re
from pathlib import Path

from pipelex.plugins.contract import PLUGIN_API_VERSION

_TESTS_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "tests")
_TUTORIAL_PATH = _TESTS_ROOT.parent / "docs" / "under-the-hood" / "writing-an-inference-plugin.md"
_LITERAL_TARGETS_API = re.compile(r"^\s*targets_api = (\d+)\s*$", re.MULTILINE)


class TestPluginApiVersionInDocs:
    def test_the_tutorial_plugin_targets_the_current_plugin_api_version(self) -> None:
        declared_versions = [int(version) for version in _LITERAL_TARGETS_API.findall(_TUTORIAL_PATH.read_text(encoding="utf-8"))]
        assert declared_versions, f"{_TUTORIAL_PATH.name} no longer declares `targets_api` as a literal: update this test"
        assert declared_versions == [PLUGIN_API_VERSION] * len(declared_versions)
