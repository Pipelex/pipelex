"""Unit tests for the rewrite that gives every outcome of a dry-run condition the condition's output digest."""

from datetime import UTC, datetime
from typing import ClassVar

import pytest

from pipelex.graph.condition_output_merge import ConditionOutputMerge, ConditionOutputTyping, apply_condition_output_merges
from pipelex.graph.graphspec import EdgeKind, EdgeSpec, GraphSpec, IOSpec, NodeIOSpec, NodeKind, NodeSpec, NodeStatus


def _node(*, node_id: str, kind: NodeKind = NodeKind.OPERATOR, inputs: list[IOSpec] | None = None, outputs: list[IOSpec] | None = None) -> NodeSpec:
    return NodeSpec(
        node_id=node_id,
        kind=kind,
        pipe_code=node_id,
        status=NodeStatus.SUCCEEDED,
        node_io=NodeIOSpec(inputs=inputs or [], outputs=outputs or []),
    )


def _contains(*, source: str, target: str) -> EdgeSpec:
    return EdgeSpec(edge_id=f"contains_{source}_{target}", source=source, target=target, kind=EdgeKind.CONTAINS)


def _outputs_by_node(graph: GraphSpec) -> dict[str, list[IOSpec]]:
    return {node.node_id: node.node_io.outputs for node in graph.nodes}


def _inputs_by_node(graph: GraphSpec) -> dict[str, list[IOSpec]]:
    return {node.node_id: node.node_io.inputs for node in graph.nodes}


class TestApplyConditionOutputMerges:
    CREATED_AT: ClassVar[datetime] = datetime(2026, 10, 5, 12, 0, 0, tzinfo=UTC)

    def _graph(self, *, nodes: list[NodeSpec], edges: list[EdgeSpec]) -> GraphSpec:
        return GraphSpec(graph_id="merge_test", created_at=self.CREATED_AT, nodes=nodes, edges=edges)

    def _report_shape(self) -> GraphSpec:
        """`route` runs `write_questions` then `write_rejection`, whose stuff `assemble` reads."""
        return self._graph(
            nodes=[
                _node(
                    node_id="route",
                    kind=NodeKind.CONTROLLER,
                    inputs=[IOSpec(name="verdict", concept="Text", digest="d_verdict")],
                    outputs=[IOSpec(name="follow_up", concept="Rejection", digest="d_rejection")],
                ),
                _node(node_id="write_questions", outputs=[IOSpec(name="follow_up", concept="Question", multiplicity=True, digest="d_questions")]),
                _node(node_id="write_rejection", outputs=[IOSpec(name="follow_up", concept="Rejection", digest="d_rejection")]),
                _node(
                    node_id="assemble",
                    inputs=[
                        IOSpec(name="verdict", concept="Text", digest="d_verdict"),
                        # A reader records the stuff it received, which in a dry run is the last outcome's.
                        IOSpec(name="follow_up", concept="Rejection", digest="d_rejection"),
                    ],
                    outputs=[IOSpec(name="result", concept="Text", digest="d_result")],
                ),
            ],
            edges=[
                _contains(source="route", target="write_questions"),
                _contains(source="route", target="write_rejection"),
                EdgeSpec(edge_id="data_route_assemble", source="route", target="assemble", kind=EdgeKind.DATA, label="follow_up"),
            ],
        )

    def test_no_merge_leaves_the_graph_alone(self) -> None:
        graph = self._report_shape()
        assert apply_condition_output_merges(graph=graph, merges=[]) == graph

    def test_every_outcome_takes_the_shared_digest(self) -> None:
        graph = self._report_shape()
        merge = ConditionOutputMerge(condition_node_id="route", shared_digest="d_rejection", merged_digests=["d_questions"])

        merged = apply_condition_output_merges(graph=graph, merges=[merge])

        outputs = _outputs_by_node(merged)
        assert [spec.digest for spec in outputs["write_questions"]] == ["d_rejection"]
        assert [spec.digest for spec in outputs["write_rejection"]] == ["d_rejection"]
        assert [spec.digest for spec in outputs["route"]] == ["d_rejection"]
        assert [spec.digest for spec in _inputs_by_node(merged)["assemble"]] == ["d_verdict", "d_rejection"]
        # Each outcome keeps what it writes: only the digest moves.
        assert outputs["write_questions"][0].concept == "Question"
        assert outputs["write_questions"][0].multiplicity is True
        # Without a typing, the condition's own item is untouched.
        assert outputs["route"][0].concept == "Rejection"

    def test_a_typing_retypes_the_condition_and_its_reader_not_the_outcomes(self) -> None:
        graph = self._report_shape()
        merge = ConditionOutputMerge(
            condition_node_id="route",
            shared_digest="d_rejection",
            merged_digests=["d_questions"],
            shared_typing=ConditionOutputTyping(concept="Anything", multiplicity=None),
        )

        merged = apply_condition_output_merges(graph=graph, merges=[merge])

        outputs = _outputs_by_node(merged)
        assert outputs["route"][0].concept == "Anything"
        assert outputs["route"][0].multiplicity is None
        assert outputs["write_questions"][0].concept == "Question"
        assert outputs["write_questions"][0].multiplicity is True
        assert outputs["write_rejection"][0].concept == "Rejection"
        assert _inputs_by_node(merged)["assemble"][1].concept == "Anything"
        # Items on other stuffs are untouched.
        assert _inputs_by_node(merged)["assemble"][0].concept == "Text"
        assert _inputs_by_node(merged)["route"][0].concept == "Text"
        assert outputs["assemble"][0].concept == "Text"

    def test_a_typing_types_a_list(self) -> None:
        graph = self._report_shape()
        merge = ConditionOutputMerge(
            condition_node_id="route",
            shared_digest="d_rejection",
            merged_digests=["d_questions"],
            shared_typing=ConditionOutputTyping(concept="Question", multiplicity=True),
        )

        merged = apply_condition_output_merges(graph=graph, merges=[merge])

        route_output = _outputs_by_node(merged)["route"][0]
        assert route_output.concept_label == "Question[]"

    @pytest.mark.parametrize("inner_first", [True, False])
    def test_a_nested_condition_lands_on_the_outer_digest(self, *, inner_first: bool) -> None:
        """`outer` runs `inner` then `fallback`; `inner` runs `x` then `y`. Every one ends on `fallback`'s digest."""
        graph = self._graph(
            nodes=[
                _node(node_id="outer", kind=NodeKind.CONTROLLER, outputs=[IOSpec(name="slot", digest="d_fallback")]),
                _node(node_id="inner", kind=NodeKind.CONTROLLER, outputs=[IOSpec(name="slot", digest="d_y")]),
                _node(node_id="x", outputs=[IOSpec(name="slot", digest="d_x")]),
                _node(node_id="y", outputs=[IOSpec(name="slot", digest="d_y")]),
                _node(node_id="fallback", outputs=[IOSpec(name="slot", digest="d_fallback")]),
            ],
            edges=[
                _contains(source="outer", target="inner"),
                _contains(source="outer", target="fallback"),
                _contains(source="inner", target="x"),
                _contains(source="inner", target="y"),
            ],
        )
        inner_merge = ConditionOutputMerge(condition_node_id="inner", shared_digest="d_y", merged_digests=["d_x"])
        outer_merge = ConditionOutputMerge(condition_node_id="outer", shared_digest="d_fallback", merged_digests=["d_y"])
        merges = [inner_merge, outer_merge] if inner_first else [outer_merge, inner_merge]

        merged = apply_condition_output_merges(graph=graph, merges=merges)

        assert {node_id: [spec.digest for spec in specs] for node_id, specs in _outputs_by_node(merged).items()} == {
            "outer": ["d_fallback"],
            "inner": ["d_fallback"],
            "x": ["d_fallback"],
            "y": ["d_fallback"],
            "fallback": ["d_fallback"],
        }

    def test_a_sequence_ending_on_the_condition_takes_the_typing(self) -> None:
        """`screen` runs `judge` then `route`, so `screen`'s output is `route`'s, the last outcome's stuff."""
        graph = self._graph(
            nodes=[
                _node(node_id="screen", kind=NodeKind.CONTROLLER, outputs=[IOSpec(name="decision", concept="Email", digest="d_email")]),
                _node(node_id="judge", outputs=[IOSpec(name="verdict", concept="Text", digest="d_verdict")]),
                _node(
                    node_id="route",
                    kind=NodeKind.CONTROLLER,
                    inputs=[IOSpec(name="verdict", concept="Text", digest="d_verdict")],
                    outputs=[IOSpec(name="decision", concept="Email", digest="d_email")],
                ),
                _node(node_id="write_questions", outputs=[IOSpec(name="decision", concept="Question", multiplicity=True, digest="d_questions")]),
                _node(node_id="write_email", outputs=[IOSpec(name="decision", concept="Email", digest="d_email")]),
            ],
            edges=[
                _contains(source="screen", target="judge"),
                _contains(source="screen", target="route"),
                _contains(source="route", target="write_questions"),
                _contains(source="route", target="write_email"),
            ],
        )
        merge = ConditionOutputMerge(
            condition_node_id="route",
            shared_digest="d_email",
            merged_digests=["d_questions"],
            shared_typing=ConditionOutputTyping(concept="Anything"),
        )

        merged = apply_condition_output_merges(graph=graph, merges=[merge])

        outputs = _outputs_by_node(merged)
        assert [(spec.digest, spec.concept, spec.multiplicity) for spec in outputs["screen"]] == [("d_email", "Anything", None)]
        assert [(spec.digest, spec.concept, spec.multiplicity) for spec in outputs["route"]] == [("d_email", "Anything", None)]
        assert [(spec.digest, spec.concept, spec.multiplicity) for spec in outputs["write_questions"]] == [("d_email", "Question", True)]
        assert [(spec.digest, spec.concept, spec.multiplicity) for spec in outputs["write_email"]] == [("d_email", "Email", None)]
        assert outputs["judge"][0].concept == "Text"

    def test_each_batch_branch_sequence_takes_its_own_condition_typing(self) -> None:
        """`screen_each` runs the sequence `screen_one` per item, each ending on its own run of `route`."""
        nodes = [
            _node(
                node_id="screen_each", kind=NodeKind.CONTROLLER, outputs=[IOSpec(name="results", concept="Text", multiplicity=True, digest="d_list")]
            )
        ]
        edges: list[EdgeSpec] = []
        merges: list[ConditionOutputMerge] = []
        for index in (0, 1):
            branch_digest = f"d_branch_{index}"
            nodes += [
                _node(node_id=f"screen_one_{index}", kind=NodeKind.CONTROLLER, outputs=[IOSpec(name="output", concept="Text", digest=branch_digest)]),
                _node(node_id=f"route_{index}", kind=NodeKind.CONTROLLER, outputs=[IOSpec(name="output", concept="Text", digest=branch_digest)]),
                _node(
                    node_id=f"write_questions_{index}",
                    outputs=[IOSpec(name="output", concept="Question", multiplicity=True, digest=f"d_questions_{index}")],
                ),
                _node(node_id=f"write_refusal_{index}", outputs=[IOSpec(name="output", concept="Text", digest=branch_digest)]),
            ]
            edges += [
                _contains(source="screen_each", target=f"screen_one_{index}"),
                _contains(source=f"screen_one_{index}", target=f"route_{index}"),
                _contains(source=f"route_{index}", target=f"write_questions_{index}"),
                _contains(source=f"route_{index}", target=f"write_refusal_{index}"),
                EdgeSpec(
                    edge_id=f"aggregate_{index}",
                    source=f"screen_one_{index}",
                    target="screen_each",
                    kind=EdgeKind.BATCH_AGGREGATE,
                    source_stuff_digest=branch_digest,
                    target_stuff_digest="d_list",
                ),
            ]
            merges.append(
                ConditionOutputMerge(
                    condition_node_id=f"route_{index}",
                    shared_digest=branch_digest,
                    merged_digests=[f"d_questions_{index}"],
                    shared_typing=ConditionOutputTyping(concept=f"Declared{index}"),
                )
            )

        merged = apply_condition_output_merges(graph=self._graph(nodes=nodes, edges=edges), merges=merges)

        outputs = _outputs_by_node(merged)
        for index in (0, 1):
            assert [(spec.digest, spec.concept) for spec in outputs[f"screen_one_{index}"]] == [(f"d_branch_{index}", f"Declared{index}")]
            assert [(spec.digest, spec.concept) for spec in outputs[f"route_{index}"]] == [(f"d_branch_{index}", f"Declared{index}")]
            assert [(spec.digest, spec.concept) for spec in outputs[f"write_questions_{index}"]] == [(f"d_branch_{index}", "Question")]
            assert [(spec.digest, spec.concept) for spec in outputs[f"write_refusal_{index}"]] == [(f"d_branch_{index}", "Text")]
        # The batch's aggregate is another stuff, which keeps its own typing.
        assert [(spec.digest, spec.concept, spec.multiplicity) for spec in outputs["screen_each"]] == [("d_list", "Text", True)]

    def test_an_outcome_sequence_keeps_the_outcome_typing(self) -> None:
        """`questions_flow` is an outcome: it and its last step write the slot, inside the condition's outcomes."""
        graph = self._graph(
            nodes=[
                _node(node_id="route", kind=NodeKind.CONTROLLER, outputs=[IOSpec(name="follow_up", concept="Rejection", digest="d_rejection")]),
                _node(
                    node_id="questions_flow",
                    kind=NodeKind.CONTROLLER,
                    outputs=[IOSpec(name="follow_up", concept="Question", multiplicity=True, digest="d_questions")],
                ),
                _node(node_id="draft_questions", outputs=[IOSpec(name="draft", concept="Text", digest="d_draft")]),
                _node(
                    node_id="finalize_questions",
                    inputs=[IOSpec(name="draft", concept="Text", digest="d_draft")],
                    outputs=[IOSpec(name="follow_up", concept="Question", multiplicity=True, digest="d_questions")],
                ),
                _node(node_id="write_rejection", outputs=[IOSpec(name="follow_up", concept="Rejection", digest="d_rejection")]),
            ],
            edges=[
                _contains(source="route", target="questions_flow"),
                _contains(source="questions_flow", target="draft_questions"),
                _contains(source="questions_flow", target="finalize_questions"),
                _contains(source="route", target="write_rejection"),
            ],
        )
        merge = ConditionOutputMerge(
            condition_node_id="route",
            shared_digest="d_rejection",
            merged_digests=["d_questions"],
            shared_typing=ConditionOutputTyping(concept="Anything"),
        )

        merged = apply_condition_output_merges(graph=graph, merges=[merge])

        outputs = _outputs_by_node(merged)
        assert [(spec.digest, spec.concept, spec.multiplicity) for spec in outputs["questions_flow"]] == [("d_rejection", "Question", True)]
        assert [(spec.digest, spec.concept, spec.multiplicity) for spec in outputs["finalize_questions"]] == [("d_rejection", "Question", True)]
        assert outputs["route"][0].concept == "Anything"

    def _nested_shape(self) -> GraphSpec:
        """`screen` ends on `outer`, which runs `wrapper` then `fallback`; `wrapper` ends on `inner`, which runs `x` then `y`."""
        return self._graph(
            nodes=[
                _node(node_id="screen", kind=NodeKind.CONTROLLER, outputs=[IOSpec(name="slot", concept="Text", digest="d_fallback")]),
                _node(node_id="outer", kind=NodeKind.CONTROLLER, outputs=[IOSpec(name="slot", concept="Text", digest="d_fallback")]),
                _node(node_id="wrapper", kind=NodeKind.CONTROLLER, outputs=[IOSpec(name="slot", concept="Email", digest="d_y")]),
                _node(node_id="inner", kind=NodeKind.CONTROLLER, outputs=[IOSpec(name="slot", concept="Email", digest="d_y")]),
                _node(node_id="x", outputs=[IOSpec(name="slot", concept="Question", multiplicity=True, digest="d_x")]),
                _node(node_id="y", outputs=[IOSpec(name="slot", concept="Email", digest="d_y")]),
                _node(node_id="fallback", outputs=[IOSpec(name="slot", concept="Text", digest="d_fallback")]),
                _node(node_id="assemble", inputs=[IOSpec(name="slot", concept="Text", digest="d_fallback")]),
            ],
            edges=[
                _contains(source="screen", target="outer"),
                _contains(source="outer", target="wrapper"),
                _contains(source="wrapper", target="inner"),
                _contains(source="inner", target="x"),
                _contains(source="inner", target="y"),
                _contains(source="outer", target="fallback"),
            ],
        )

    def _nested_merges(self, *, outer_typing: ConditionOutputTyping | None) -> list[ConditionOutputMerge]:
        return [
            ConditionOutputMerge(
                condition_node_id="inner",
                shared_digest="d_y",
                merged_digests=["d_x"],
                shared_typing=ConditionOutputTyping(concept="InnerDeclared"),
            ),
            ConditionOutputMerge(condition_node_id="outer", shared_digest="d_fallback", merged_digests=["d_y"], shared_typing=outer_typing),
        ]

    @pytest.mark.parametrize("inner_first", [True, False])
    def test_nested_typings_split_at_the_outer_condition(self, *, inner_first: bool) -> None:
        """What lies between the conditions carries the inner typing; the outer condition and beyond, the outer one."""
        merges = self._nested_merges(outer_typing=ConditionOutputTyping(concept="OuterDeclared"))
        if not inner_first:
            merges.reverse()

        merged = apply_condition_output_merges(graph=self._nested_shape(), merges=merges)

        outputs = _outputs_by_node(merged)
        assert {node_id: [(spec.digest, spec.concept) for spec in specs] for node_id, specs in outputs.items()} == {
            "screen": [("d_fallback", "OuterDeclared")],
            "outer": [("d_fallback", "OuterDeclared")],
            "wrapper": [("d_fallback", "InnerDeclared")],
            "inner": [("d_fallback", "InnerDeclared")],
            "x": [("d_fallback", "Question")],
            "y": [("d_fallback", "Email")],
            # A sibling outcome of the inner condition is the outer condition's outcome, never the inner one's.
            "fallback": [("d_fallback", "Text")],
            "assemble": [],
        }
        assert [(spec.digest, spec.concept) for spec in _inputs_by_node(merged)["assemble"]] == [("d_fallback", "OuterDeclared")]

    def test_an_untyped_outer_condition_lets_the_inner_typing_through(self) -> None:
        merged = apply_condition_output_merges(graph=self._nested_shape(), merges=self._nested_merges(outer_typing=None))

        concepts = {node_id: [spec.concept for spec in specs] for node_id, specs in _outputs_by_node(merged).items()}
        assert concepts["screen"] == ["InnerDeclared"]
        assert concepts["outer"] == ["InnerDeclared"]
        assert concepts["wrapper"] == ["InnerDeclared"]
        assert concepts["inner"] == ["InnerDeclared"]
        assert concepts["fallback"] == ["Text"]
        assert concepts["x"] == ["Question"]
        assert concepts["y"] == ["Email"]
        assert [spec.concept for spec in _inputs_by_node(merged)["assemble"]] == ["InnerDeclared"]

    def test_sibling_typed_conditions_resolve_to_the_first_in_node_order(self) -> None:
        """Two typed conditions as outcomes of an untyped one: everything outside them takes the first one's typing."""
        graph = self._graph(
            nodes=[
                _node(node_id="outer", kind=NodeKind.CONTROLLER, outputs=[IOSpec(name="slot", concept="Text", digest="d_b")]),
                _node(node_id="inner_a", kind=NodeKind.CONTROLLER, outputs=[IOSpec(name="slot", concept="Text", digest="d_a")]),
                _node(node_id="a_1", outputs=[IOSpec(name="slot", concept="Number", digest="d_a1")]),
                _node(node_id="a_2", outputs=[IOSpec(name="slot", concept="Text", digest="d_a")]),
                _node(node_id="inner_b", kind=NodeKind.CONTROLLER, outputs=[IOSpec(name="slot", concept="Text", digest="d_b")]),
                _node(node_id="b_1", outputs=[IOSpec(name="slot", concept="Number", digest="d_b1")]),
                _node(node_id="b_2", outputs=[IOSpec(name="slot", concept="Text", digest="d_b")]),
            ],
            edges=[
                _contains(source="outer", target="inner_a"),
                _contains(source="inner_a", target="a_1"),
                _contains(source="inner_a", target="a_2"),
                _contains(source="outer", target="inner_b"),
                _contains(source="inner_b", target="b_1"),
                _contains(source="inner_b", target="b_2"),
            ],
        )
        merges = [
            ConditionOutputMerge(
                condition_node_id="inner_b", shared_digest="d_b", merged_digests=["d_b1"], shared_typing=ConditionOutputTyping(concept="B")
            ),
            ConditionOutputMerge(
                condition_node_id="inner_a", shared_digest="d_a", merged_digests=["d_a1"], shared_typing=ConditionOutputTyping(concept="A")
            ),
            ConditionOutputMerge(condition_node_id="outer", shared_digest="d_b", merged_digests=["d_a"]),
        ]

        merged = apply_condition_output_merges(graph=graph, merges=merges)

        concepts = {node_id: [spec.concept for spec in specs] for node_id, specs in _outputs_by_node(merged).items()}
        assert concepts["outer"] == ["A"]
        assert concepts["inner_a"] == ["A"]
        assert concepts["inner_b"] == ["B"]
        assert concepts["a_1"] == ["Number"]
        assert concepts["b_2"] == ["Text"]

    def test_stuff_to_stuff_edges_follow_the_merge(self) -> None:
        graph = self._graph(
            nodes=[
                _node(node_id="route", kind=NodeKind.CONTROLLER, outputs=[IOSpec(name="answers", digest="d_default")]),
                _node(node_id="ask_each", kind=NodeKind.CONTROLLER, outputs=[IOSpec(name="answers", multiplicity=True, digest="d_batch")]),
                _node(node_id="ask_one", outputs=[IOSpec(name="answer", digest="d_item_0")]),
                _node(node_id="write_default", outputs=[IOSpec(name="answers", multiplicity=True, digest="d_default")]),
            ],
            edges=[
                EdgeSpec(
                    edge_id="aggregate",
                    source="ask_one",
                    target="ask_each",
                    kind=EdgeKind.BATCH_AGGREGATE,
                    source_stuff_digest="d_item_0",
                    target_stuff_digest="d_batch",
                ),
                EdgeSpec(
                    edge_id="combine",
                    source="ask_one",
                    target="ask_each",
                    kind=EdgeKind.PARALLEL_COMBINE,
                    source_stuff_digest="d_batch",
                    target_stuff_digest="d_other",
                ),
                _contains(source="route", target="ask_each"),
            ],
        )
        merge = ConditionOutputMerge(condition_node_id="route", shared_digest="d_default", merged_digests=["d_batch"])

        merged = apply_condition_output_merges(graph=graph, merges=[merge])

        edges = {edge.edge_id: edge for edge in merged.edges}
        assert (edges["aggregate"].source_stuff_digest, edges["aggregate"].target_stuff_digest) == ("d_item_0", "d_default")
        assert (edges["combine"].source_stuff_digest, edges["combine"].target_stuff_digest) == ("d_default", "d_other")
        assert (edges["contains_route_ask_each"].source_stuff_digest, edges["contains_route_ask_each"].target_stuff_digest) == (None, None)
        assert _outputs_by_node(merged)["ask_one"][0].digest == "d_item_0"
