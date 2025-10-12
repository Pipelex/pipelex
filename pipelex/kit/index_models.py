"""Pydantic models for kit index configuration."""

from typing import Any

from pydantic import BaseModel, Field


class AgentsMerge(BaseModel):
    """Configuration for merging agent documentation files."""

    order: list[str] = Field(description="Ordered list of agent markdown files to merge")
    demote: int = Field(default=1, description="Number of levels to demote headings when merging")


class CursorFileOverride(BaseModel):
    """Per-file front-matter overrides for Cursor export."""

    front_matter: dict[str, Any] = Field(default_factory=dict, description="Front-matter to override for this file")


class CursorSpec(BaseModel):
    """Configuration for Cursor rules export."""

    front_matter: dict[str, Any] = Field(default_factory=dict, description="Default YAML front-matter for all Cursor files")
    files: dict[str, CursorFileOverride] = Field(default_factory=dict, description="Per-file front-matter overrides")


class Target(BaseModel):
    """Configuration for a single-file merge target."""

    id: str = Field(description="Unique identifier for this target")
    path: str = Field(description="Path to the target file relative to repo root")
    strategy: str = Field(description="Merge strategy (currently only 'merge' supported)")
    marker_begin: str = Field(description="Beginning marker for content insertion")
    marker_end: str = Field(description="Ending marker for content insertion")
    parent: str | None = Field(default=None, description="Parent heading to insert under if markers not found")


class KitIndex(BaseModel):
    """Root configuration model for kit index.toml."""

    meta: dict[str, Any] = Field(default_factory=dict, description="Metadata about the kit configuration")
    agents: AgentsMerge = Field(description="Agent documentation merge configuration")
    cursor: CursorSpec = Field(description="Cursor rules export configuration")
    targets: list[Target] = Field(description="List of single-file merge targets")
