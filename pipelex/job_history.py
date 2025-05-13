# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportMissingTypeArgument=false
from enum import StrEnum
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx
import yaml
from pydantic import BaseModel

from pipelex import log, pretty_print
from pipelex.config import get_config
from pipelex.core.concept import Concept
from pipelex.core.stuff import Stuff
from pipelex.exceptions import JobHistoryError
from pipelex.pipe_controllers.pipe_condition_details import PipeConditionDetails
from pipelex.tools.misc.mermaid_helpers import clean_str_for_mermaid_node_title, make_mermaid_url
from pipelex.tools.utils.string_utils import snake_to_capitalize_first_letter


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


def nice_edge_tag(edge_tag: str) -> str:
    return f'"{snake_to_capitalize_first_letter(edge_tag)}"'


def _indent_line(line: str, indent: int) -> str:
    return f"{'    ' * indent}{line}"


class JobHistory:
    def __init__(self):
        self.is_active: bool = False
        self.nx_graph: nx.DiGraph = nx.DiGraph()
        self.start_node: Optional[str] = None
        self.sub_graph_class_defs: List[SubGraphClassDef] = []

    def activate(self):
        self.is_active = True

        history_graph_config = get_config().pipelex.history_graph_config
        for sub_graph_index, sub_graph_color in enumerate(history_graph_config.sub_graph_colors):
            class_def_letter = chr(ord("a") + sub_graph_index)
            class_def_name = f"sub_{class_def_letter}"
            self.sub_graph_class_defs.append(SubGraphClassDef(name=class_def_name, color=sub_graph_color))

    def reset(self):
        self.is_active = False
        self.nx_graph = nx.DiGraph()
        self.start_node = None
        self.sub_graph_class_defs = []

    @property
    def _is_debug_mode(self) -> bool:
        return get_config().pipelex.history_graph_config.is_debug_mode

    def _get_node_name(self, node: str) -> Optional[str]:
        node_attributes = self.nx_graph.nodes[node]
        node_name = node_attributes[NodeAttributeKey.NAME]
        if isinstance(node_name, str):
            return node_name
        else:
            raise JobHistoryError(f"Node name is not a string: {node_name}")

    def _pipe_stack_to_subgraph_name(self, pipe_stack: List[str]) -> str:
        return "-".join(pipe_stack)

    def _add_start_node(self) -> str:
        node = SpecialNodeName.START
        node_attributes: Dict[str, Any] = {
            NodeAttributeKey.CATEGORY: NodeCategory.SPECIAL,
            NodeAttributeKey.TAG: "Start",
            NodeAttributeKey.NAME: "Start",
        }
        self.nx_graph.add_node(node, **node_attributes)
        return node

    def _make_stuff_node_tag(
        self,
        stuff: Stuff,
        as_item_index: Optional[int] = None,
    ) -> str:
        concept_code = stuff.concept_code
        concept_display = Concept.sentence_from_concept_code(concept_code=concept_code)
        log.debug(f"Concept display: {concept_code} -> {concept_display}")
        if stuff.is_list:
            concept_display = f"List of [{concept_display}]"
        if as_item_index is not None:
            return f"**{concept_display}** #{as_item_index + 1}"
        else:
            name = stuff.stuff_name
            if not name:
                raise JobHistoryError(f"Stuff name is empty for stuff {stuff}")
            return f"{name}:<br>**{concept_display}**"

    def _add_stuff_node(
        self,
        stuff: Stuff,
        pipe_stack: List[str],
        comment: str,
        as_item_index: Optional[int] = None,
    ) -> str:
        node = stuff.stuff_code
        is_existing = self.nx_graph.has_node(node)
        if is_existing:
            if self._is_debug_mode:
                existing_comment = self.nx_graph.nodes[node][NodeAttributeKey.COMMENT]
                comment = f"{existing_comment}<br/>+ {comment}"
                self.nx_graph.nodes[node][NodeAttributeKey.COMMENT] = comment
            return node

        stuff_content_rendered = stuff.content.rendered_plain()[:250]
        stuff_content_type = type(stuff.content).__name__
        stuff_description = f"{stuff_content_type}"
        stuff_description += f"<br/><br/>{stuff_content_rendered}…"

        node_tag = self._make_stuff_node_tag(
            stuff=stuff,
            as_item_index=as_item_index,
        )
        if stuff.is_text and get_config().pipelex.history_graph_config.is_include_text_preview:
            node_tag += f"<br/>{stuff_content_rendered[:100]}"
        pipe_stack_str = self._pipe_stack_to_subgraph_name(pipe_stack)
        node_attributes: Dict[str, Any] = {
            NodeAttributeKey.CATEGORY: NodeCategory.STUFF,
            NodeAttributeKey.TAG: node_tag,
            NodeAttributeKey.NAME: stuff.stuff_name,
            NodeAttributeKey.DESCRIPTION: stuff_description,
            NodeAttributeKey.DEBUG_INFO: stuff.stuff_code,
            NodeAttributeKey.COMMENT: comment,
            NodeAttributeKey.SUBGRAPH: pipe_stack_str,
        }
        self.nx_graph.add_node(node, **node_attributes)
        return node

    def _add_edge(
        self,
        from_node: str,
        to_node: str,
        edge_category: EdgeCategory,
        attributes: Optional[Dict[str, Any]] = None,
    ):
        # Ensure both nodes exist with attributes
        if not self.nx_graph.has_node(from_node):
            raise JobHistoryError(f"Source node '{from_node}' does not exist")
        if not self.nx_graph.has_node(to_node):
            raise JobHistoryError(f"Target node '{to_node}' does not exist")
        if not self.nx_graph.nodes[from_node]:
            raise JobHistoryError(f"Source node '{from_node}' exists but has no attributes")
        if not self.nx_graph.nodes[to_node]:
            raise JobHistoryError(f"Target node '{to_node}' exists but has no attributes")

        edge_attributes: Dict[str, Any] = {
            EdgeAttributeKey.EDGE_CATEGORY: edge_category,
        }
        if attributes:
            edge_attributes.update(attributes)
        self.nx_graph.add_edge(from_node, to_node, **edge_attributes)

    def add_pipe_step(
        self,
        from_stuff: Optional[Stuff],
        to_stuff: Stuff,
        pipe_code: str,
        comment: str,
        pipe_stack: List[str],
        as_item_index: Optional[int] = None,
        is_with_edge: bool = True,
    ):
        if not self.is_active:
            return
        from_node: str
        if from_stuff:
            from_node = self._add_stuff_node(
                stuff=from_stuff,
                as_item_index=as_item_index,
                pipe_stack=pipe_stack,
                comment=comment,
            )
        else:
            from_node = self._add_start_node()
        if self.start_node is None:
            self.start_node = from_node
        to_node = self._add_stuff_node(
            stuff=to_stuff,
            as_item_index=as_item_index,
            pipe_stack=pipe_stack,
            comment=comment,
        )
        edge_caption = pipe_code
        if self._is_debug_mode:
            edge_caption += f" ({comment})"
        edge_attributes: Dict[str, Any] = {
            EdgeAttributeKey.PIPE_CODE: edge_caption,
        }
        if is_with_edge:
            self._add_edge(
                from_node=from_node,
                to_node=to_node,
                edge_category=EdgeCategory.PIPE,
                attributes=edge_attributes,
            )

    def add_batch_step(
        self,
        from_stuff: Optional[Stuff],
        to_stuff: Stuff,
        to_branch_index: int,
        pipe_stack: List[str],
        comment: str,
    ):
        if not self.is_active:
            return
        from_node: str
        if from_stuff:
            from_node = self._add_stuff_node(
                stuff=from_stuff,
                pipe_stack=pipe_stack,
                comment=comment,
            )
        else:
            from_node = self._add_start_node()
        if self.start_node is None:
            self.start_node = from_node
        to_node = self._add_stuff_node(
            stuff=to_stuff,
            as_item_index=to_branch_index,
            pipe_stack=pipe_stack,
            comment=comment,
        )
        self._add_edge(
            from_node=from_node,
            to_node=to_node,
            edge_category=EdgeCategory.BATCH,
        )

    def add_aggregate_step(
        self,
        from_stuff: Stuff,
        to_stuff: Stuff,
        pipe_stack: List[str],
        comment: str,
    ):
        if not self.is_active:
            return
        from_node = self._add_stuff_node(
            stuff=from_stuff,
            pipe_stack=pipe_stack,
            comment=comment,
        )
        to_node = self._add_stuff_node(
            stuff=to_stuff,
            pipe_stack=pipe_stack,
            comment=comment,
        )
        self._add_edge(
            from_node=from_node,
            to_node=to_node,
            edge_category=EdgeCategory.AGGREGATE,
        )

    def _add_condition_node(self, condition: PipeConditionDetails, pipe_stack: List[str]) -> str:
        node = condition.code
        condition_node_tag = f"Condition:<br>**{condition.test_expression}<br>= {condition.evaluated_expression}**"
        pipe_stack_str = self._pipe_stack_to_subgraph_name(pipe_stack)
        node_attributes: Dict[str, Any] = {
            NodeAttributeKey.CATEGORY: NodeCategory.CONDITION,
            NodeAttributeKey.TAG: condition_node_tag,
            NodeAttributeKey.NAME: condition.code,
            NodeAttributeKey.SUBGRAPH: pipe_stack_str,
        }
        self.nx_graph.add_node(node, **node_attributes)
        return node

    def add_condition_step(
        self,
        from_stuff: Stuff,
        to_condition: PipeConditionDetails,
        condition_expression: str,
        pipe_stack: List[str],
        comment: str,
    ):
        if not self.is_active:
            return
        from_node = self._add_stuff_node(
            stuff=from_stuff,
            pipe_stack=pipe_stack,
            comment=comment,
        )
        to_node = self._add_condition_node(condition=to_condition, pipe_stack=pipe_stack)
        edge_attributes: Dict[str, Any] = {
            EdgeAttributeKey.CONDITION_EXPRESSION: condition_expression,
        }
        self._add_edge(
            from_node=from_node,
            to_node=to_node,
            edge_category=EdgeCategory.CONDITION,
            attributes=edge_attributes,
        )

    def add_choice_step(
        self,
        from_condition: PipeConditionDetails,
        to_stuff: Stuff,
        pipe_stack: List[str],
        comment: str,
    ):
        if not self.is_active:
            return
        to_node = self._add_stuff_node(
            stuff=to_stuff,
            pipe_stack=pipe_stack,
            comment=comment,
        )
        edge_attributes: Dict[str, Any] = {
            EdgeAttributeKey.CHOSEN_PIPE: from_condition.chosen_pipe_code,
        }
        self._add_edge(
            from_node=from_condition.code,
            to_node=to_node,
            edge_category=EdgeCategory.CHOICE,
            attributes=edge_attributes,
        )

    def generate_mermaid_flowchart(self, title: Optional[str] = None, subtitle: Optional[str] = None) -> Tuple[str, str]:
        if not self.is_active:
            raise JobHistoryError("Job history is not active")
        log.debug("Generating mermaid flowchart for the whole graph")
        mermaid_settings: Dict[str, Any] = {}
        if title:
            mermaid_settings["title"] = title
        history_graph_config = get_config().pipelex.history_graph_config
        mermaid_settings["config"] = {}
        if history_graph_config.applied_theme:
            mermaid_settings["config"]["theme"] = history_graph_config.applied_theme
        if history_graph_config.applied_layout:
            mermaid_settings["config"]["layout"] = history_graph_config.applied_layout
        if history_graph_config.applied_wrapping_width:
            mermaid_settings["config"]["flowchart"] = {"wrappingWidth": history_graph_config.applied_wrapping_width}
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
            node_pipe_stack = node_attributes.get(NodeAttributeKey.SUBGRAPH)
            if not node_pipe_stack:
                node_pipe_stack = "Unknown"
            elif not isinstance(node_pipe_stack, str):
                raise JobHistoryError(f"Node '{node}' has no pipe stack: {node_attributes}")

            sub_graph = node_pipe_stack or "root"
            # Split sub_graph by "-" and keep the last token
            if "-" in sub_graph:
                sub_graph = sub_graph.split("-")[-1]
            if sub_graph not in graph_tree.nodes_by_subgraph:
                graph_tree.nodes_by_subgraph[sub_graph] = []
            graph_tree.nodes_by_subgraph[sub_graph].append(node)

        # pretty_print(graph_tree, title="Graph tree")

        subgraph_lines = self.generate_subgraph_lines(graph_tree)
        mermaid_code += "\n".join(subgraph_lines)
        mermaid_code += "\n"

        # Generate subtitle
        if subtitle:
            # this is a hack to add something that looks like a subtitle, but it's actually a node with no stroke and no visible link
            if self.start_node is None:
                raise JobHistoryError("Start node is not set")
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
                        mermaid_code += f"    {source} -- {edge_tag} {history_graph_config.pipe_edge_style} {target}\n"
                    else:
                        raise JobHistoryError(f"Pipe edge missing pipe code: {edge_data}")
                case EdgeCategory.BATCH:
                    mermaid_code += f"    {source} {history_graph_config.branch_edge_style} {target}\n"
                case EdgeCategory.AGGREGATE:
                    mermaid_code += f"    {source} {history_graph_config.aggregate_edge_style} {target}\n"
                case EdgeCategory.CONDITION:
                    condition_expression = edge_data.get(EdgeAttributeKey.CONDITION_EXPRESSION)
                    if not condition_expression:
                        raise JobHistoryError(f"Condition edge missing condition expression: {edge_data}")
                    edge_tag = nice_edge_tag(condition_expression)
                    mermaid_code += f"    {source} {history_graph_config.condition_edge_style} {target}\n"
                case EdgeCategory.CHOICE:
                    chosen_pipe_code = edge_data.get(EdgeAttributeKey.CHOSEN_PIPE)
                    if not chosen_pipe_code:
                        raise JobHistoryError(f"No chosen pipe code set for edge {source} --- {target}")
                    edge_tag = nice_edge_tag(chosen_pipe_code)
                    mermaid_code += f"    {source} -- {edge_tag} {history_graph_config.choice_edge_style} {target}\n"

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
                if self._is_debug_mode:
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
                if get_config().pipelex.history_graph_config.is_include_interactivity:
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

    def print_mermaid_flowchart_and_reset(self, title: Optional[str] = None, subtitle: Optional[str] = None):
        if not self.is_active:
            return
        mermaid_code, url = self.generate_mermaid_flowchart(title=title, subtitle=subtitle)
        print(mermaid_code)
        pretty_print("⚠️  Warning: By clicking on the following mermaid flowchart URL, you send data to https://mermaid.live/.", border_style="red")
        pretty_print(url, title=f"Mermaid flowchart URL for {title}", border_style="yellow")
        self.reset()

    def print_mermaid_flowchart_url(self, title: Optional[str] = None, subtitle: Optional[str] = None):
        if not self.is_active:
            return
        _, url = self.generate_mermaid_flowchart(title=title, subtitle=subtitle)
        pretty_print("⚠️  Warning: By clicking on the following mermaid flowchart URL, you send data to https://mermaid.live/.", border_style="red")
        pretty_print(url, title=f"Mermaid flowchart URL for {title}", border_style="yellow")
        self.reset()


job_history = JobHistory()
