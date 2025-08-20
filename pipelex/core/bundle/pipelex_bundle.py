from typing import Dict

from pydantic import BaseModel

from pipelex.core.concept.concept import Concept
from pipelex.core.domain.domain import Domain
from pipelex.core.pipe.pipe_abstract import PipeAbstract


class PipelexBundle(BaseModel):
    """Complete bundle of a pipelex bundle."""

    domain: Domain
    concepts: Dict[str, Concept]
    pipes: Dict[str, PipeAbstract]
