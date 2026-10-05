"""Read a dry run's GraphSpec by pipe code, for the tests of a dry-run condition's shared output."""

from pipelex.graph.graphspec import GraphSpec, IOSpec, NodeSpec


def node_by_code(graph_spec: GraphSpec, pipe_code: str) -> NodeSpec:
    matches = nodes_by_code(graph_spec, pipe_code)
    assert len(matches) == 1, f"expected one node for '{pipe_code}', found {len(matches)}"
    return matches[0]


def nodes_by_code(graph_spec: GraphSpec, pipe_code: str) -> list[NodeSpec]:
    return [node for node in graph_spec.nodes if node.pipe_code == pipe_code]


def only_output(node: NodeSpec) -> IOSpec:
    assert len(node.node_io.outputs) == 1, f"expected one output on '{node.pipe_code}', found {node.node_io.outputs}"
    return node.node_io.outputs[0]


def input_named(node: NodeSpec, name: str) -> IOSpec:
    matches = [input_spec for input_spec in node.node_io.inputs if input_spec.name == name]
    assert len(matches) == 1, f"expected one input '{name}' on '{node.pipe_code}', found {node.node_io.inputs}"
    return matches[0]


def read_digests(graph_spec: GraphSpec) -> set[str]:
    return {input_spec.digest for node in graph_spec.nodes for input_spec in node.node_io.inputs if input_spec.digest is not None}


def output_named(node: NodeSpec, name: str) -> IOSpec:
    matches = [output_spec for output_spec in node.node_io.outputs if output_spec.name == name]
    assert len(matches) == 1, f"expected one output '{name}' on '{node.pipe_code}', found {node.node_io.outputs}"
    return matches[0]
