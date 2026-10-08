"""What a former release left in a configuration directory, found by a pure read.

The machine this is about is every former user's: a release that ran models through the Pipelex Gateway, or offered
Pipelex Manifold, wrote tables, routing profiles and files that the current runtime refuses or ignores. The v0.72
directory under `tests/data/migration/former_release/v0_72/` is that release's kit, copied from its wheel, and
`tests/data/inference/previous_release_kit/` is the same era under a neutral name for the Manifold table, which is
what makes it the specimen for a `model_specs_section` key on a backend whose name means nothing to the detector.
"""

import shutil
from pathlib import Path

import pytest

from pipelex.kit.paths import get_kit_configs_dir
from pipelex.migration.former_release import (
    FormerReleaseFinding,
    FormerReleaseFindingKind,
    detect_former_release,
    former_release_boot_blockers,
)
from pipelex.system.configuration.config_loader import (
    BACKENDS_DIR_NAME,
    BACKENDS_FILE_NAME,
    BACKENDS_OVERRIDE_FILE_NAME,
    INFERENCE_DIR_NAME,
    ROUTING_PROFILES_FILE_NAME,
    ROUTING_PROFILES_OVERRIDE_FILE_NAME,
)

V0_72_CONFIG_DIR = Path("tests/data/migration/former_release/v0_72")
PREVIOUS_RELEASE_KIT_DIR = Path("tests/data/inference/previous_release_kit")

# The line of the v0.72 kit's `backends.toml` that enables the Pipelex Gateway.
GATEWAY_ENABLED_LINE = "enabled = true                         # Enable after accepting terms via `pipelex init config`"


def _copy_tree(*, source: Path, destination: Path) -> Path:
    shutil.copytree(source, destination)
    return destination


def _summary(*, findings: list[FormerReleaseFinding], config_dir: Path) -> set[tuple[str, str, str | None, str | None, bool]]:
    """Each finding as (kind, file relative to the directory, subject, route pattern, blocks boot)."""
    return {
        (finding.kind, finding.file_path.relative_to(config_dir).as_posix(), finding.subject, finding.route_pattern, finding.blocks_boot)
        for finding in findings
    }


def _snapshot(*, directory: Path) -> dict[str, bytes]:
    return {path.relative_to(directory).as_posix(): path.read_bytes() for path in sorted(directory.rglob("*")) if path.is_file()}


class TestDetectFormerRelease:
    def test_a_v0_72_directory_is_found_in_full(self, tmp_path: Path) -> None:
        config_dir = _copy_tree(source=V0_72_CONFIG_DIR, destination=tmp_path / ".pipelex")

        findings = detect_former_release(config_dir=config_dir)

        backends = f"{INFERENCE_DIR_NAME}/{BACKENDS_FILE_NAME}"
        routing = f"{INFERENCE_DIR_NAME}/{ROUTING_PROFILES_FILE_NAME}"
        backend_files = f"{INFERENCE_DIR_NAME}/{BACKENDS_DIR_NAME}"
        assert findings.config_dir == config_dir
        assert _summary(findings=findings.findings, config_dir=config_dir) == {
            (FormerReleaseFindingKind.RETIRED_BACKEND_TABLE, backends, "pipelex_gateway", None, True),
            (FormerReleaseFindingKind.RETIRED_BACKEND_FILE, f"{backend_files}/pipelex_gateway.toml", "pipelex_gateway", None, False),
            (FormerReleaseFindingKind.GATEWAY_MODELS_REFERENCE, f"{backend_files}/pipelex_gateway_models.md", None, None, False),
            (FormerReleaseFindingKind.GATEWAY_MODELS_REFERENCE, f"{backend_files}/pipelex_gateway_models_plain.md", None, None, False),
            (FormerReleaseFindingKind.SERVICE_FILE, "pipelex_service.toml", None, None, False),
            (FormerReleaseFindingKind.ACTIVE_ROUTING_PROFILE, routing, "all_pipelex_gateway", None, True),
            (FormerReleaseFindingKind.RETIRED_ROUTING_PROFILE, routing, "all_pipelex_gateway", None, False),
            (FormerReleaseFindingKind.RETIRED_ROUTING_PROFILE, routing, "example_routing_using_patterns", None, False),
            (FormerReleaseFindingKind.ROUTE_TO_RETIRED_BACKEND, routing, "example_routing_using_specific_models", "gpt-5.4-nano", False),
            (FormerReleaseFindingKind.ROUTE_TO_RETIRED_BACKEND, routing, "example_routing_using_specific_models", "claude-4-sonnet", False),
            (FormerReleaseFindingKind.ROUTE_TO_RETIRED_BACKEND, routing, "example_routing_using_specific_models", "gemini-2.5-flash-lite", False),
            (FormerReleaseFindingKind.ROUTE_TO_RETIRED_BACKEND, routing, "example_routing_using_specific_models", "grok-3", False),
        }
        assert not findings.is_clean
        assert findings.blocks_boot

    def test_pipelex_manifold_is_never_found_even_enabled_and_active(self, tmp_path: Path) -> None:
        """Manifold is live: the v0.72 table enabled, its `model_specs_section` kept, and its profile active, is no finding.

        A boot on it is the backend library's to refuse, for the key, with a message naming the change.
        """
        config_dir = _copy_tree(source=V0_72_CONFIG_DIR, destination=tmp_path / ".pipelex")
        inference_dir = config_dir / INFERENCE_DIR_NAME
        (inference_dir / BACKENDS_OVERRIDE_FILE_NAME).write_text(
            "[pipelex_gateway]\nenabled = false\n\n[pipelex_manifold]\nenabled = true\n", encoding="utf-8"
        )
        (inference_dir / ROUTING_PROFILES_OVERRIDE_FILE_NAME).write_text('active = "all_pipelex_manifold"\n', encoding="utf-8")

        findings = detect_former_release(config_dir=config_dir)

        assert not any("manifold" in str(finding.subject) or finding.file_path.name == "pipelex_manifold.toml" for finding in findings.findings)
        assert not findings.blocks_boot

    def test_a_model_specs_section_key_is_found_on_a_backend_of_any_name(self, tmp_path: Path) -> None:
        """The previous kit under its neutral name: the key is what is found, whatever the backend is called."""
        config_dir = tmp_path / ".pipelex"
        _copy_tree(source=PREVIOUS_RELEASE_KIT_DIR, destination=config_dir / INFERENCE_DIR_NAME)

        findings = detect_former_release(config_dir=config_dir)

        model_specs_findings = [finding for finding in findings.findings if finding.kind == FormerReleaseFindingKind.MODEL_SPECS_SECTION_KEY]
        assert [(finding.subject, finding.blocks_boot) for finding in model_specs_findings] == [("retired_preview", False)]
        assert {finding.subject for finding in findings.findings if finding.blocks_boot} == {"pipelex_gateway", "all_pipelex_gateway"}

    def test_an_enabled_backend_still_naming_model_specs_section_stops_the_boot(self, tmp_path: Path) -> None:
        config_dir = tmp_path / ".pipelex"
        inference_dir = config_dir / INFERENCE_DIR_NAME
        inference_dir.mkdir(parents=True)
        (inference_dir / BACKENDS_FILE_NAME).write_text('[acme]\nenabled = true\nmodel_specs_section = "acme_specs"\n', encoding="utf-8")

        findings = detect_former_release(config_dir=config_dir)

        assert [(finding.kind, finding.subject, finding.blocks_boot) for finding in findings.findings] == [
            (FormerReleaseFindingKind.MODEL_SPECS_SECTION_KEY, "acme", True)
        ]

    def test_a_current_kit_and_a_missing_directory_are_clean(self, tmp_path: Path) -> None:
        current = _copy_tree(source=Path(str(get_kit_configs_dir())), destination=tmp_path / "current")

        assert detect_former_release(config_dir=current).is_clean
        assert detect_former_release(config_dir=tmp_path / "missing").is_clean
        assert not detect_former_release(config_dir=current).blocks_boot

    def test_a_disabled_gateway_still_stops_the_boot_through_the_active_profile(self, tmp_path: Path) -> None:
        """The machine the developer met: the gateway turned off, `active` left on its profile."""
        config_dir = _copy_tree(source=V0_72_CONFIG_DIR, destination=tmp_path / ".pipelex")
        backends_path = config_dir / INFERENCE_DIR_NAME / BACKENDS_FILE_NAME
        text = backends_path.read_text(encoding="utf-8")
        assert text.count(GATEWAY_ENABLED_LINE) == 1, "the v0.72 kit no longer enables the gateway on the line this test turns off"
        backends_path.write_text(text.replace(GATEWAY_ENABLED_LINE, "enabled = false"), encoding="utf-8")

        findings = detect_former_release(config_dir=config_dir)

        blocking = [(finding.kind, finding.subject) for finding in findings.findings if finding.blocks_boot]
        assert blocking == [(FormerReleaseFindingKind.ACTIVE_ROUTING_PROFILE, "all_pipelex_gateway")]

    def test_an_override_in_the_same_directory_is_read_with_its_base(self, tmp_path: Path) -> None:
        """A personal override that turned the gateway off and picked another profile: nothing stops the boot."""
        config_dir = _copy_tree(source=V0_72_CONFIG_DIR, destination=tmp_path / ".pipelex")
        inference_dir = config_dir / INFERENCE_DIR_NAME
        (inference_dir / BACKENDS_OVERRIDE_FILE_NAME).write_text("[pipelex_gateway]\nenabled = false\n", encoding="utf-8")
        (inference_dir / ROUTING_PROFILES_OVERRIDE_FILE_NAME).write_text('active = "all_openai"\n', encoding="utf-8")

        findings = detect_former_release(config_dir=config_dir)

        assert not findings.blocks_boot
        override_findings = [finding for finding in findings.findings if finding.file_path.name == BACKENDS_OVERRIDE_FILE_NAME]
        assert [(finding.kind, finding.subject) for finding in override_findings] == [
            (FormerReleaseFindingKind.RETIRED_BACKEND_TABLE, "pipelex_gateway")
        ]

    def test_an_override_naming_a_retired_profile_its_base_does_not_hold_is_found(self, tmp_path: Path) -> None:
        config_dir = _copy_tree(source=Path(str(get_kit_configs_dir())), destination=tmp_path / ".pipelex")
        (config_dir / INFERENCE_DIR_NAME / ROUTING_PROFILES_OVERRIDE_FILE_NAME).write_text('active = "all_pipelex_gateway"\n', encoding="utf-8")

        findings = detect_former_release(config_dir=config_dir)

        assert [(finding.kind, finding.file_path.name, finding.subject, finding.blocks_boot) for finding in findings.findings] == [
            (FormerReleaseFindingKind.ACTIVE_ROUTING_PROFILE, ROUTING_PROFILES_OVERRIDE_FILE_NAME, "all_pipelex_gateway", True)
        ]

    def test_every_file_naming_a_retired_active_profile_is_found_and_only_the_one_the_boot_reads_blocks(self, tmp_path: Path) -> None:
        """A base left on the Gateway's profile under an override that picked another: inert today, refused the day the override goes."""
        config_dir = _copy_tree(source=V0_72_CONFIG_DIR, destination=tmp_path / ".pipelex")
        (config_dir / INFERENCE_DIR_NAME / ROUTING_PROFILES_OVERRIDE_FILE_NAME).write_text('active = "all_openai"\n', encoding="utf-8")

        findings = detect_former_release(config_dir=config_dir)

        active_findings = [finding for finding in findings.findings if finding.kind == FormerReleaseFindingKind.ACTIVE_ROUTING_PROFILE]
        assert [(finding.file_path.name, finding.subject, finding.blocks_boot) for finding in active_findings] == [
            (ROUTING_PROFILES_FILE_NAME, "all_pipelex_gateway", False)
        ]

    def test_an_active_profile_routing_a_model_to_a_retired_backend_stops_the_boot_on_that_route(self, tmp_path: Path) -> None:
        config_dir = _copy_tree(source=V0_72_CONFIG_DIR, destination=tmp_path / ".pipelex")
        override_path = config_dir / INFERENCE_DIR_NAME / ROUTING_PROFILES_OVERRIDE_FILE_NAME
        override_path.write_text('active = "example_routing_using_specific_models"\n', encoding="utf-8")

        findings = detect_former_release(config_dir=config_dir)

        active_findings = [finding for finding in findings.findings if finding.kind == FormerReleaseFindingKind.ACTIVE_ROUTING_PROFILE]
        assert [
            (finding.file_path.name, finding.subject, finding.route_pattern, finding.retired_backend, finding.blocks_boot)
            for finding in active_findings
        ] == [
            (ROUTING_PROFILES_FILE_NAME, "all_pipelex_gateway", None, "pipelex_gateway", False),
            (ROUTING_PROFILES_OVERRIDE_FILE_NAME, "example_routing_using_specific_models", "gpt-5.4-nano", "pipelex_gateway", True),
        ]
        assert active_findings[1].description == (
            f"'{override_path}' makes 'example_routing_using_specific_models' the active routing profile, "
            "and it routes 'gpt-5.4-nano' to 'pipelex_gateway'"
        )

    def test_an_unreadable_document_is_skipped_rather_than_raised(self, tmp_path: Path) -> None:
        """Whether the file parses is the boot's and the doctor's to say; the detector judges what it can read."""
        config_dir = _copy_tree(source=V0_72_CONFIG_DIR, destination=tmp_path / ".pipelex")
        (config_dir / INFERENCE_DIR_NAME / BACKENDS_FILE_NAME).write_text("[pipelex_gateway\nbroken", encoding="utf-8")

        findings = detect_former_release(config_dir=config_dir)

        assert FormerReleaseFindingKind.RETIRED_BACKEND_TABLE not in {finding.kind for finding in findings.findings}
        assert FormerReleaseFindingKind.ACTIVE_ROUTING_PROFILE in {finding.kind for finding in findings.findings}

    def test_detecting_writes_nothing(self, tmp_path: Path) -> None:
        config_dir = _copy_tree(source=V0_72_CONFIG_DIR, destination=tmp_path / ".pipelex")
        before = _snapshot(directory=config_dir)

        detect_former_release(config_dir=config_dir)

        assert _snapshot(directory=config_dir) == before

    @pytest.mark.parametrize("use_override", [False, True])
    def test_the_boot_blockers_are_read_from_the_files_the_boot_merges(self, tmp_path: Path, use_override: bool) -> None:
        """Across directories, as the boot reads them: a project's override can lift what the home's base would stop."""
        home_inference = _copy_tree(source=V0_72_CONFIG_DIR, destination=tmp_path / "home") / INFERENCE_DIR_NAME
        project_inference = tmp_path / "project" / INFERENCE_DIR_NAME
        project_inference.mkdir(parents=True)
        if use_override:
            (project_inference / BACKENDS_OVERRIDE_FILE_NAME).write_text("[pipelex_gateway]\nenabled = false\n", encoding="utf-8")
            (project_inference / ROUTING_PROFILES_OVERRIDE_FILE_NAME).write_text('active = "all_openai"\n', encoding="utf-8")

        blockers = former_release_boot_blockers(
            backends_library_paths=[home_inference / BACKENDS_FILE_NAME, project_inference / BACKENDS_OVERRIDE_FILE_NAME],
            routing_profile_library_paths=[home_inference / ROUTING_PROFILES_FILE_NAME, project_inference / ROUTING_PROFILES_OVERRIDE_FILE_NAME],
        )

        if use_override:
            assert blockers == []
        else:
            assert [(finding.kind, finding.subject) for finding in blockers] == [
                (FormerReleaseFindingKind.RETIRED_BACKEND_TABLE, "pipelex_gateway"),
                (FormerReleaseFindingKind.ACTIVE_ROUTING_PROFILE, "all_pipelex_gateway"),
            ]
            assert all(finding.blocks_boot for finding in blockers)
