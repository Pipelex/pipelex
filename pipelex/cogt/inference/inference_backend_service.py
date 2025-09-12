from typing import List, Optional

from pydantic import BaseModel

from pipelex.types import StrEnum


class InferenceService(StrEnum):
    LLM = "llm"
    IMAGE_GEN = "image_gen"
