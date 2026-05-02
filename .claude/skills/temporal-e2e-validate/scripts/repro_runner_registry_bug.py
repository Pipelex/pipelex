"""Submitter that mirrors `pipelex run bundle` but attaches a DeliveryAssignment so
`act_deliver` fires on the runner worker. This forces Temporal's data converter on
the runner process to deserialize a hydrated PipeOutput — the path that surfaces
the cross-process dynamic-class registry bug when the bundle defines a dynamic
concept (e.g. Greeting) the runner has never registered.

Equivalent to the cloud / webhook submission path (`start_pipeline` with a
WebhookTarget): the runner must decode the dynamic concept class even though the
crate was only loaded on the router process.

Usage (with both scoped workers up — router + runner on temporal_task_queue):

    .venv/bin/python .claude/skills/temporal-e2e-validate/scripts/repro_runner_registry_bug.py \\
        --bundle tests/integration/pipelex/temporal/library_crate/dynamic_concept_sequence.mthds \\
        --pipe dynamic_greeting_sequence

Defaults reproduce the canonical Greeting case.
"""

import argparse
import asyncio
from pathlib import Path

from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.error_handlers import ErrorContext
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment, StorageTarget
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipelex import Pipelex
from pipelex.pipeline.runner import PipelexRunner

DEFAULT_BUNDLE = "tests/integration/pipelex/temporal/library_crate/dynamic_concept_sequence.mthds"
DEFAULT_PIPE = "dynamic_greeting_sequence"


async def submit(bundle: str, pipe_code: str) -> None:
    bundle_content = Path(bundle).read_text(encoding="utf-8")
    runner = PipelexRunner(
        bundle_uris=[bundle],
        pipe_run_mode=PipeRunMode.DRY,
        execution_config=None,
        library_dirs=None,
    )
    delivery = DeliveryAssignment(storage=StorageTarget())
    print(f"Submitting pipe='{pipe_code}' with delivery_assignment={delivery!r}")
    response = await runner.execute_pipeline(
        pipe_code=pipe_code,
        mthds_contents=[bundle_content],
        inputs=None,
        delivery_assignment=delivery,
    )
    print(f"OK: pipeline_run_id={response.pipeline_run_id} state={response.pipeline_state}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", default=DEFAULT_BUNDLE)
    parser.add_argument("--pipe", default=DEFAULT_PIPE, dest="pipe_code")
    args = parser.parse_args()

    make_pipelex_for_cli(context=ErrorContext.VALIDATION_BEFORE_PIPE_RUN, library_dirs=None, temporal_enabled=True)
    try:
        asyncio.run(submit(bundle=args.bundle, pipe_code=args.pipe_code))
    finally:
        Pipelex.teardown_if_needed()


if __name__ == "__main__":
    main()
