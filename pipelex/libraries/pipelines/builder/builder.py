from typing import Dict

from pydantic import Field

from pipelex.core.stuffs.stuff_content import StructuredContent
from pipelex.libraries.pipelines.builder.concept.concept import ConceptSpec
from pipelex.libraries.pipelines.builder.pipe.pipe import PipeSignature


class PipelexBundleBlueprintDraft(StructuredContent):
    """Complete blueprint of a pipeline library TOML file."""

    domain: str = Field(description="The domain of the pipeline library.")
    definition: str = Field(description="The definition of the pipeline library.")

    concept: Dict[str, ConceptSpec] = Field(default_factory=dict, description="The concepts of the pipeline library.")

    pipe: Dict[str, PipeSignature] = Field(default_factory=dict, description="The pipes of the pipeline library.")
