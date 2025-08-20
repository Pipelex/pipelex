from typing import Dict, Optional

from pydantic import BaseModel

from pipelex.core.pipe.pipe_input_spec import InputRequirementBlueprint


class PipeBlueprint(BaseModel):
    """Simple data container for pipe blueprint information."""

    type: str
    definition: Optional[str] = None
    inputs: Optional[Dict[str, InputRequirementBlueprint]] = None
    output: str
