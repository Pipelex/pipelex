#!/usr/bin/env python3
"""Workflow test runner -- starts a real worker, executes via the API, reports the result.

Usage:
    python test_workflow.py <file> --input '{}'
    python test_workflow.py <file> --input '{}' --interactions '[{"choice": "WFL"}]'
    python test_workflow.py <file> --input '{}' --timeout 60 --workflow-name my-wf

For interactive workflows (those extending InteractiveWorkflow), pass --interactions
with a JSON array.  Each element is submitted in order to the next wait_for_input() call.

Exit codes: 0 = passed, 1 = failed/timed out, 2 = bad arguments.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import inspect
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

# SDK imports (deferred to avoid import errors when just running --help)
_sdk_imported = False


def _ensure_sdk():
    global _sdk_imported
    if _sdk_imported:
        return
    global workflows, get_mistral_client, get_workflow_definition, BaseModel
    import mistralai.workflows as _wf
    from mistralai.workflows.client import get_mistral_client as _gmc
    from mistralai.workflows.core.definition.workflow_definition import (
        get_workflow_definition as _gwd,
    )
    from pydantic import BaseModel as _BM

    workflows = _wf
    get_mistral_client = _gmc
    get_workflow_definition = _gwd
    BaseModel = _BM
    _sdk_imported = True


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def _import_module(file_path: Path) -> Any:
    """Import a Python module from a filesystem path."""
    spec = importlib.util.spec_from_file_location(file_path.stem, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot create module spec for {file_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[file_path.stem] = mod
    spec.loader.exec_module(mod)
    return mod


def _find_workflow_classes(module: Any) -> list[type]:
    """Return all @workflow.define classes in *module*."""
    return [
        obj
        for _, obj in inspect.getmembers(module, inspect.isclass)
        if hasattr(obj, "__workflows_workflow_def")
    ]


def _workflow_name(cls: type) -> str:
    return get_workflow_definition(cls).name


def _is_interactive(cls: type) -> bool:
    return issubclass(cls, workflows.InteractiveWorkflow)


def _discover_workflow(
    workflow_file: Path, name_override: str | None
) -> tuple[type, str, bool]:
    """Find and select the workflow class.  Returns (cls, name, interactive)."""
    module = _import_module(workflow_file)
    found = _find_workflow_classes(module)

    if not found:
        raise SystemExit(
            f"No workflow classes found in {workflow_file}. "
            "Ensure the file has a class decorated with @workflow.define."
        )

    if name_override:
        matches = [w for w in found if _workflow_name(w) == name_override]
        if not matches:
            available = ", ".join(_workflow_name(w) for w in found)
            raise SystemExit(
                f"Workflow '{name_override}' not found. Available: {available}"
            )
        cls = matches[0]
    else:
        if len(found) > 1:
            names = ", ".join(_workflow_name(w) for w in found)
            print(
                f"Multiple workflows found: {names}. Using the first one. "
                "Pass --workflow-name to select.",
                file=sys.stderr,
            )
        cls = found[0]

    return cls, _workflow_name(cls), _is_interactive(cls)


# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------


def _build_input(input_data: dict) -> dict | None:
    """Return the input dict for the API client, or None if empty."""
    if not input_data:
        return None
    return input_data


# ---------------------------------------------------------------------------
# Interactions (for interactive workflows)
# ---------------------------------------------------------------------------


async def _poll_and_submit_interactions(
    client: Any,
    execution_id: str,
    interactions: list[dict],
    poll_timeout: float = 60.0,
    poll_interval: float = 0.5,
) -> None:
    """Poll __get_pending_inputs and submit each interaction response in order."""

    class _Payload(BaseModel):
        task_id: str
        input: dict

    for i, response_data in enumerate(interactions, 1):
        task_id = await _wait_for_pending_input(
            client, execution_id, i, poll_timeout, poll_interval
        )

        print(f"  Interaction {i}: submitting {json.dumps(response_data)}")
        try:
            payload = _Payload(task_id=task_id, input=response_data)
            resp = await asyncio.wait_for(
                client.workflows.executions.update_workflow_execution_async(
                    execution_id=execution_id,
                    name="__submit_input",
                    input=payload.model_dump(mode="json"),
                ),
                timeout=30,
            )
        except asyncio.TimeoutError:
            print(
                f"  Interaction {i}: update timed out "
                "(workflow may have failed to process the input)",
                file=sys.stderr,
            )
            raise

        error = resp.result.get("error") if isinstance(resp.result, dict) else None
        if error:
            raise RuntimeError(f"Interaction {i} rejected: {error}")
        print(f"  Interaction {i}: accepted")


async def _wait_for_pending_input(
    client: Any,
    execution_id: str,
    index: int,
    timeout: float,
    interval: float,
) -> str:
    """Block until a pending input appears, return its task_id."""
    start = asyncio.get_event_loop().time()
    while True:
        try:
            resp = await client.workflows.executions.query_workflow_execution_async(
                execution_id=execution_id, name="__get_pending_inputs"
            )
            pending = resp.result.get("pending_inputs", [])
            if pending:
                task_id = pending[0]["task_id"]
                label = pending[0].get("label", "")
                print(
                    f"  Interaction {index}: pending input found "
                    f"(task={task_id[:8]}..., label={label!r})"
                )
                return task_id
        except Exception:
            pass

        if asyncio.get_event_loop().time() - start > timeout:
            raise TimeoutError(
                f"Timeout waiting for pending input #{index} ({timeout}s)"
            )
        await asyncio.sleep(interval)


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


async def _execute_with_retry(
    client: Any, wf_name: str, input_dict: dict | None, retries: int = 10
) -> Any:
    """Start the workflow, retrying on registration-propagation errors."""
    for attempt in range(retries):
        try:
            return await client.workflows.execute_workflow_async(
                workflow_identifier=wf_name,
                input=input_dict,
            )
        except Exception:
            if attempt == retries - 1:
                raise
            await asyncio.sleep(1)


async def _await_result(
    client: Any,
    execution_id: str,
    interactions: list[dict] | None,
    interactive: bool,
    timeout: int,
) -> dict:
    """Wait for workflow completion, submitting interactions if needed.

    Uses asyncio.wait with FIRST_EXCEPTION so that interaction errors
    (e.g. validation failures) surface immediately instead of blocking
    until the overall timeout.
    """
    if not (interactive and interactions):
        final = await asyncio.wait_for(
            client.workflows.wait_for_workflow_completion_async(
                execution_id, polling_interval=2
            ),
            timeout=timeout,
        )
        return final.result

    # Run interactions and completion polling concurrently.
    interaction_task = asyncio.create_task(
        _poll_and_submit_interactions(
            client, execution_id, interactions, poll_timeout=timeout
        )
    )
    completion_task = asyncio.create_task(
        client.workflows.wait_for_workflow_completion_async(
            execution_id, polling_interval=2
        )
    )

    done, pending = await asyncio.wait(
        [interaction_task, completion_task],
        timeout=timeout,
        return_when=asyncio.FIRST_EXCEPTION,
    )

    for t in pending:
        t.cancel()
        try:
            await t
        except (asyncio.CancelledError, Exception):
            pass

    if not done:
        raise asyncio.TimeoutError()

    # Surface errors -- interaction errors take priority.
    if interaction_task in done and interaction_task.exception():
        raise interaction_task.exception()
    if completion_task in done and completion_task.exception():
        raise completion_task.exception()

    if completion_task in done:
        return completion_task.result().result

    raise asyncio.TimeoutError()


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

# How long to wait after starting the worker before executing.
# The worker needs time to register the workflow with the API and
# start polling the task queue.  8s is empirically reliable.
_WORKER_READY_DELAY = 8


async def run_workflow(
    workflow_file: Path,
    input_data: dict,
    timeout_seconds: int,
    workflow_name_override: str | None,
    interactions: list[dict] | None = None,
) -> dict:
    """Start a real worker, execute the workflow, and return the result."""
    _ensure_sdk()

    # -- discover --
    workflow_cls, wf_name, interactive = _discover_workflow(
        workflow_file, workflow_name_override
    )

    print(f"Workflow:      {wf_name} ({workflow_cls.__name__})")
    print(f"Interactive:   {interactive}")
    print(f"Input:         {json.dumps(input_data)}")
    if interactions:
        print(f"Interactions:  {len(interactions)} response(s) queued")
    print(f"Timeout:       {timeout_seconds}s")
    print()

    if interactive and not interactions:
        print(
            "WARNING: Interactive workflow but no --interactions provided.\n"
            "         The workflow will hang at wait_for_input().\n",
            file=sys.stderr,
        )

    # -- API client --
    client = get_mistral_client()

    # -- start worker --
    print("Starting worker...")
    worker_task = await workflows.run_worker([workflow_cls], detach=True)
    if worker_task is None:
        raise RuntimeError("run_worker(detach=True) returned None")
    print("Worker started.")

    print("Waiting for worker to be ready...", end="", flush=True)
    await asyncio.sleep(_WORKER_READY_DELAY)
    print(" ready.\n")

    execution_id: str | None = None
    try:
        # -- execute --
        execution = await _execute_with_retry(
            client, wf_name, _build_input(input_data)
        )
        execution_id = execution.execution_id
        print(f"Execution:     {execution_id}")
        print(f"Status:        {execution.status}\n")

        # -- wait for result --
        return await _await_result(
            client, execution_id, interactions, interactive, timeout_seconds
        )

    except asyncio.TimeoutError:
        if execution_id:
            print(f"\nTerminating execution {execution_id}...", file=sys.stderr)
            try:
                await client.workflows.executions.terminate_workflow_execution_async(
                    execution_id=execution_id
                )
                print("Execution terminated.", file=sys.stderr)
            except Exception as e:
                print(f"Failed to terminate: {e}", file=sys.stderr)
        raise

    finally:
        if worker_task and not worker_task.done():
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a workflow with a real worker and the Workflows API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "workflow_file", type=Path,
        help="Path to the Python file containing the workflow.",
    )
    parser.add_argument(
        "--input", required=True, dest="input_json",
        help="JSON string with the workflow input.",
    )
    parser.add_argument(
        "--timeout", type=int, default=30,
        help="Max seconds before the workflow is killed (default: 30).",
    )
    parser.add_argument(
        "--workflow-name", default=None,
        help="Workflow name (if the file contains multiple workflows).",
    )
    parser.add_argument(
        "--interactions", default=None, dest="interactions_json",
        help=(
            "JSON array of interaction responses for interactive workflows. "
            'Example: \'[{"choice": "WFL"}]\''
        ),
    )
    return parser.parse_args()


def _parse_json(raw: str, label: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON in {label}: {e}", file=sys.stderr)
        raise SystemExit(2)


def main() -> None:
    args = _parse_args()

    if not args.workflow_file.is_file():
        print(f"Error: {args.workflow_file} does not exist.", file=sys.stderr)
        raise SystemExit(2)

    input_data = _parse_json(args.input_json, "--input")

    interactions = None
    if args.interactions_json:
        interactions = _parse_json(args.interactions_json, "--interactions")
        if not isinstance(interactions, list):
            print("Error: --interactions must be a JSON array.", file=sys.stderr)
            raise SystemExit(2)

    # Load .env if present.
    try:
        from dotenv import load_dotenv
        load_dotenv(override=True)
    except ImportError:
        pass

    # Add workflow's directory to sys.path for relative imports.
    parent = str(args.workflow_file.resolve().parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)

    try:
        result = asyncio.run(
            run_workflow(
                args.workflow_file.resolve(),
                input_data,
                args.timeout,
                args.workflow_name,
                interactions,
            )
        )
        print("PASSED")
        print(json.dumps(result, indent=2, default=str))
    except SystemExit:
        raise
    except asyncio.TimeoutError:
        print("FAILED: workflow timed out", file=sys.stderr)
        raise SystemExit(1)
    except Exception:
        print("FAILED:", file=sys.stderr)
        traceback.print_exc()
        raise SystemExit(1)


if __name__ == "__main__":
    main()
