"""Data models for the know-how graph: concepts, pipes, edges, and the graph container."""

from pydantic import BaseModel, ConfigDict, Field

from pipelex.tools.typing.pydantic_utils import empty_list_factory_of
from pipelex.types import StrEnum

NATIVE_PACKAGE_ADDRESS = "__native__"


class ConceptId(BaseModel):
    """Unique concept identity across the ecosystem.

    Combines a package address with a domain-qualified concept reference
    to uniquely identify concepts even when different packages define
    concepts with the same code.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    package_address: str
    concept_ref: str

    @property
    def node_key(self) -> str:
        return f"{self.package_address}::{self.concept_ref}"

    @property
    def concept_code(self) -> str:
        """Last segment of the concept_ref (split on '.')."""
        return self.concept_ref.rsplit(".", maxsplit=1)[-1]

    @property
    def is_native(self) -> bool:
        return self.package_address == NATIVE_PACKAGE_ADDRESS


class EdgeKind(StrEnum):
    DATA_FLOW = "data_flow"
    REFINEMENT = "refinement"


class PipeNode(BaseModel):
    """A pipe in the graph with resolved concept identities."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    package_address: str
    pipe_code: str
    pipe_type: str
    domain_code: str
    description: str
    is_exported: bool
    input_concept_ids: dict[str, ConceptId] = Field(default_factory=dict)
    output_concept_id: ConceptId

    @property
    def node_key(self) -> str:
        return f"{self.package_address}::{self.pipe_code}"


class ConceptNode(BaseModel):
    """A concept in the graph with optional refinement link."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    concept_id: ConceptId
    description: str
    refines: ConceptId | None = None
    structure_fields: list[str] = Field(default_factory=list)


class GraphEdge(BaseModel):
    """An edge in the know-how graph, discriminated by kind.

    For DATA_FLOW edges: source_pipe_key and target_pipe_key identify connected pipes,
    input_param names the target pipe's input parameter being satisfied.

    For REFINEMENT edges: source_concept_id refines target_concept_id.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: EdgeKind = Field(strict=False)
    # DATA_FLOW fields
    source_pipe_key: str | None = None
    target_pipe_key: str | None = None
    input_param: str | None = None
    # REFINEMENT fields
    source_concept_id: ConceptId | None = None
    target_concept_id: ConceptId | None = None


class KnowHowGraph(BaseModel):
    """Mutable container for the know-how graph.

    Holds pipe nodes, concept nodes, and edges connecting them.
    """

    model_config = ConfigDict(extra="forbid")

    pipe_nodes: dict[str, PipeNode] = Field(default_factory=dict)
    concept_nodes: dict[str, ConceptNode] = Field(default_factory=dict)
    data_flow_edges: list[GraphEdge] = Field(default_factory=empty_list_factory_of(GraphEdge))
    refinement_edges: list[GraphEdge] = Field(default_factory=empty_list_factory_of(GraphEdge))

    def get_pipe_node(self, key: str) -> PipeNode | None:
        """Retrieve a pipe node by its node_key."""
        return self.pipe_nodes.get(key)

    def get_concept_node(self, concept_id: ConceptId) -> ConceptNode | None:
        """Retrieve a concept node by its ConceptId."""
        return self.concept_nodes.get(concept_id.node_key)

    def get_outgoing_data_flow(self, pipe_key: str) -> list[GraphEdge]:
        """Return data flow edges where the given pipe is the source (producer)."""
        return [edge for edge in self.data_flow_edges if edge.source_pipe_key == pipe_key]

    def get_incoming_data_flow(self, pipe_key: str) -> list[GraphEdge]:
        """Return data flow edges where the given pipe is the target (consumer)."""
        return [edge for edge in self.data_flow_edges if edge.target_pipe_key == pipe_key]
