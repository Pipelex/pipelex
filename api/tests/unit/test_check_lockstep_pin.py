"""`scripts/check_lockstep_pin.py` refuses a `pipelex-api` distribution that does not pin its pipelex exactly.

The release workflow runs it on the built wheel and sdist before uploading them, so it is the last thing between a
missing or wrong pin and PyPI. These tests build small distributions by hand, one defect at a time, and check that
each is reported. The script is a standalone entry point, not a package module, so it is loaded from its path.
"""

import importlib.util
import io
import tarfile
import zipfile
from pathlib import Path
from types import ModuleType

import pytest

_MEMBER_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_PATH = _MEMBER_ROOT / "scripts" / "check_lockstep_pin.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_lockstep_pin", _SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_lockstep_pin = _load_script()

VERSION = "1.2.3"
PINNED_REQUIREMENT = "pipelex[anthropic,bedrock,fal,google,google-genai,mistralai]==1.2.3"
CONFIGURED_REQUIREMENT = "pipelex[mistralai,anthropic,google,google-genai,bedrock,fal]"


def _metadata(*, version: str = VERSION, requirements: list[str]) -> str:
    lines = ["Metadata-Version: 2.4", "Name: pipelex-api", f"Version: {version}"]
    lines.extend(f"Requires-Dist: {requirement}" for requirement in requirements)
    return "\n".join(lines) + "\n"


def _write_wheel(*, dist_dir: Path, version: str, metadata_text: str) -> None:
    with zipfile.ZipFile(dist_dir / f"pipelex_api-{version}-py3-none-any.whl", "w") as wheel:
        wheel.writestr(f"pipelex_api-{version}.dist-info/METADATA", metadata_text)
        wheel.writestr("pipelex_api/__init__.py", "")


def _write_sdist(*, dist_dir: Path, version: str, metadata_text: str) -> None:
    payload = metadata_text.encode("utf-8")
    member = tarfile.TarInfo(name=f"pipelex_api-{version}/PKG-INFO")
    member.size = len(payload)
    with tarfile.open(dist_dir / f"pipelex_api-{version}.tar.gz", "w:gz") as sdist:
        sdist.addfile(member, io.BytesIO(payload))


def _write_distributions(*, dist_dir: Path, version: str = VERSION, requirements: list[str]) -> None:
    metadata_text = _metadata(version=version, requirements=requirements)
    _write_wheel(dist_dir=dist_dir, version=version, metadata_text=metadata_text)
    _write_sdist(dist_dir=dist_dir, version=version, metadata_text=metadata_text)


def _check(dist_dir: Path, version: str = VERSION) -> list[str]:
    lockstep_requirements = [check_lockstep_pin.parse_requirement(CONFIGURED_REQUIREMENT)]
    problems: list[str] = check_lockstep_pin.check_distributions(
        dist_dir=dist_dir,
        version=version,
        lockstep_requirements=lockstep_requirements,
    )
    return problems


class TestCheckLockstepPin:
    def test_exact_pin_in_wheel_and_sdist_passes(self, tmp_path: Path) -> None:
        _write_distributions(
            dist_dir=tmp_path,
            requirements=["fastapi>=0.118.0", PINNED_REQUIREMENT, "pytest>=8; extra == 'dev'"],
        )
        assert _check(tmp_path) == []

    @pytest.mark.parametrize(
        ("requirement", "expected_fragment"),
        [
            ("pipelex[anthropic,bedrock,fal,google,google-genai,mistralai]", "with `no version`, expected `==1.2.3`"),
            ("pipelex[anthropic,bedrock,fal,google,google-genai,mistralai]>=1.2.3", "with `>=1.2.3`, expected `==1.2.3`"),
            ("pipelex[anthropic,bedrock,fal,google,google-genai,mistralai]==1.2.2", "with `==1.2.2`, expected `==1.2.3`"),
            ("pipelex[anthropic,google]==1.2.3", "expected ['anthropic', 'bedrock', 'fal', 'google', 'google-genai', 'mistralai']"),
        ],
    )
    def test_a_wrong_pin_is_reported_for_both_distributions(self, tmp_path: Path, requirement: str, expected_fragment: str) -> None:
        _write_distributions(dist_dir=tmp_path, requirements=["fastapi>=0.118.0", requirement])
        problems = _check(tmp_path)
        assert len(problems) == 2
        assert all(expected_fragment in problem for problem in problems)

    def test_a_requirement_behind_a_marker_is_not_the_pin(self, tmp_path: Path) -> None:
        _write_distributions(dist_dir=tmp_path, requirements=[f"{PINNED_REQUIREMENT}; extra == 'dev'"])
        problems = _check(tmp_path)
        assert problems == [
            "pipelex_api-1.2.3-py3-none-any.whl carries 0 unconditional `Requires-Dist` for `pipelex`, expected exactly one.",
            "pipelex_api-1.2.3.tar.gz carries 0 unconditional `Requires-Dist` for `pipelex`, expected exactly one.",
        ]

    def test_distributions_of_another_version_are_refused(self, tmp_path: Path) -> None:
        _write_distributions(dist_dir=tmp_path, requirements=[PINNED_REQUIREMENT])
        problems = _check(tmp_path, version="1.2.4")
        assert "pipelex_api-1.2.3-py3-none-any.whl is not a 1.2.4 distribution: expected pipelex_api-1.2.4-py3-none-any.whl." in problems
        assert "pipelex_api-1.2.3.tar.gz declares `Version: 1.2.3`, expected `1.2.4`." in problems

    def test_a_missing_sdist_is_refused(self, tmp_path: Path) -> None:
        _write_wheel(dist_dir=tmp_path, version=VERSION, metadata_text=_metadata(requirements=[PINNED_REQUIREMENT]))
        problems = _check(tmp_path)
        assert problems == [f"Expected exactly one `pipelex-api` wheel and one sdist in {tmp_path}, found: pipelex_api-1.2.3-py3-none-any.whl."]

    def test_the_configured_lockstep_requirement_names_pipelex_without_a_version(self) -> None:
        lockstep_requirements = check_lockstep_pin.read_lockstep_requirements()
        assert [requirement.name for requirement in lockstep_requirements] == ["pipelex"]
        assert all(requirement.specifier == "" and requirement.marker == "" for requirement in lockstep_requirements)
