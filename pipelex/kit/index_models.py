from typing import Any

from pydantic import Field

from pipelex.system.configuration.config_model import ConfigModel


class CursorFileOverride(ConfigModel):
    """Per-file front-matter overrides for Cursor export."""

    front_matter: dict[str, Any] = Field(default_factory=dict, description="Front-matter to override for this file")


class CursorSpec(ConfigModel):
    """Configuration for Cursor rules export."""

    front_matter: dict[str, Any] = Field(default_factory=dict, description="Default YAML front-matter for all Cursor files")
    files: dict[str, CursorFileOverride] = Field(default_factory=dict, description="Per-file front-matter overrides")


class Target(ConfigModel):
    """Configuration for a single-file merge target."""

    path: str = Field(description="Path to the target file relative to repo root")
    sets: dict[str, list[str]] | None = Field(default=None, description="Target-specific named sets overrides for agent_rules files (e.g., all)")


class AgentRules(ConfigModel):
    """Configuration for merging agent documentation files."""

    sets: dict[str, list[str]] = Field(description="Named sets of agent_rules files (e.g., all)")
    default_set: str = Field(default="all", description="Default set to use when syncing")
    demote: int = Field(default=1, description="Number of levels to demote headings when merging")
    cursor: CursorSpec = Field(description="Cursor rules export configuration")
    targets: dict[str, Target] = Field(description="Dictionary of single-file merge targets keyed by ID")


class KitIndex(ConfigModel):
    """Root configuration model for kit index.toml."""

    meta: dict[str, Any] = Field(default_factory=dict, description="Metadata about the kit configuration")
    agent_rules: AgentRules = Field(description="Agent documentation merge configuration")
