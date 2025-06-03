# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportMissingTypeArgument=false
from typing import Any, Dict, List, Optional

import networkx as nx
from typing_extensions import override

from pipelex import log
from pipelex.core.concept import Concept
from pipelex.core.stuff import Stuff
from pipelex.exceptions import JobHistoryError
from pipelex.pipe_controllers.pipe_condition_details import PipeConditionDetails
from pipelex.pipeline.track.flow_chart import PipelineFlowChart
from pipelex.pipeline.track.pipeline_tracker_protocol import PipelineTrackerProtocol
from pipelex.pipeline.track.tracker_config import TrackerConfig
from pipelex.pipeline.track.tracker_models import (
    EdgeAttributeKey,
    EdgeCategory,
    NodeAttributeKey,
    NodeCategory,
    SpecialNodeName,
)
from pipelex.tools.misc.mermaid_utils import print_mermaid_url


# TODO: manage a separate graph for each pipeline_run_id
# TODO: restore disabled tracking functionality in PipeBatch
class PipelineTracker(PipelineTrackerProtocol):
    def __init__(self, tracker_config: TrackerConfig):
        self._tracker_config = tracker_config
        self._is_debug_mode = tracker_config.is_debug_mode
        self.is_active: bool = False
        self.nx_graph: nx.DiGraph = nx.DiGraph()
        self.start_node: Optional[str] = None

    @override
    def setup(self):
        self.is_active = True

    @override
    def teardown(self):
        self.is_active = False
        self.nx_graph = nx.DiGraph()
        self.start_node = None

    def _get_node_name(self, node: str) -> Optional[str]:
        node_attributes = self.nx_graph.nodes[node]
        node_name = node_attributes[NodeAttributeKey.NAME]
        if isinstance(node_name, str):
            return node_name
        else:
            raise JobHistoryError(f"Node name is not a string: {node_name}")

    def _pipe_layer_to_subgraph_name(self, pipe_layer: List[str]) -> str:
        return "-".join(pipe_layer)

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
        pipe_layer: List[str],
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
        if stuff.is_text and self._tracker_config.is_include_text_preview:
            node_tag += f"<br/>{stuff_content_rendered[:100]}"
        pipe_layer_str = self._pipe_layer_to_subgraph_name(pipe_layer)
        node_attributes: Dict[str, Any] = {
            NodeAttributeKey.CATEGORY: NodeCategory.STUFF,
            NodeAttributeKey.TAG: node_tag,
            NodeAttributeKey.NAME: stuff.stuff_name,
            NodeAttributeKey.DESCRIPTION: stuff_description,
            NodeAttributeKey.DEBUG_INFO: stuff.stuff_code,
            NodeAttributeKey.COMMENT: comment,
            NodeAttributeKey.SUBGRAPH: pipe_layer_str,
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

    @override
    def add_pipe_step(
        self,
        from_stuff: Optional[Stuff],
        to_stuff: Stuff,
        pipe_code: str,
        comment: str,
        pipe_layer: List[str],
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
                pipe_layer=pipe_layer,
                comment=comment,
            )
        else:
            from_node = self._add_start_node()
        if self.start_node is None:
            self.start_node = from_node
        to_node = self._add_stuff_node(
            stuff=to_stuff,
            as_item_index=as_item_index,
            pipe_layer=pipe_layer,
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

    @override
    def add_batch_step(
        self,
        from_stuff: Optional[Stuff],
        to_stuff: Stuff,
        to_branch_index: int,
        pipe_layer: List[str],
        comment: str,
    ):
        if not self.is_active:
            return
        from_node: str
        if from_stuff:
            from_node = self._add_stuff_node(
                stuff=from_stuff,
                pipe_layer=pipe_layer,
                comment=comment,
            )
        else:
            from_node = self._add_start_node()
        if self.start_node is None:
            self.start_node = from_node
        to_node = self._add_stuff_node(
            stuff=to_stuff,
            as_item_index=to_branch_index,
            pipe_layer=pipe_layer,
            comment=comment,
        )
        self._add_edge(
            from_node=from_node,
            to_node=to_node,
            edge_category=EdgeCategory.BATCH,
        )

    @override
    def add_aggregate_step(
        self,
        from_stuff: Stuff,
        to_stuff: Stuff,
        pipe_layer: List[str],
        comment: str,
    ):
        if not self.is_active:
            return
        from_node = self._add_stuff_node(
            stuff=from_stuff,
            pipe_layer=pipe_layer,
            comment=comment,
        )
        to_node = self._add_stuff_node(
            stuff=to_stuff,
            pipe_layer=pipe_layer,
            comment=comment,
        )
        self._add_edge(
            from_node=from_node,
            to_node=to_node,
            edge_category=EdgeCategory.AGGREGATE,
        )

    def _add_condition_node(self, condition: PipeConditionDetails, pipe_layer: List[str]) -> str:
        node = condition.code
        condition_node_tag = f"Condition:<br>**{condition.test_expression}<br>= {condition.evaluated_expression}**"
        pipe_layer_str = self._pipe_layer_to_subgraph_name(pipe_layer)
        node_attributes: Dict[str, Any] = {
            NodeAttributeKey.CATEGORY: NodeCategory.CONDITION,
            NodeAttributeKey.TAG: condition_node_tag,
            NodeAttributeKey.NAME: condition.code,
            NodeAttributeKey.SUBGRAPH: pipe_layer_str,
        }
        self.nx_graph.add_node(node, **node_attributes)
        return node

    @override
    def add_condition_step(
        self,
        from_stuff: Stuff,
        to_condition: PipeConditionDetails,
        condition_expression: str,
        pipe_layer: List[str],
        comment: str,
    ):
        if not self.is_active:
            return
        from_node = self._add_stuff_node(
            stuff=from_stuff,
            pipe_layer=pipe_layer,
            comment=comment,
        )
        to_node = self._add_condition_node(condition=to_condition, pipe_layer=pipe_layer)
        edge_attributes: Dict[str, Any] = {
            EdgeAttributeKey.CONDITION_EXPRESSION: condition_expression,
        }
        self._add_edge(
            from_node=from_node,
            to_node=to_node,
            edge_category=EdgeCategory.CONDITION,
            attributes=edge_attributes,
        )

    @override
    def add_choice_step(
        self,
        from_condition: PipeConditionDetails,
        to_stuff: Stuff,
        pipe_layer: List[str],
        comment: str,
    ):
        if not self.is_active:
            return
        to_node = self._add_stuff_node(
            stuff=to_stuff,
            pipe_layer=pipe_layer,
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

    def _print_mermaid_flowchart_code_and_url(self, title: Optional[str] = None, subtitle: Optional[str] = None):
        if not self.nx_graph.nodes:
            log.info("No nodes in the pipeline tracker")
            return
        if self.start_node is None:
            raise JobHistoryError("Start node is not set")
        flowchart = PipelineFlowChart(nx_graph=self.nx_graph, start_node=self.start_node, tracker_config=self._tracker_config)
        mermaid_code, url = flowchart.generate_mermaid_flowchart(title=title, subtitle=subtitle)
        print(mermaid_code)
        title_to_print = "Mermaid flowchart URL"
        if title:
            title_to_print += f" for {title}"
        print_mermaid_url(url=url, title=title_to_print)

    def _print_mermaid_flowchart_url(self, title: Optional[str] = None, subtitle: Optional[str] = None):
        if not self.nx_graph.nodes:
            log.info("No nodes in the pipeline tracker")
            return
        if self.start_node is None:
            raise JobHistoryError("Start node is not set")
        flowchart = PipelineFlowChart(nx_graph=self.nx_graph, start_node=self.start_node, tracker_config=self._tracker_config)
        _, url = flowchart.generate_mermaid_flowchart(title=title, subtitle=subtitle)
        title_to_print = "Mermaid flowchart URL"
        if title:
            title_to_print += f" for {title}"
        print_mermaid_url(url=url, title=title_to_print)

    @override
    def output_flowchart(
        self,
        title: Optional[str] = None,
        subtitle: Optional[str] = None,
        is_detailed: bool = False,
    ):
        if is_detailed:
            self._print_mermaid_flowchart_code_and_url(title=title, subtitle=subtitle)
        else:
            self._print_mermaid_flowchart_url(title=title, subtitle=subtitle)
