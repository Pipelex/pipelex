from typing import Dict

from pydantic import BaseModel

from pipelex.core.concepts.concept import Concept
from pipelex.core.domains.domain import Domain
from pipelex.core.pipes.pipe_abstract import PipeAbstract


class PipelexBundle(BaseModel):
    """Complete bundle of a pipelex bundle."""

    domain: Domain
    concepts: Dict[str, Concept]
    pipes: Dict[str, PipeAbstract]
