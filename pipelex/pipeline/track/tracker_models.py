from typing import Dict, List

from pydantic import BaseModel

from pipelex.types import StrEnum


class NodeCategory(StrEnum):
    SPECIAL = "special"
    STUFF = "stuff"
    CONDITION = "condition"


class NodeAttributeKey(StrEnum):
    CATEGORY = "category"
    NAME = "name"
    TAG = "tag"
    DESCRIPTION = "description"
    DEBUG_INFO = "debug_info"
    SUBGRAPH = "subgraph"
    COMMENT = "comment"


class SpecialNodeName(StrEnum):
    START = "start"


class EdgeCategory(StrEnum):
    PIPE = "pipe"
    BATCH = "batch"
    AGGREGATE = "aggregate"
    CONDITION = "condition"
    CHOICE = "choice"


class EdgeAttributeKey(StrEnum):
    EDGE_CATEGORY = "edge_category"
    PIPE_CODE = "pipe_code"
    CONDITION_EXPRESSION = "condition_expression"
    CHOSEN_PIPE = "chosen_pipe"


class GraphTree(BaseModel):
    nodes_by_subgraph: Dict[str, List[str]]


class SubGraphClassDef(BaseModel):
    name: str
    color: str
