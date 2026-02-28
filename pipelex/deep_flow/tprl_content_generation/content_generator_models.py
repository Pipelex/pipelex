from typing import Union

from pydantic import BaseModel

from pipelex.cogt.content_generation.assignment_models import ImggAssignment, LLMAssignment, ObjectAssignment, TextThenObjectAssignment
from pipelex.cogt.image.generated_image import GeneratedImage

AssignmentType = Union[
    LLMAssignment,
    ObjectAssignment,
    TextThenObjectAssignment,
    ImggAssignment,
]

ResultType = Union[
    str,
    BaseModel,
    list[BaseModel],
    GeneratedImage,
]
