"""Check that built `pipelex-api` distributions pin pipelex to the release's own version.

The server is released with the library under one version number, and a published `pipelex-api` must install
exactly the pipelex it was released with. `hatch_build.py` writes that pin into the metadata; this script is the
check the release workflow runs on the built wheel and sdist before uploading them, and that pull-request CI runs
on a test build, so a pin that went missing or wrong never reaches PyPI.

For each requirement of `lockstep-dependencies` (in `[tool.hatch.metadata.hooks.custom]` of this member's
`pyproject.toml`), the wheel's `METADATA` and the sdist's `PKG-INFO` must each carry exactly one unconditional
`Requires-Dist` for that package, with the same extras and the specifier `==X.Y.Z`. Both must also declare
`Version: X.Y.Z`. The version defaults to the one in the repository root's `pyproject.toml`.

It needs nothing but the standard library, so it runs on a bare runner without the member's environment.

Usage:
    python api/scripts/check_lockstep_pin.py dist/
    python api/scripts/check_lockstep_pin.py dist/ --version 0.71.0
"""

import argparse
import re
import sys
import tarfile
import tomllib
import zipfile
from email.parser import Parser
from pathlib import Path
from typing import NamedTuple

_MEMBER_ROOT = Path(__file__).resolve().parents[1]
_REPOSITORY_ROOT = _MEMBER_ROOT.parent
_DISTRIBUTION_FILE_PREFIX = "pipelex_api-"

_REQUIREMENT_PATTERN = re.compile(
    r"""^\s*
    (?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)\s*
    (?:\[(?P<extras>[^\]]*)\])?\s*
    (?P<specifier>[^;]*?)\s*
    (?:;\s*(?P<marker>.*?))?\s*$""",
    re.VERBOSE,
)


class ParsedRequirement(NamedTuple):
    name: str
    extras: frozenset[str]
    specifier: str
    marker: str


def normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_requirement(requirement_text: str) -> ParsedRequirement:
    match = _REQUIREMENT_PATTERN.match(requirement_text)
    if match is None:
        msg = f"Cannot parse the requirement `{requirement_text}`."
        raise ValueError(msg)
    extras_text = match.group("extras") or ""
    extras = frozenset(normalize_name(extra.strip()) for extra in extras_text.split(",") if extra.strip())
    return ParsedRequirement(
        name=normalize_name(match.group("name")),
        extras=extras,
        specifier=re.sub(r"\s+", "", match.group("specifier") or "").removeprefix("(").removesuffix(")"),
        marker=(match.group("marker") or "").strip(),
    )


def read_root_version() -> str:
    with (_REPOSITORY_ROOT / "pyproject.toml").open("rb") as root_pyproject:
        version = tomllib.load(root_pyproject)["project"]["version"]
    if not isinstance(version, str):
        msg = "The repository root's `pyproject.toml` declares no string `[project] version`."
        raise TypeError(msg)
    return version


def read_lockstep_requirements() -> list[ParsedRequirement]:
    with (_MEMBER_ROOT / "pyproject.toml").open("rb") as member_pyproject:
        hook_config = tomllib.load(member_pyproject)["tool"]["hatch"]["metadata"]["hooks"]["custom"]
    requirement_texts = hook_config["lockstep-dependencies"]
    if not isinstance(requirement_texts, list) or not requirement_texts:
        msg = "`lockstep-dependencies` in the member's `pyproject.toml` must be a non-empty list."
        raise TypeError(msg)
    return [parse_requirement(str(requirement_text)) for requirement_text in requirement_texts]


def check_metadata(
    *,
    metadata_text: str,
    source: str,
    version: str,
    lockstep_requirements: list[ParsedRequirement],
) -> list[str]:
    """Return what is wrong with one distribution's core metadata, or nothing when it pins correctly."""
    metadata = Parser().parsestr(metadata_text)
    problems: list[str] = []
    declared_version = metadata.get("Version")
    if declared_version != version:
        problems.append(f"{source} declares `Version: {declared_version}`, expected `{version}`.")
    requires_dist = [parse_requirement(str(line)) for line in metadata.get_all("Requires-Dist") or []]
    for expected in lockstep_requirements:
        unconditional = [requirement for requirement in requires_dist if requirement.name == expected.name and not requirement.marker]
        if len(unconditional) != 1:
            problems.append(f"{source} carries {len(unconditional)} unconditional `Requires-Dist` for `{expected.name}`, expected exactly one.")
            continue
        found = unconditional[0]
        if found.specifier != f"=={version}":
            problems.append(f"{source} requires `{expected.name}` with `{found.specifier or 'no version'}`, expected `=={version}`.")
        if found.extras != expected.extras:
            problems.append(f"{source} requires `{expected.name}` with the extras {sorted(found.extras)}, expected {sorted(expected.extras)}.")
    return problems


def read_wheel_metadata(wheel_path: Path) -> str:
    with zipfile.ZipFile(wheel_path) as wheel:
        metadata_names = [name for name in wheel.namelist() if name.endswith(".dist-info/METADATA") and name.count("/") == 1]
        if len(metadata_names) != 1:
            msg = f"{wheel_path.name} holds {len(metadata_names)} top-level `.dist-info/METADATA` files, expected one."
            raise ValueError(msg)
        return wheel.read(metadata_names[0]).decode("utf-8")


def read_sdist_metadata(sdist_path: Path) -> str:
    with tarfile.open(sdist_path, "r:gz") as sdist:
        pkg_info_members = [member for member in sdist.getmembers() if member.name.endswith("/PKG-INFO") and member.name.count("/") == 1]
        if len(pkg_info_members) != 1:
            msg = f"{sdist_path.name} holds {len(pkg_info_members)} top-level `PKG-INFO` files, expected one."
            raise ValueError(msg)
        pkg_info = sdist.extractfile(pkg_info_members[0])
        if pkg_info is None:
            msg = f"{sdist_path.name}'s `PKG-INFO` is not a regular file."
            raise ValueError(msg)
        return pkg_info.read().decode("utf-8")


def check_distributions(*, dist_dir: Path, version: str, lockstep_requirements: list[ParsedRequirement]) -> list[str]:
    """Return what is wrong with the `pipelex-api` wheel and sdist in `dist_dir`, or nothing when both pin correctly."""
    wheels = sorted(dist_dir.glob(f"{_DISTRIBUTION_FILE_PREFIX}*.whl"))
    sdists = sorted(dist_dir.glob(f"{_DISTRIBUTION_FILE_PREFIX}*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        found = ", ".join(path.name for path in [*wheels, *sdists]) or "nothing"
        return [f"Expected exactly one `pipelex-api` wheel and one sdist in {dist_dir}, found: {found}."]
    problems: list[str] = []
    for distribution, read_metadata, expected_name in (
        (wheels[0], read_wheel_metadata, f"{_DISTRIBUTION_FILE_PREFIX}{version}-py3-none-any.whl"),
        (sdists[0], read_sdist_metadata, f"{_DISTRIBUTION_FILE_PREFIX}{version}.tar.gz"),
    ):
        if distribution.name != expected_name:
            problems.append(f"{distribution.name} is not a {version} distribution: expected {expected_name}.")
        try:
            metadata_text = read_metadata(distribution)
        except (OSError, ValueError, zipfile.BadZipFile, tarfile.TarError) as exc:
            problems.append(f"Cannot read the metadata of {distribution.name}: {exc}")
            continue
        problems.extend(
            check_metadata(
                metadata_text=metadata_text,
                source=distribution.name,
                version=version,
                lockstep_requirements=lockstep_requirements,
            )
        )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="Check that built pipelex-api distributions pin pipelex to the release's version.")
    parser.add_argument("dist_dir", type=Path, help="The directory holding the built pipelex-api wheel and sdist")
    parser.add_argument("--version", help="The release's version (default: the repository root's pyproject.toml)")
    args = parser.parse_args()

    version: str = args.version or read_root_version()
    lockstep_requirements = read_lockstep_requirements()
    problems = check_distributions(dist_dir=args.dist_dir, version=version, lockstep_requirements=lockstep_requirements)
    if problems:
        print("Lockstep pin check FAILED:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    pins = ", ".join(f"{requirement.name}=={version}" for requirement in lockstep_requirements)
    print(f"The pipelex-api wheel and sdist in {args.dist_dir} are {version} and pin {pins}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
