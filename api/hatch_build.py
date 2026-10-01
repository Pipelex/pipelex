"""The hatch metadata hook that pins the published server on the pipelex it was released with.

The server and the library are released together under one version number, which this member reads from the
repository root's `pyproject.toml` (`[tool.hatch.version]`). In the workspace, its `pipelex` dependency resolves
from the same commit and carries no version, because uv ignores a version specifier on a workspace source. A
published `pipelex-api` has no workspace to resolve from, so its metadata must say which pipelex it was released
with, or an install would pair the server with whatever pipelex PyPI serves.

This hook writes the dependencies: each requirement of `lockstep-dependencies` pinned to `==` this distribution's
own version, then `dependencies` as written. Both lists live in `[tool.hatch.metadata.hooks.custom]` of
`pyproject.toml`, and `dependencies` is declared dynamic there, since a build backend may not rewrite a static
field. A wheel built from the sdist reads the dependencies back from `PKG-INFO`, so this hook runs once per release.
"""

from __future__ import annotations

from typing import Any

from hatchling.metadata.plugin.interface import MetadataHookInterface
from packaging.requirements import Requirement


class LockstepPinMetadataHook(MetadataHookInterface):
    def update(self, metadata: dict[str, Any]) -> None:
        version = metadata.get("version")
        if not isinstance(version, str) or not version:
            msg = "The lockstep pin needs the distribution's version, which hatch had not resolved when the hook ran."
            raise ValueError(msg)
        lockstep_requirements = self._string_list(option="lockstep-dependencies")
        other_requirements = self._string_list(option="dependencies")
        pinned_requirements: list[str] = []
        for requirement_text in lockstep_requirements:
            requirement = Requirement(requirement_text)
            if requirement.specifier or requirement.url or requirement.marker:
                msg = (
                    f"`{requirement_text}` in `lockstep-dependencies` must name the package and its extras only: "
                    "the hook supplies the version, so a specifier, a URL or a marker written here would be overridden."
                )
                raise ValueError(msg)
            pinned_requirements.append(f"{requirement_text}=={version}")
        metadata["dependencies"] = [*pinned_requirements, *other_requirements]

    def _string_list(self, *, option: str) -> list[str]:
        value = self.config.get(option)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            msg = f"Option `{option}` of the custom metadata hook must be a list of strings."
            raise TypeError(msg)
        return list(value)
