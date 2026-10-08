"""The former-release cleanup over random layouts of a home and a project, held to what it promises every boot.

Each layout is a home `routing_profiles.toml`, and maybe a home override, a project base and a project override, each
drawn from a small set of profile names, `default` backends and route shapes, with a former release's Gateway among
them. The cleanup runs over the home and the project together, then each boot — the one outside the project, reading
the home's files alone, and the project's — is judged as `ModelManager.setup` judges it: the former release's refusal
first, then the routing profile library the boot loads.

What must hold for every layout:

- the cleanup never raises;
- a boot that started before the cleanup still starts after it, on the same active profile, and if that profile sent
  models somewhere, it still does;
- a boot that only the former release stopped — one that would start with the retired backends still enabled — starts
  after the cleanup, with an active profile that sends models somewhere; or the cleanup left a file both boots read
  for a hand edit, because no change to it suits both.

The seed is fixed, so a failure names a layout that can be replayed. The profile the kit makes active is left out of
the names drawn: a user's own profile under that name, sent to the Gateway, is a known gap of the cleanup tracked on
its own.
"""

import random
from pathlib import Path
from typing import Any

import pytest

from pipelex.cogt.exceptions import RoutingProfileDisabledBackendError, RoutingProfileLibraryError, RoutingProfileLibraryNotFoundError
from pipelex.cogt.model_routing.routing_profile_loader import load_active_routing_profile
from pipelex.migration.former_release import former_release_boot_blockers, inference_merge_sequences
from pipelex.migration.former_release_cleanup import clean_former_release
from pipelex.migration.plan import FileBlockedReason
from pipelex.system.configuration.config_loader import (
    BACKENDS_FILE_NAME,
    BACKENDS_OVERRIDE_FILE_NAME,
    INFERENCE_DIR_NAME,
    ROUTING_PROFILES_FILE_NAME,
    ROUTING_PROFILES_OVERRIDE_FILE_NAME,
)

SEED = 20261008
LAYOUT_COUNT = 400

PROFILE_NAMES = ("all_pipelex_gateway", "custom", "mine", "team")
DEFAULTS = ("openai", "pipelex_gateway", None)
ROUTE_BACKENDS = ("openai", "pipelex_gateway")
ROUTE_PATTERNS = ("gpt-*", "*")
ENABLED_BACKENDS = ["openai", "anthropic"]
WITH_THE_RETIRED_BACKENDS = [*ENABLED_BACKENDS, "pipelex_gateway", "pipelex_manifold"]
BACKENDS_TEXT = '[openai]\nenabled = true\napi_key = "${OPENAI_API_KEY}"\n\n[anthropic]\nenabled = true\napi_key = "${ANTHROPIC_API_KEY}"\n'

# How each file of a layout is drawn: whether it is a base, and how likely it is to exist.
FILES = (
    ("home", ROUTING_PROFILES_FILE_NAME, True, 1.0),
    ("home", ROUTING_PROFILES_OVERRIDE_FILE_NAME, False, 0.5),
    ("project", ROUTING_PROFILES_FILE_NAME, True, 0.4),
    ("project", ROUTING_PROFILES_OVERRIDE_FILE_NAME, False, 0.6),
)


def _routing_text(*, rng: random.Random, is_base: bool) -> str:
    """One routing profiles document: an `active`, always in a base and sometimes in an override, and a few profiles."""
    lines: list[str] = []
    active = rng.choice(PROFILE_NAMES) if is_base else rng.choice([None, None, *PROFILE_NAMES])
    if active is not None:
        lines.append(f'active = "{active}"')
    for name in PROFILE_NAMES:
        if rng.random() < (0.45 if is_base else 0.7):
            continue
        shape = "full" if is_base else rng.choice(["full", "default_only", "routes_only"])
        profile: dict[str, Any] = {}
        if shape == "full":
            profile["description"] = f"{name} description"
            if (default := rng.choice(DEFAULTS)) is not None:
                profile["default"] = default
            if rng.random() < 0.4:
                profile["routes"] = {rng.choice(ROUTE_PATTERNS): rng.choice(ROUTE_BACKENDS)}
        elif shape == "default_only":
            profile["default"] = rng.choice(ROUTE_BACKENDS)
        else:
            profile["routes"] = {rng.choice(ROUTE_PATTERNS): rng.choice(ROUTE_BACKENDS)}
        lines += ["", f"[profiles.{name}]"]
        lines += [f'{key} = "{profile[key]}"' for key in ("description", "default") if key in profile]
        if "routes" in profile:
            lines += ["", f"[profiles.{name}.routes]"]
            lines += [f'"{pattern}" = "{backend}"' for pattern, backend in profile["routes"].items()]
    return "\n".join(lines) + "\n"


def _write_layout(*, rng: random.Random, home: Path, project: Path) -> dict[str, str]:
    (home / INFERENCE_DIR_NAME).mkdir(parents=True)
    (project / INFERENCE_DIR_NAME).mkdir(parents=True)
    (home / INFERENCE_DIR_NAME / BACKENDS_FILE_NAME).write_text(BACKENDS_TEXT, encoding="utf-8")
    layout: dict[str, str] = {}
    for directory, file_name, is_base, likelihood in FILES:
        if rng.random() >= likelihood:
            continue
        text = _routing_text(rng=rng, is_base=is_base)
        ((home if directory == "home" else project) / INFERENCE_DIR_NAME / file_name).write_text(text, encoding="utf-8")
        layout[f"{directory}/{file_name}"] = text
    return layout


def _boots(*, home: Path, project: Path, retired_backends_enabled: bool) -> list[tuple[str, str | None, bool]]:
    """Each boot of the machine as `(verdict, active profile, routes something)`: `starts`, `refused` or `fails`."""
    config_dirs = [home, project]
    routing_sequences = inference_merge_sequences(
        config_dirs=config_dirs, file_name=ROUTING_PROFILES_FILE_NAME, override_file_name=ROUTING_PROFILES_OVERRIDE_FILE_NAME
    )
    backends_sequences = inference_merge_sequences(
        config_dirs=config_dirs, file_name=BACKENDS_FILE_NAME, override_file_name=BACKENDS_OVERRIDE_FILE_NAME
    )
    boots: list[tuple[str, str | None, bool]] = []
    for routing_paths, backends_paths in zip(routing_sequences, backends_sequences, strict=True):
        if not retired_backends_enabled and former_release_boot_blockers(
            backends_library_paths=backends_paths, routing_profile_library_paths=routing_paths
        ):
            boots.append(("refused", None, False))
            continue
        try:
            profile = load_active_routing_profile(
                routing_profile_library_paths=routing_paths,
                enabled_backends=WITH_THE_RETIRED_BACKENDS if retired_backends_enabled else ENABLED_BACKENDS,
            )
        except (RoutingProfileLibraryError, RoutingProfileLibraryNotFoundError, RoutingProfileDisabledBackendError):
            boots.append(("fails", None, False))
            continue
        boots.append(("starts", profile.name, bool(profile.default or profile.routes or profile.fallback_order)))
    return boots


class TestFormerReleaseCleanupInvariants:
    @pytest.mark.parametrize("case", range(LAYOUT_COUNT))
    def test_every_boot_starts_as_it_did_or_better(self, tmp_path: Path, case: int) -> None:
        rng = random.Random(SEED * 10_000 + case)
        home = tmp_path / "home"
        project = tmp_path / "project" / ".pipelex"
        layout = _write_layout(rng=rng, home=home, project=project)
        with_the_gateway = _boots(home=home, project=project, retired_backends_enabled=True)
        before = _boots(home=home, project=project, retired_backends_enabled=False)

        cleanup = clean_former_release(config_dirs=[home, project], dry_run=False)

        after = _boots(home=home, project=project, retired_backends_enabled=False)
        left_for_a_hand_edit = [file for file in cleanup.files if file.blocked_reason is FileBlockedReason.NEEDS_A_HAND_EDIT]
        for boot_name, gateway_boot, boot_before, boot_after in zip(("home", "project"), with_the_gateway, before, after, strict=True):
            context = f"case {case}, {boot_name} boot: before {boot_before}, after {boot_after}, layout {layout}"
            if boot_before[0] == "starts":
                assert boot_after[0] == "starts", f"a boot that started no longer does — {context}"
                assert boot_after[1] == boot_before[1], f"a boot that started switched profile — {context}"
                assert boot_after[2] or not boot_before[2], f"a boot's profile no longer routes anything — {context}"
            elif gateway_boot[0] == "starts" and gateway_boot[2]:
                whole = boot_after[0] == "starts" and boot_after[2]
                assert whole or left_for_a_hand_edit, f"a boot the former release stopped is left without a profile to run on, unreported — {context}"
