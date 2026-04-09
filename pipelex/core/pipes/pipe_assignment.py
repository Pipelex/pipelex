"""Base Assignment class for the pipe execution pre_run/run/post_run pattern.

An Assignment carries resolved runtime data through the execution lifecycle:
- Created in prepare_assignment() (pre_run phase): models resolved, prompts rendered
- Consumed in execute() (run phase): pure execution using pre-resolved data
- Finalized in finalize_assignment() (post_run phase): execution metadata captured

Each pipe subclass defines its own Assignment type with operator-specific fields.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PipeAssignment(BaseModel):
    """Base Assignment for pipe execution.

    Subclasses add operator-specific fields (rendered prompts, resolved models, etc.).
    The execution_data dict collects metadata for the GraphSpec's execution_data field.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    execution_data: dict[str, Any] = Field(default_factory=dict)
