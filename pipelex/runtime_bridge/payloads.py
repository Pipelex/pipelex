"""JSON-safe boundary payloads for the runtime bridge.

Extracted from ``bridge.py`` so they can be referenced (e.g. by the orchestrator
SPI / ``OrchestratorProtocol``) without importing the bridge's dispatch logic —
which pulls the bootstrap path and would form an import cycle. This module is
deliberately import-light: pydantic, the orchestration/delivery types, stdlib typing.

``bridge.py`` re-exports both names, so existing
``from pipelex.runtime_bridge.bridge import PipelexPipeRunInput`` imports keep working.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pipelex.runtime_bridge.delivery_mode import DeliveryMode
from pipelex.runtime_bridge.orchestration_mode import DIRECT_ORCHESTRATION_MODE


class PipelexPipeRunInput(BaseModel):
    """JSON-safe input crossing the host-runtime / Temporal boundary."""

    model_config = ConfigDict(extra="forbid")

    pipe_code: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    output_name: str | None = None
    pipeline_run_id: str | None = None
    user_id: str | None = None
    library_crate_dump: dict[str, Any] | None = None
    # Two orthogonal axes: which orchestrator runs the pipe (open token, defaults to the
    # core in-process orchestrator) and whether the caller waits (endpoint-set; defaults
    # to BLOCKING). ``orchestration_mode`` is a plain ``str`` because the set of tokens is
    # open (plugins contribute their own); validation is the registry lookup at dispatch.
    orchestration_mode: str = DIRECT_ORCHESTRATION_MODE
    delivery: DeliveryMode = DeliveryMode.BLOCKING
    delivery_assignment_dump: dict[str, Any] | None = None


class PipelexPipeRunOutput(BaseModel):
    """JSON-safe output crossing the host-runtime / Temporal boundary."""

    model_config = ConfigDict(extra="forbid")

    output_dict: dict[str, Any]
    main_stuff_name: str | None = None
    pipeline_run_id: str
    workflow_id: str | None = None
    is_completed: bool
    graph_spec_dump: dict[str, Any] | None = None
    # graph_assembly_error / usage_assembly_error mirror the same fields on PipeOutput: a non-None
    # value means assembly of the graph / token usage failed, which a host must be able to tell
    # apart from "assembly was off" (a None graph_spec_dump / tokens_usages_dump). tokens_usages_dump
    # is the JSON-safe dump of the AnyTokensUsage discriminated union so a host can render the
    # end-of-run cost report: None when cost reporting was off, [] when on but no inference happened.
    graph_assembly_error: str | None = None
    tokens_usages_dump: list[dict[str, Any]] | None = None
    usage_assembly_error: str | None = None
