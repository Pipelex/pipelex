# ruff: noqa: INP001
r"""Tier-2d submitter: dispatch the dry-run+validation job as ONE Temporal activity.

Dispatches the one-step wrapper workflow ``WfDryValidate`` (which runs the single
``act_dry_validate`` activity fully in-process on a worker) and awaits the
``{status map, GraphSpec}`` result in one round-trip — the Temporal-enabled ``/validate``
dispatch shape. Prints the per-pipe status map and writes the GraphSpec JSON when produced.

Usage (with the Temporal server + split workers up — see mode-2-setup.md):

    .venv/bin/python .claude/skills/temporal-e2e-validate/scripts/submit_dry_validate.py \\
        --bundle tests/integration/pipelex/temporal/library_crate/temporal_parallel.mthds \\
        --pipe temporal_parallel_test.temporal_parallel_sequence

Exit codes: 0 = validation succeeded (graph may still be None — best-effort); 1 = validation
failed (the structured ErrorReport is printed).
"""

import argparse
import asyncio
import sys
from pathlib import Path

from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.error_handlers import ErrorContext
from pipelex.pipelex import Pipelex
from pipelex.temporal.exceptions import WorkflowExecutionError
from pipelex.temporal.tprl_pipe.act_dry_validate import DryValidateArg
from pipelex.temporal.tprl_pipe.dry_validate_dispatch import dispatch_dry_validate

DEFAULT_BUNDLE = "tests/integration/pipelex/temporal/library_crate/temporal_parallel.mthds"
DEFAULT_PIPE = "temporal_parallel_test.temporal_parallel_sequence"
DEFAULT_GRAPH_OUT = "/tmp/tier2d-graph-spec.json"  # noqa: S108


async def submit(bundle: str, pipe_code: str | None, allow_signatures: bool, graph_out: str) -> int:
    bundle_content = Path(bundle).expanduser().read_text(encoding="utf-8")
    arg = DryValidateArg(
        mthds_contents=[bundle_content],
        allow_signatures=allow_signatures,
        pipe_code=pipe_code,
    )
    print(f"Dispatching wf_dry_validate for bundle='{bundle}' pipe_code={pipe_code!r} allow_signatures={allow_signatures}")
    try:
        result = await dispatch_dry_validate(arg)
    except WorkflowExecutionError as exc:
        print("VALIDATION FAILED — structured ErrorReport recovered from the workflow failure:")
        print(f"  error_type:   {exc.error_report.error_type if exc.error_report else 'n/a'}")
        print(f"  error_domain: {exc.error_report.error_domain if exc.error_report else 'n/a'}")
        print(f"  message:      {exc.message}")
        return 1

    print(f"STATUS MAP ({len(result.dry_run_outputs)} pipes):")
    for pipe_ref, output in sorted(result.dry_run_outputs.items()):
        suffix = f" — {output.error_message}" if output.error_message else ""
        print(f"  {output.status:<8} {pipe_ref}{suffix}")

    if result.graph_spec is None:
        print("GRAPH: None (best-effort — validation still succeeded)")
    else:
        print(f"GRAPH: graph_id={result.graph_spec.graph_id} nodes={len(result.graph_spec.nodes)} edges={len(result.graph_spec.edges)}")
        graph_path = Path(graph_out).expanduser()
        try:
            graph_path.parent.mkdir(parents=True, exist_ok=True)
            graph_path.write_text(result.graph_spec.model_dump_json(indent=2), encoding="utf-8")
        except OSError as exc:
            # The graph file is a best-effort artifact: an IO failure must not be reported as a validation failure (exit 1)
            print(f"GRAPH JSON write to {graph_path} failed: {exc}")
        else:
            print(f"GRAPH JSON written to {graph_path}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", default=DEFAULT_BUNDLE)
    parser.add_argument("--pipe", default=DEFAULT_PIPE, dest="pipe_code")
    parser.add_argument("--no-pipe", action="store_true", help="Do not pass a pipe_code (use the bundle's main_pipe, if any)")
    parser.add_argument("--allow-signatures", action="store_true")
    parser.add_argument("--graph-out", default=DEFAULT_GRAPH_OUT)
    args = parser.parse_args()

    pipe_code: str | None = None if args.no_pipe else args.pipe_code
    make_pipelex_for_cli(context=ErrorContext.VALIDATION_BEFORE_PIPE_RUN, library_dirs=None, temporal_enabled=True)
    try:
        exit_code = asyncio.run(submit(bundle=args.bundle, pipe_code=pipe_code, allow_signatures=args.allow_signatures, graph_out=args.graph_out))
    finally:
        Pipelex.teardown_if_needed()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
