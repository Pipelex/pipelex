from typing import Dict

from pydantic import Field

from pipelex.core.bundle.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.stuff.stuff_content import StructuredContent


class PipeDraft(StructuredContent):
    code: str
    type: str
    definition: str
    inputs: Dict[str, str]
    output: str


class PipelineDraft(StructuredContent):
    """Complete blueprint of a pipeline library TOML file."""

    # Domain information (required)
    domain: str
    definition: str

    # Concepts section - concept_name -> definition (string) or blueprint (dict)
    concept: Dict[str, str] = Field(default_factory=dict)

    # Pipes section - pipe_name -> blueprint dict
    pipe: Dict[str, PipeDraft] = Field(default_factory=dict)


class PipelexBundleBlueprintStuff(PipelexBundleBlueprint, StructuredContent):
    """Complete blueprint of a pipelex bundle TOML file."""

    pass
