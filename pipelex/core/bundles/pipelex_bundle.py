from pathlib import Path
from typing import Dict, Optional

from pydantic import BaseModel

from pipelex.core.concepts.concept import Concept
from pipelex.core.domains.domain import Domain
from pipelex.core.pipes.pipe_abstract import PipeAbstract


class PipelexBundle(BaseModel):
    """Complete bundle of a pipelex bundle."""

    file_path: Optional[Path] = None
    file_content: str
    domain: Domain
    concepts: Dict[str, Concept]
    pipes: Dict[str, PipeAbstract]
