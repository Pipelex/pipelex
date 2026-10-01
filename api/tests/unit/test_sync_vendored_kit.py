"""`scripts/sync_vendored_kit.py` carries this image's backend switches and never invents them.

The vendored `backends.toml` is the only record of which backends the image enables, so the sync
must keep every switch across a re-sync, disable a backend the kit adds, and stop when that record
is missing or unreadable rather than render every backend off. The script is a standalone entry
point, not a package module, so it is loaded from its path.
"""

import importlib.util
import shutil
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "sync_vendored_kit.py"
_VENDORED_CONFIG_DIR = _REPO_ROOT / ".pipelex"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("sync_vendored_kit", _SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sync_vendored_kit = _load_script()

KIT_BACKENDS_TOML = """\
[kept_on]
enabled = true
api_key = "${KEPT_ON_API_KEY}"

[kept_off] # a comment on the header
enabled = true # the kit enables it, this image does not

[new_in_kit]
enabled = true
"""


@pytest.fixture
def vendored_copy(tmp_path: Path) -> Path:
    config_dir = tmp_path / ".pipelex"
    shutil.copytree(_VENDORED_CONFIG_DIR, config_dir)
    return config_dir


class TestSyncVendoredKit:
    def test_render_carries_each_switch_and_disables_a_new_backend(self) -> None:
        rendered: str = sync_vendored_kit.render_backends_toml(
            kit_text=KIT_BACKENDS_TOML,
            enabled_switches={"kept_on": True, "kept_off": False},
        )
        assert rendered.startswith("# pipelex-api:")
        assert rendered.endswith(
            """\
[kept_on]
enabled = true
api_key = "${KEPT_ON_API_KEY}"

[kept_off] # a comment on the header
enabled = false # the kit enables it, this image does not

[new_in_kit]
enabled = false
"""
        )

    def test_render_refuses_a_kit_table_without_a_switch(self) -> None:
        with pytest.raises(sync_vendored_kit.KitShapeError, match="no_switch"):
            sync_vendored_kit.render_backends_toml(kit_text="[no_switch]\napi_key = 'x'\n", enabled_switches={})

    def test_committed_tree_is_in_sync(self) -> None:
        plan = sync_vendored_kit.plan_sync(_VENDORED_CONFIG_DIR)
        assert plan.drifts == []
        assert plan.is_clean

    def test_committed_tree_enables_the_gateway(self) -> None:
        switches: dict[str, bool] = sync_vendored_kit.read_enabled_switches(_VENDORED_CONFIG_DIR / "inference" / "backends.toml")
        assert switches["pipelex_gateway"] is True
        assert switches["internal"] is True

    def test_a_table_without_a_switch_is_read_as_on(self, tmp_path: Path) -> None:
        backends_toml = tmp_path / "backends.toml"
        backends_toml.write_text("[acme]\napi_key = 'x'\n\n[other]\nenabled = false\n", encoding="utf-8")
        assert sync_vendored_kit.read_enabled_switches(backends_toml) == {"acme": True, "other": False}

    def test_a_backend_new_in_the_kit_arrives_disabled(self, vendored_copy: Path) -> None:
        inference_dir = vendored_copy / "inference"
        backends_toml = inference_dir / "backends.toml"
        backends_toml.write_text(_without_table(backends_toml.read_text(encoding="utf-8"), "minimax"), encoding="utf-8")
        (inference_dir / "backends" / "minimax.toml").unlink()
        plan = sync_vendored_kit.plan_sync(vendored_copy)
        rendered = next(drift.content for drift in plan.drifts if drift.path == backends_toml)
        assert '[minimax]\ndisplay_name = "MiniMax"\nenabled = false\n' in rendered.decode("utf-8")

    @pytest.mark.parametrize(
        ("backends_toml_text", "reason"),
        [
            (None, "is missing"),
            ("[pipelex_gateway\nenabled = true\n", "is not valid TOML"),
            ("", "holds no backend table"),
            ("[pipelex_gateway]\nenabled = 'yes'\n", "is not a boolean"),
            ("[pipelex_gateway]\nenabled = true\n", "has no table for"),
        ],
    )
    def test_sync_stops_when_the_switch_record_is_unusable(self, vendored_copy: Path, backends_toml_text: str | None, reason: str) -> None:
        backends_toml = vendored_copy / "inference" / "backends.toml"
        backends_toml.unlink()
        if backends_toml_text is not None:
            backends_toml.write_text(backends_toml_text, encoding="utf-8")
        with pytest.raises(sync_vendored_kit.SwitchSourceError, match=reason):
            sync_vendored_kit.plan_sync(vendored_copy)

    def test_sync_stops_when_a_vendored_backend_lost_its_table(self, vendored_copy: Path) -> None:
        backends_toml = vendored_copy / "inference" / "backends.toml"
        backends_toml.write_text(_without_table(backends_toml.read_text(encoding="utf-8"), "internal"), encoding="utf-8")
        with pytest.raises(sync_vendored_kit.SwitchSourceError, match=r"has no table for internal,"):
            sync_vendored_kit.plan_sync(vendored_copy)


def _without_table(toml_text: str, table_name: str) -> str:
    """Cut one table, from its header to the next one, out of a TOML document."""
    kept_lines: list[str] = []
    skipping = False
    for line in toml_text.splitlines(keepends=True):
        if line.startswith("["):
            skipping = line.startswith(f"[{table_name}]")
        if not skipping:
            kept_lines.append(line)
    assert len(kept_lines) < len(toml_text.splitlines())
    return "".join(kept_lines)
