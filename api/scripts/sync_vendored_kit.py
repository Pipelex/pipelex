"""Keep the vendored `.pipelex/inference/` tree in step with the installed pipelex's kit.

The image serves the models its `/root/.pipelex/inference/` tree declares, and that tree is this
repository's `.pipelex/inference/`, copied in by the Dockerfile. Once a config directory exists,
pipelex never reads the kit shipped inside its own wheel, so a pin bump changes nothing the image
serves until these files move with it. `pipelex update` refreshes only the numbered deck files; this
script owns the whole tree, under four rules:

- `inference/backends/` mirrors the kit's directory: every kit file byte for byte, and no other
  file. What `pipelex migrate` leaves beside the files it rewrites is never counted or deleted.
- `inference/routing_profiles.toml` is the kit's, byte for byte.
- `inference/backends.toml` is the kit's except for each backend's `enabled` switch, which is this
  image's own choice: the switch is carried over from the current file, read the way pipelex reads
  it (a table with no `enabled` key is on), and a backend the kit adds arrives disabled. The current
  file is the only record of those choices, so when it is missing or unreadable, or lacks the table
  of a backend whose file is already vendored, both modes stop rather than invent a switch.
- `inference/deck/`: the numbered files are the kit's, with the `.kit_manifest.json` pipelex keeps
  for them. The `x_custom_*` overrides are this repository's and are never touched.

Usage:
    python scripts/sync_vendored_kit.py .pipelex
    python scripts/sync_vendored_kit.py --check .pipelex

`--check` exits non-zero when the vendored tree has drifted from the kit — wired into CI via
`make kit-check`. Both modes also fail when the kit ships an `inference/` entry none of the rules
above covers, since only a person can decide what this image does with it.
"""

import argparse
import re
import sys
import tomllib
from pathlib import Path
from typing import cast

from pipelex.cogt.models.deck_manifest import (
    compute_kit_manifest,
    kit_deck_dir,
    list_managed_installed_files,
    list_managed_kit_files,
    read_manifest,
    write_manifest,
)
from pipelex.kit.paths import get_kit_configs_dir
from pipelex.migration.backup import BACKUP_INFIX, RESCUE_INFIX
from pydantic import BaseModel, ConfigDict, Field

_BACKENDS_DIR = "backends"
_DECK_DIR = "deck"
_BACKENDS_TOML = "backends.toml"
_ROUTING_PROFILES_TOML = "routing_profiles.toml"
_HANDLED_KIT_ENTRIES = frozenset({_BACKENDS_DIR, _DECK_DIR, _BACKENDS_TOML, _ROUTING_PROFILES_TOML})

# `pipelex migrate` can leave three kinds of file beside each file it rewrites: `<file>.bak.<stamp>`
# backups, `<file>.rescue.<stamp>` copies whose removal pipelex leaves to the user, and the
# `.<file>.pipelex-fix-<label>.<random>.tmp` staging files a crash can strand. The mirror neither
# counts nor deletes any of them, nor a hand-made `*.bak`, nor a Finder `.DS_Store`.
_MIGRATION_LEFTOVER_MARKERS = (BACKUP_INFIX, RESCUE_INFIX, ".pipelex-fix-")
_IGNORED_NAMES = frozenset({".DS_Store"})

_TABLE_HEADER = re.compile(r"^\[([^\[\]]+)\]")
_ENABLED_SWITCH = re.compile(r"^(enabled\s*=\s*)(true|false)\b")

_BACKENDS_TOML_PREAMBLE = """\
# pipelex-api: this is the kit's `inference/backends.toml` from the pinned pipelex, re-synced by
# `make kit-sync`. Only the `enabled` switches are this image's own choice, and the sync keeps them;
# any other edit is reported as drift by `make kit-check`.
#
"""


class KitShapeError(Exception):
    """The kit no longer has the shape these rules were written for."""


class SwitchSourceError(Exception):
    """The vendored backends.toml cannot say which backends this image enables."""


class Drift(BaseModel):
    """One vendored file that differs from what the kit says it should be."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: Path
    reason: str
    content: bytes | None = Field(description="What the file should hold, or None when it should not exist")


class SyncPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    drifts: list[Drift] = Field(default_factory=list[Drift])
    deck_dir: Path | None = None
    manifest_is_stale: bool = False
    unhandled_kit_entries: list[str] = Field(default_factory=list)
    dropped_backend_switches: dict[str, bool] = Field(default_factory=dict)

    @property
    def is_clean(self) -> bool:
        return not self.drifts and not self.manifest_is_stale and not self.unhandled_kit_entries


def _is_mirrored_name(name: str) -> bool:
    if name in _IGNORED_NAMES or name.endswith(".bak"):
        return False
    return not any(marker in name for marker in _MIGRATION_LEFTOVER_MARKERS)


def _compare_file(*, target: Path, expected: bytes | None, plan: SyncPlan) -> None:
    if expected is None:
        if target.exists():
            plan.drifts.append(Drift(path=target, reason="absent from the kit", content=None))
        return
    if not target.is_file():
        plan.drifts.append(Drift(path=target, reason="added in the kit", content=expected))
    elif target.read_bytes() != expected:
        plan.drifts.append(Drift(path=target, reason="differs from the kit", content=expected))


def _plan_backends_dir(*, kit_dir: Path, vendored_dir: Path, plan: SyncPlan) -> None:
    kit_files = {entry.name: entry for entry in kit_dir.iterdir() if entry.is_file() and _is_mirrored_name(entry.name)}
    vendored_names: set[str] = set()
    if vendored_dir.is_dir():
        vendored_names = {entry.name for entry in vendored_dir.iterdir() if entry.is_file() and _is_mirrored_name(entry.name)}
    for name in sorted(set(kit_files) | vendored_names):
        kit_file = kit_files.get(name)
        _compare_file(target=vendored_dir / name, expected=kit_file.read_bytes() if kit_file is not None else None, plan=plan)


def read_enabled_switches(backends_toml: Path) -> dict[str, bool]:
    """Read each backend's `enabled` switch from the vendored backends.toml, as pipelex reads it.

    Args:
        backends_toml: The vendored `inference/backends.toml`, the only record of this image's switches.

    Returns:
        The switch per backend table. A table with no `enabled` key is on, which is pipelex's default.

    Raises:
        SwitchSourceError: The file is missing, is not valid TOML, holds no backend table, or sets an
            `enabled` that is not a boolean. Rendering from it would invent this image's switches.
    """
    if not backends_toml.is_file():
        msg = f"{backends_toml} is missing, and it is the only record of which backends this image enables. Restore it from git and run again."
        raise SwitchSourceError(msg)
    try:
        document = tomllib.loads(backends_toml.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        msg = f"{backends_toml} is not valid TOML ({exc}), so this image's `enabled` switches cannot be read from it."
        raise SwitchSourceError(msg) from exc
    switches: dict[str, bool] = {}
    for backend_name, table in document.items():
        if not isinstance(table, dict):
            continue
        switch = cast("dict[str, object]", table).get("enabled", True)
        if not isinstance(switch, bool):
            msg = (
                f"{backends_toml} sets `enabled` on [{backend_name}] to {switch!r}, which is not a boolean, so this image's switch for it is unknown."
            )
            raise SwitchSourceError(msg)
        switches[backend_name] = switch
    if not switches:
        msg = f"{backends_toml} holds no backend table, so which backends this image enables is unknown. Restore it from git and run again."
        raise SwitchSourceError(msg)
    return switches


def _table_names(toml_text: str) -> set[str]:
    return {name for name, value in tomllib.loads(toml_text).items() if isinstance(value, dict)}


def render_backends_toml(*, kit_text: str, enabled_switches: dict[str, bool]) -> str:
    """Render the kit's backends.toml with this image's `enabled` switches in place of the kit's.

    Args:
        kit_text: The kit's `inference/backends.toml`.
        enabled_switches: This image's switch per backend. A backend missing from it is disabled.

    Returns:
        The file the vendored tree should hold.

    Raises:
        KitShapeError: A kit table carries no `enabled` line, so a switch has nowhere to go.
    """
    rendered_lines = [_BACKENDS_TOML_PREAMBLE]
    current_table: str | None = None
    switched_tables: set[str] = set()
    for line in kit_text.splitlines(keepends=True):
        rendered_line = line
        header_match = _TABLE_HEADER.match(line)
        if header_match is not None:
            current_table = header_match.group(1).strip().strip('"')
        elif current_table is not None:
            switch_match = _ENABLED_SWITCH.match(line)
            if switch_match is not None:
                switch_value = "true" if enabled_switches.get(current_table, False) else "false"
                rendered_line = f"{switch_match.group(1)}{switch_value}{line[switch_match.end() :]}"
                switched_tables.add(current_table)
        rendered_lines.append(rendered_line)
    unswitched_tables = sorted(_table_names(kit_text) - switched_tables)
    if unswitched_tables:
        msg = f"The kit's backends.toml has tables with no `enabled` line, so this image's switch cannot be carried: {', '.join(unswitched_tables)}"
        raise KitShapeError(msg)
    return "".join(rendered_lines)


def _plan_backends_toml(*, kit_file: Path, vendored_file: Path, vendored_backends_dir: Path, plan: SyncPlan) -> None:
    kit_text = kit_file.read_text(encoding="utf-8")
    enabled_switches = read_enabled_switches(vendored_file)
    kit_backends = _table_names(kit_text)
    # A kit backend with no table here is new only if its backend file is new too. One whose file is
    # already vendored had a table, so the switch record was cut short and its switch is unknown.
    unrecorded_backends = sorted(name for name in kit_backends - set(enabled_switches) if (vendored_backends_dir / f"{name}.toml").is_file())
    if unrecorded_backends:
        msg = (
            f"{vendored_file} has no table for {', '.join(unrecorded_backends)}, whose backend files are already vendored, "
            "so this image's switch for them is unknown. Restore the file from git and run again."
        )
        raise SwitchSourceError(msg)
    plan.dropped_backend_switches = {name: value for name, value in enabled_switches.items() if name not in kit_backends}
    rendered = render_backends_toml(kit_text=kit_text, enabled_switches=enabled_switches)
    _compare_file(target=vendored_file, expected=rendered.encode("utf-8"), plan=plan)


def _plan_deck(*, vendored_deck_dir: Path, plan: SyncPlan) -> None:
    kit_dir = kit_deck_dir()
    kit_names = set(list_managed_kit_files())
    vendored_names = set(list_managed_installed_files(vendored_deck_dir))
    for name in sorted(kit_names | vendored_names):
        expected = (kit_dir / name).read_bytes() if name in kit_names else None
        _compare_file(target=vendored_deck_dir / name, expected=expected, plan=plan)
    plan.deck_dir = vendored_deck_dir
    plan.manifest_is_stale = read_manifest(vendored_deck_dir) != compute_kit_manifest()


def plan_sync(config_dir: Path) -> SyncPlan:
    """Compare a vendored config dir's `inference/` tree against the installed pipelex's kit."""
    kit_inference_dir = Path(str(get_kit_configs_dir())) / "inference"
    vendored_inference_dir = config_dir / "inference"
    plan = SyncPlan()
    plan.unhandled_kit_entries = sorted(
        entry.name for entry in kit_inference_dir.iterdir() if entry.name not in _HANDLED_KIT_ENTRIES and _is_mirrored_name(entry.name)
    )
    _plan_backends_dir(kit_dir=kit_inference_dir / _BACKENDS_DIR, vendored_dir=vendored_inference_dir / _BACKENDS_DIR, plan=plan)
    routing_profiles = (kit_inference_dir / _ROUTING_PROFILES_TOML).read_bytes()
    _compare_file(target=vendored_inference_dir / _ROUTING_PROFILES_TOML, expected=routing_profiles, plan=plan)
    _plan_backends_toml(
        kit_file=kit_inference_dir / _BACKENDS_TOML,
        vendored_file=vendored_inference_dir / _BACKENDS_TOML,
        vendored_backends_dir=vendored_inference_dir / _BACKENDS_DIR,
        plan=plan,
    )
    _plan_deck(vendored_deck_dir=vendored_inference_dir / _DECK_DIR, plan=plan)
    return plan


def apply_plan(plan: SyncPlan) -> None:
    for drift in plan.drifts:
        if drift.content is None:
            drift.path.unlink()
        else:
            drift.path.parent.mkdir(parents=True, exist_ok=True)
            drift.path.write_bytes(drift.content)
    if plan.manifest_is_stale and plan.deck_dir is not None:
        write_manifest(compute_kit_manifest(), deck_dir=plan.deck_dir)


def _describe(plan: SyncPlan) -> list[str]:
    lines = [f"  {drift.path}: {drift.reason}" for drift in plan.drifts]
    if plan.manifest_is_stale and plan.deck_dir is not None:
        lines.append(f"  {plan.deck_dir / '.kit_manifest.json'}: does not record the installed kit")
    return lines


def _describe_unhandled(plan: SyncPlan) -> str:
    entries = ", ".join(f"inference/{name}" for name in plan.unhandled_kit_entries)
    return f"The kit ships {entries}, which no rule in scripts/sync_vendored_kit.py covers. Decide what this image does with it and add the rule."


def main() -> int:
    parser = argparse.ArgumentParser(description="Re-sync (or drift-check) the vendored inference tree against the installed pipelex kit.")
    parser.add_argument("config_dir", type=Path, help="The vendored pipelex config dir, normally .pipelex")
    parser.add_argument("--check", action="store_true", help="Report drift and exit 1 instead of re-syncing")
    args = parser.parse_args()

    config_dir: Path = args.config_dir
    kit_version = compute_kit_manifest().kit_version
    mode = "drift check" if args.check else "sync"
    try:
        plan = plan_sync(config_dir)
    except (KitShapeError, SwitchSourceError) as exc:
        print(f"Vendored kit {mode} FAILED against pipelex {kit_version}: {exc}")
        return 1

    if args.check:
        if plan.is_clean:
            print(f"Vendored inference tree matches the pipelex {kit_version} kit: {config_dir / 'inference'}")
            return 0
        print(f"Vendored kit drift check FAILED against pipelex {kit_version}:")
        for line in _describe(plan):
            print(line)
        if plan.unhandled_kit_entries:
            print(_describe_unhandled(plan))
        if plan.drifts or plan.manifest_is_stale:
            print("Run `make kit-sync` and commit the result.")
        return 1

    for backend_name, enabled in sorted(plan.dropped_backend_switches.items()):
        state = "enabled" if enabled else "disabled"
        print(f"Note: backend '{backend_name}' is no longer in the kit, so its switch ({state}) is dropped.")
    if plan.drifts or plan.manifest_is_stale:
        apply_plan(plan)
        print(f"Re-synced the vendored inference tree to the pipelex {kit_version} kit:")
        for line in _describe(plan):
            print(line)
    else:
        print(f"Vendored inference tree already matches the pipelex {kit_version} kit.")
    if plan.unhandled_kit_entries:
        print(_describe_unhandled(plan))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
