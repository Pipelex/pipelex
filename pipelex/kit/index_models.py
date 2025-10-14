from typing import Any

from pydantic import Field

from pipelex.config import ConfigModel


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
    strategy: str = Field(description="Merge strategy (currently only 'merge' supported)")
    marker_begin: str = Field(description="Beginning marker for content insertion")
    marker_end: str = Field(description="Ending marker for content insertion")
    heading_1: str | None = Field(default=None, description="Main title (H1) to add when inserting into empty file or file with no H1 headings")


class AgentRules(ConfigModel):
    """Configuration for merging agent documentation files."""

    sets: dict[str, list[str]] = Field(description="Named sets of agent_rules files (e.g., coding_standards, pipelex_language, all)")
    default_set: str = Field(default="pipelex_language", description="Default set to use when syncing")
    demote: int = Field(default=1, description="Number of levels to demote headings when merging")
    cursor: CursorSpec = Field(description="Cursor rules export configuration")
    targets: dict[str, Target] = Field(description="Dictionary of single-file merge targets keyed by ID")


class KitIndex(ConfigModel):
    """Root configuration model for kit index.toml."""

    meta: dict[str, Any] = Field(default_factory=dict, description="Metadata about the kit configuration")
    agent_rules: AgentRules = Field(description="Agent documentation merge configuration")
