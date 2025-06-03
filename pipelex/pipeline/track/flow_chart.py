# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownParameterType=false
# pyright: reportMissingTypeArgument=false
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx
import yaml

from pipelex import log
from pipelex.exceptions import JobHistoryError
from pipelex.pipeline.track.tracker_config import TrackerConfig
from pipelex.pipeline.track.tracker_models import (
    EdgeAttributeKey,
    EdgeCategory,
    GraphTree,
    NodeAttributeKey,
    NodeCategory,
    SubGraphClassDef,
)
from pipelex.tools.misc.mermaid_utils import clean_str_for_mermaid_node_title, make_mermaid_url
from pipelex.tools.misc.string_utils import snake_to_capitalize_first_letter


def nice_edge_tag(edge_tag: str) -> str:
    return f'"{snake_to_capitalize_first_letter(edge_tag)}"'


def _indent_line(line: str, indent: int) -> str:
    return f"{'    ' * indent}{line}"


class PipelineFlowChart:
    def __init__(self, nx_graph: nx.DiGraph, start_node: str, tracker_config: TrackerConfig):
        self.nx_graph = nx_graph
        self._tracker_config = tracker_config
        self.is_debug_mode = tracker_config.is_debug_mode
        self.start_node = start_node
        self.sub_graph_class_defs: List[SubGraphClassDef] = []
        for sub_graph_index, sub_graph_color in enumerate(self._tracker_config.sub_graph_colors):
            class_def_letter = chr(ord("a") + sub_graph_index)
            class_def_name = f"sub_{class_def_letter}"
            self.sub_graph_class_defs.append(SubGraphClassDef(name=class_def_name, color=sub_graph_color))

    def generate_mermaid_flowchart(
        self,
        title: Optional[str] = None,
        subtitle: Optional[str] = None,
    ) -> Tuple[str, str]:
        nb_nodes = len(self.nx_graph.nodes)
        if nb_nodes == 0:
            raise JobHistoryError("Graph has no nodes")
        log.debug(f"Generating mermaid flowchart for the whole graph which holds {nb_nodes} nodes")
        mermaid_settings: Dict[str, Any] = {}
        if title:
            mermaid_settings["title"] = title
        mermaid_settings["config"] = {}
        if self._tracker_config.applied_theme:
            mermaid_settings["config"]["theme"] = self._tracker_config.applied_theme
        if self._tracker_config.applied_layout:
            mermaid_settings["config"]["layout"] = self._tracker_config.applied_layout
        if self._tracker_config.applied_wrapping_width:
            mermaid_settings["config"]["flowchart"] = {"wrappingWidth": self._tracker_config.applied_wrapping_width}
        mermaid_code = "---\n"
        mermaid_code += yaml.dump(mermaid_settings)
        mermaid_code += "---\n"
        mermaid_code += "flowchart LR\n"

        graph_tree: GraphTree = GraphTree(nodes_by_subgraph={})

        # First pass: Collect nodes into their respective subgraphs
        for node in self.nx_graph.nodes:
            node_attributes = self.nx_graph.nodes[node]
            if not node_attributes:
                raise JobHistoryError(f"Node attributes are empty for node '{node}'")
            node_pipe_layer = node_attributes.get(NodeAttributeKey.SUBGRAPH)
            if not node_pipe_layer:
                node_pipe_layer = "Unknown"
            elif not isinstance(node_pipe_layer, str):
                raise JobHistoryError(f"Node '{node}' has no pipe stack: {node_attributes}")

            sub_graph = node_pipe_layer or "root"
            # Split sub_graph by "-" and keep the last token
            if "-" in sub_graph:
                sub_graph = sub_graph.split("-")[-1]
            if sub_graph not in graph_tree.nodes_by_subgraph:
                graph_tree.nodes_by_subgraph[sub_graph] = []
            graph_tree.nodes_by_subgraph[sub_graph].append(node)

        log.verbose(graph_tree, title="Graph tree")

        subgraph_lines = self.generate_subgraph_lines(graph_tree)
        mermaid_code += "\n".join(subgraph_lines)
        mermaid_code += "\n"

        # Generate subtitle
        if subtitle:
            # this is a hack to add something that looks like a subtitle, but it's actually a node with no stroke and no visible link
            # if self.start_node is None:
            #     raise JobHistoryError("Start node is not set")
            mermaid_code += f"""
    classDef subtitleNodeClass fill:transparent,stroke:#333,stroke-width:0px;
    __subtitle__["{subtitle}"]
    class __subtitle__ subtitleNodeClass;
    __subtitle__ --> {self.start_node}
    linkStyle 0 stroke:transparent,stroke-width:0px
"""

        for sub_graph_class_def in self.sub_graph_class_defs:
            mermaid_code += f"""
    classDef {sub_graph_class_def.name} fill:{sub_graph_class_def.color},color:#333,stroke:#333;
"""

        # Generate edges
        for edge in self.nx_graph.edges(data=True):
            source, target, edge_data = edge
            edge_tag: str
            edge_type = EdgeCategory(edge_data[EdgeAttributeKey.EDGE_CATEGORY])
            match edge_type:
                case EdgeCategory.PIPE:
                    if pipe_code := edge_data.get(EdgeAttributeKey.PIPE_CODE):
                        edge_tag = nice_edge_tag(pipe_code)
                        mermaid_code += f"    {source} -- {edge_tag} {self._tracker_config.pipe_edge_style} {target}\n"
                    else:
                        raise JobHistoryError(f"Pipe edge missing pipe code: {edge_data}")
                case EdgeCategory.BATCH:
                    mermaid_code += f"    {source} {self._tracker_config.branch_edge_style} {target}\n"
                case EdgeCategory.AGGREGATE:
                    mermaid_code += f"    {source} {self._tracker_config.aggregate_edge_style} {target}\n"
                case EdgeCategory.CONDITION:
                    condition_expression = edge_data.get(EdgeAttributeKey.CONDITION_EXPRESSION)
                    if not condition_expression:
                        raise JobHistoryError(f"Condition edge missing condition expression: {edge_data}")
                    edge_tag = nice_edge_tag(condition_expression)
                    mermaid_code += f"    {source} {self._tracker_config.condition_edge_style} {target}\n"
                case EdgeCategory.CHOICE:
                    chosen_pipe_code = edge_data.get(EdgeAttributeKey.CHOSEN_PIPE)
                    if not chosen_pipe_code:
                        raise JobHistoryError(f"No chosen pipe code set for edge {source} --- {target}")
                    edge_tag = nice_edge_tag(chosen_pipe_code)
                    mermaid_code += f"    {source} -- {edge_tag} {self._tracker_config.choice_edge_style} {target}\n"

        url = make_mermaid_url(mermaid_code)
        return mermaid_code, url

    def generate_subgraph_lines(self, graph_tree: GraphTree) -> List[str]:
        subgraph_lines: List[str] = []
        subgraph_class_lines: List[str] = []

        cycle = 0
        for subgraph_name, nodes in graph_tree.nodes_by_subgraph.items():
            node_lines: List[str] = []
            for node in nodes:
                # log.debug(f"generate_subgraph_lines for node '{node}'")
                node_attributes = self.nx_graph.nodes[node]
                if not node_attributes:
                    raise JobHistoryError(f"Node attributes are empty for node '{node}'")
                node_category = NodeCategory(node_attributes[NodeAttributeKey.CATEGORY])
                node_tag = node_attributes[NodeAttributeKey.TAG]
                if not node_tag:
                    raise JobHistoryError(f"Node tag is empty for node '{node}'")
                node_text = node_tag
                if self.is_debug_mode:
                    if node_comment := node_attributes.get(NodeAttributeKey.COMMENT):
                        node_text += f"\n\n{node_comment}"
                    else:
                        node_text += "\n\nNo comment"
                    if node_debug_info := node_attributes.get(NodeAttributeKey.DEBUG_INFO):
                        node_text += f"\n\n{node_debug_info}"
                match node_category:
                    case NodeCategory.SPECIAL:
                        node_lines.append(f'{node}(["{node_text}"])')
                    case NodeCategory.STUFF:
                        node_lines.append(f'{node}["{node_text}"]')
                    case NodeCategory.CONDITION:
                        node_lines.append(f'{node}{{"{node_text}"}}')
                if self._tracker_config.is_include_interactivity:
                    if node_description := node_attributes.get(NodeAttributeKey.DESCRIPTION):
                        if not isinstance(node_description, str):
                            raise JobHistoryError(f"Node description is not a string: {node_description}")
                        node_description = clean_str_for_mermaid_node_title(node_description)
                        node_lines.append(f'click {node} stuff_node_callback "{node_description}"')

            if not node_lines:
                raise JobHistoryError(f"No node lines found for subgraph '{subgraph_name}'")

            if subgraph_name == "root":
                for mermaid_line in node_lines:
                    subgraph_lines.append(_indent_line(mermaid_line, 2))
            else:
                subgraph_lines.append(_indent_line(f'subgraph "{subgraph_name}"', 1))
                subgraph_lines.append(_indent_line("direction LR", 1))
                for mermaid_line in node_lines:
                    subgraph_lines.append(_indent_line(mermaid_line, 2))
                subgraph_lines.append(_indent_line("end", 1))

                class_def = self.sub_graph_class_defs[cycle % len(self.sub_graph_class_defs)]
                subgraph_class_lines.append(f"class {subgraph_name} {class_def.name};")
            cycle += 1

        subgraph_lines.extend(subgraph_class_lines)

        return subgraph_lines
