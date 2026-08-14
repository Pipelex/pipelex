"""Regression test: a dry run of a ``PipeCondition`` must not depend on set iteration order.

``PipeCondition.pipe_dependencies()`` returns a ``set[str]``, and ``_dry_run_controller_pipe``
dry-runs **every** branch into the same working memory under the same ``output_name`` — so the
branch iterated last is the one whose stuff the caller sees as the condition's output. Iterating
the raw set made that "last" a function of string-hash order, which varies per process: the same
bundle dry-run in two processes produced two different graphs, and any consumer diffing graph
specs (the mthds-ui fixture corpus, a static-vs-dry parity check) saw phantom changes.

The loop sorts now. This test pins the property that makes the sort load-bearing: forcing the
dependency set to iterate in either order must produce the same graph.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from pytest_mock import MockerFixture
from typing_extensions import override

from pipelex.pipe_controllers.condition.pipe_condition import PipeCondition
from pipelex.pipeline.dry_run_pipeline import dry_run_pipeline

_CONDITION_DOMAIN = "dry_run_condition_branch_order"
_CONDITION_MTHDS = f"""
domain = "{_CONDITION_DOMAIN}"
description = "Sequence whose second step is a condition over two named branches"
main_pipe = "respond"

[pipe.respond]
type = "PipeSequence"
description = "Classify then route"
inputs = {{ request = "Text" }}
output = "Text"
steps = [
  {{ pipe = "classify", result = "classified" }},
  {{ pipe = "route", result = "response" }},
]

[pipe.classify]
type = "PipeLLM"
description = "Classify the request"
inputs = {{ request = "Text" }}
output = "Text"
prompt = "Classify $request"

[pipe.route]
type = "PipeCondition"
description = "Route to one of two branches"
inputs = {{ classified = "Text" }}
output = "Text"
expression = "classified"
outcomes = {{ alpha = "alpha_branch", beta = "beta_branch" }}
default_outcome = "alpha_branch"

[pipe.alpha_branch]
type = "PipeSequence"
description = "Alpha branch, whose tail step names its own result"
inputs = {{ classified = "Text" }}
output = "Text"
steps = [
  {{ pipe = "write_alpha", result = "alpha_result" }},
]

[pipe.beta_branch]
type = "PipeSequence"
description = "Beta branch, whose tail step names its own result"
inputs = {{ classified = "Text" }}
output = "Text"
steps = [
  {{ pipe = "write_beta", result = "beta_result" }},
]

[pipe.write_alpha]
type = "PipeLLM"
description = "Alpha branch body"
inputs = {{ classified = "Text" }}
output = "Text"
prompt = "Alpha $classified"

[pipe.write_beta]
type = "PipeLLM"
description = "Beta branch body"
inputs = {{ classified = "Text" }}
output = "Text"
prompt = "Beta $classified"
"""


class _OrderedDependencySet(set[str]):
    """A dependency set that iterates in a caller-chosen order.

    Subclasses ``set`` so every other ``pipe_dependencies()`` call site — membership,
    emptiness, set arithmetic — keeps behaving exactly as before; only ``__iter__`` is
    pinned, which is the single thing the dry-run loop is being tested against.
    """

    def __init__(self, *, values: list[str]) -> None:
        super().__init__(values)
        self._ordered = values

    @override
    def __iter__(self) -> Iterator[str]:
        return iter(self._ordered)


@pytest.mark.asyncio(loop_scope="class")
class TestDryRunConditionBranchOrder:
    async def _graph_output_names(self, *, mocker: MockerFixture, order: list[str]) -> dict[str, list[str]]:
        def ordered_dependencies(condition: Any) -> set[str]:  # noqa: ARG001 — bound as a method, so it takes self
            return _OrderedDependencySet(values=order)

        mocker.patch.object(PipeCondition, "pipe_dependencies", ordered_dependencies)
        graph_spec, _ = await dry_run_pipeline(mthds_contents=[_CONDITION_MTHDS])
        return {node.pipe_code: [output.name for output in node.node_io.outputs] for node in graph_spec.nodes if node.pipe_code}

    async def test_branch_iteration_order_does_not_change_the_graph(self, mocker: MockerFixture) -> None:
        """Both iteration orders must yield the same graph — that is what sorting buys."""
        forward = await self._graph_output_names(mocker=mocker, order=["alpha_branch", "beta_branch"])
        reverse = await self._graph_output_names(mocker=mocker, order=["beta_branch", "alpha_branch"])

        assert forward == reverse
        # Pin the value too, not just the agreement: the sorted loop ends on the branch whose
        # pipe code sorts last, so the enclosing sequence's output is always beta's stuff.
        # Without the sort these two runs disagree — alpha_result one way, beta_result the other.
        assert forward["respond"] == ["beta_result"]
