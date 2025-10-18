from typing import Literal

from pydantic import Field

from pipelex.core.pipes.pipe_blueprint import AllowedPipeTypes
from pipelex.core.stuffs.structured_content import StructuredContent


class PipeSignature(StructuredContent):
    """PipeSignature is a contract for a pipe.

    It defines the inputs, outputs, and the purpose of the pipe without implementation details.

    Multiplicity Notation:
        Use bracket notation to specify how many items are produced, but only for the outputs:
        - No brackets: single item (default)
        - []: variable-length list
        - [N]: exactly N items (where N is a positive integer)

    Examples:
        - output = "Text[]" - produces multiple text items
        - output = "Image[3]" - produces exactly 3 images
    """

    code: str = Field(description="Pipe code identifying the pipe. Must be snake_case.")
    type: AllowedPipeTypes = Field(description="Pipe type: PipeLLM, PipeImgGen, PipeExtract, PipeSequence, PipeParallel, etc.")
    pipe_category: Literal["PipeSignature"] = "PipeSignature"
    description: str = Field(description="Natural language description of what the pipe does and its purpose in the pipeline.")
    inputs: dict[str, str] = Field(
        description=(
            "Input specifications mapping variable names to concept codes. "
            "Keys: input variable names in snake_case. "
            "Values: ConceptCodes in PascalCase. Don't use multiplicity brackets. "
        )
    )
    result: str = Field(description="Variable name for the pipe's result in snake_case. This name can be referenced as input in subsequent pipes.")
    output: str = Field(
        description=(
            "Output concept code in PascalCase with optional multiplicity brackets. "
            "Examples: 'Text' (single text), 'Article[]' (list of articles), 'Image[5]' (exactly 5 images)."
        )
    )
    pipe_dependencies: list[str] = Field(description="List of pipe codes that this pipe depends on. THis only applies to PipeControllers.")
