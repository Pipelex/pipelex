from typing import Dict

from pydantic import Field

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint as PipelexBundleBlueprintBaseModel
from pipelex.core.stuffs.stuff_content import StructuredContent


class PipeDraft(StructuredContent):
    code: str
    type: str
    definition: str
    inputs: Dict[str, str]
    output: str


class PipelineDraft(StructuredContent):
    """Complete blueprint of a pipeline library PLX file."""

    # Domain information (required)
    domain: str
    definition: str

    # Concepts section - concept_name -> definition (string) or blueprint (dict)
    concept: Dict[str, str] = Field(default_factory=dict)

    # Pipes section - pipe_name -> blueprint dict
    pipe: Dict[str, PipeDraft] = Field(default_factory=dict)


class PipelexBundleBlueprint(PipelexBundleBlueprintBaseModel, StructuredContent):
    """Complete blueprint of a pipelex bundle PLX file."""

    pass
