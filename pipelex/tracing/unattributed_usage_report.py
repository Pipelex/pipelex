"""The report of a run whose graph came out incomplete, to the operator's error trackers.

When the graph assembler meets usage reported by a node the run's trace never started, it counts that usage in the run's
``unattributed`` bucket, logs a warning per node and returns those nodes beside the graph
(``GraphSpecAssembler.assemble_with_never_started_usage``). A start event was lost, so the run's record is incomplete: the
graph shows fewer steps, and a smaller cost under each step, than the run spent. The assembler reports nothing itself.
The tracing assembly of a run whose caller asked for it (``pipelex.pipe_run.tracing_assembly``) hands those nodes here,
for a run that is no dry run, and this reports them once per call, as a handled problem under
``pipelex.run.graph_incomplete``. ``PipeRun`` asks for it as it decides to report a failure: never for a dry run, nor for
the runs a validation makes.

The report names the run, the nodes that never started and what they spent, and carries no content of the run: no
input, output, prompt or pipe of the run, nothing but identifiers and counts. The request id is read by the seam from
the log context the assembly binds.

Usage of a superseded attempt, and usage made outside any pipe context (``UNATTRIBUTED_NODE_ID``), also lands in the
``unattributed`` bucket, but names no node of the run that went missing, so it is not reported: a retried attempt is
left out of the graph on purpose, and fallback usage was never tied to a node at all.

**Reporting never fails the assembly.** With no tracker installed nothing is built. Building the report, the cost
conversion included, is guarded here, and the seam guards calling each tracker: a report that cannot be built is logged
at debug level and dropped, since an error escaping from here would fail the run's tracing assembly.
"""

import math
from collections.abc import Mapping

from pipelex import log
from pipelex.errors.problem import PipelexProblem, ProblemView, make_problem, problem_status_of
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode, RunGraphIncompleteParams
from pipelex.system.error_tracking.error_tracking import has_error_trackers, reaches_error_trackers, report_problem
from pipelex.tools.log.error_fields import error_fields
from pipelex.tracing.usage_attribution import NodeUsages, make_self_contained_spec

# The most node ids one report names; ``node_count`` still says how many there were.
REPORTED_NODE_IDS_LIMIT = 20

_MICRO_USD_PER_USD = 1_000_000


def report_unattributed_usage(*, pipeline_run_id: str, usages_by_never_started_node: Mapping[str, NodeUsages]) -> None:
    """Report to the error trackers, once, that a run's graph left the usage of nodes that never started unattributed.

    Does nothing when no node is given or no tracker is installed. Never raises for a report it cannot build. The caller
    decides whether the run reports at all: a dry run, and the runs a validation makes, never call this.

    Args:
        pipeline_run_id: The run whose graph was assembled.
        usages_by_never_started_node: The usage each node reported, by the id of a node the trace never started.
    """
    if not usages_by_never_started_node or not has_error_trackers():
        return
    try:
        problem = _graph_incomplete_problem(pipeline_run_id=pipeline_run_id, usages_by_never_started_node=usages_by_never_started_node)
        if not reaches_error_trackers(status=problem_status_of(problem=problem), domain=problem.effective_domain):
            return
    except (ValueError, ArithmeticError) as build_error:
        # Building the report sums the nodes' usage, converts its cost and validates the problem, which raise a pydantic
        # ValidationError (a ValueError) or an arithmetic error at worst. Either would fail the run's tracing assembly,
        # so it is dropped here: the report is lost, never the run's graph.
        log.debug("The report of an incomplete graph could not be built", fields=error_fields(exc=build_error))
        return
    report_problem(problem=problem)


def _graph_incomplete_problem(*, pipeline_run_id: str, usages_by_never_started_node: Mapping[str, NodeUsages]) -> PipelexProblem:
    """The ``pipelex.run.graph_incomplete`` problem of a run, in the operator's view.

    Raises:
        ValueError: A pydantic ``ValidationError`` from the usage total, the parameters or the problem.
        ArithmeticError: From the usage total's cost arithmetic.
    """
    usage_spec = make_self_contained_spec([usage for usages in usages_by_never_started_node.values() for usage in usages])
    cost_micro_usd: int | None = None
    if usage_spec.cost is not None:
        # A finite cost can still overflow to infinity once scaled, which `round` refuses, so the scaled value is the
        # one checked.
        scaled_cost = usage_spec.cost * _MICRO_USD_PER_USD
        if math.isfinite(scaled_cost):
            cost_micro_usd = round(scaled_cost)
    params = RunGraphIncompleteParams(
        node_ids=sorted(usages_by_never_started_node)[:REPORTED_NODE_IDS_LIMIT],
        node_count=len(usages_by_never_started_node),
        inference_calls=usage_spec.inference_calls,
        cost_micro_usd=cost_micro_usd,
    )
    return make_problem(
        code=PipelexErrorCode.RUN_GRAPH_INCOMPLETE,
        view=ProblemView.OPERATOR,
        params=params.model_dump(exclude_none=True),
        pipeline_run_id=pipeline_run_id,
    )
