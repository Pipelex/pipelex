from typing import Any, Dict, Optional, Union

from pydantic import Field

from pipelex.core.concept_blueprint import ConceptBlueprint
from pipelex.core.stuff_content import StructuredContent
from pipelex.exceptions import LibraryError


class PipelineBlueprintValidationError(LibraryError):
    """Error raised when a pipeline blueprint fails validation."""

    def __init__(self, file_path: str, validation_error_msg: str):
        self.file_path = file_path
        self.validation_error_msg = validation_error_msg
        super().__init__(f"Pipeline blueprint validation failed for '{file_path}': {validation_error_msg}")


class ConceptBlueprintError(LibraryError):
    """Error raised when loading concept blueprints."""

    def __init__(self, file_path: str, concept_name: str, error_msg: str):
        self.file_path = file_path
        self.concept_name = concept_name
        super().__init__(f"Error loading concept '{concept_name}' from '{file_path}': {error_msg}")


class PipeBlueprintError(LibraryError):
    """Error raised when loading pipe blueprints."""

    def __init__(self, file_path: str, pipe_name: str, error_msg: str):
        self.file_path = file_path
        self.pipe_name = pipe_name
        super().__init__(f"Error loading pipe '{pipe_name}' from '{file_path}': {error_msg}")


class PipelineBlueprint(StructuredContent):
    """Complete blueprint of a pipeline TOML definition."""

    # Domain information (required)
    domain: str
    definition: Optional[str] = None
    system_prompt: Optional[str] = None
    system_prompt_to_structure: Optional[str] = None
    prompt_template_to_structure: Optional[str] = None

    # Concepts section - concept_name -> definition (string) or blueprint (dict)
    concept: Dict[str, Union[str, ConceptBlueprint]] = Field(default_factory=dict)

    # Pipes section - pipe_name -> blueprint dict
    pipe: Dict[str, Dict[str, Any]] = Field(default_factory=dict)

    @property
    def desc(self) -> str:
        if self.definition:
            return f"{self.domain} • {self.definition[:100]}"
        else:
            return self.domain
