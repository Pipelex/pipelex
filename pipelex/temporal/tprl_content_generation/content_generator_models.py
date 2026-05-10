from typing import Union

from pydantic import BaseModel

from pipelex.cogt.content_generation.assignment_models import ImgGenAssignment, LLMAssignment, ObjectAssignment
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails

AssignmentType = Union[
    LLMAssignment,
    ObjectAssignment,
    ImgGenAssignment,
]

ResultType = Union[
    str,
    BaseModel,
    list[BaseModel],
    GeneratedImageRawDetails,
]
