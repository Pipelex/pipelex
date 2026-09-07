"""The three I/O artifacts that describe a method's data, built once and carried together.

`pipe_io_contracts`, `input_form` and `output_form` are the validate report's own fields, each
keyed by namespaced `pipe_ref`, and they are always produced together because they share one key
set: all three iterate the same pipes. `PipeIOArtifacts` is the carrier that keeps them together
wherever a graph travels — on `PipeOutput` beside `graph_spec`, across the SPI payload, and into a
results directory as three sibling files beside `graphspec.json`. The one sequence that derives
them is `build_pipe_io_artifacts` (its own module: it needs the live library, and this carrier is
imported by `PipeOutput`, which must stay free of the library machinery).

The rendering follows the projection corpus's byte discipline (two-space indent, `ensure_ascii`
off, one trailing newline, keyed by `pipe_ref` over the JSON-mode dump), so for the same bundle a
results directory and the committed fixture corpus hold byte-identical files.
"""

from __future__ import annotations

import json

from mthds.protocol.input_form import InputForm
from mthds.protocol.output_form import OutputForm
from mthds.protocol.pipe_io_contracts import PipeIOContracts
from pydantic import BaseModel, ConfigDict

PIPE_IO_CONTRACTS_FILE_NAME = "pipe_io_contracts.json"
INPUT_FORM_FILE_NAME = "input_form.json"
OUTPUT_FORM_FILE_NAME = "output_form.json"


class PipeIOArtifacts(BaseModel):
    """The validate report's three I/O artifacts, under the report's names and types.

    A grouping, not a new shape: each field is the standard's artifact, keyed by `pipe_ref`.
    """

    model_config = ConfigDict(extra="forbid")

    pipe_io_contracts: PipeIOContracts
    input_form: InputForm
    output_form: OutputForm


def render_pipe_io_artifact_files(artifacts: PipeIOArtifacts) -> dict[str, str]:
    """Render the artifacts as the three sibling files, file name to text.

    Each text is the projection corpus's byte discipline over `{pipe_ref: artifact}` in JSON mode.
    """
    return {
        PIPE_IO_CONTRACTS_FILE_NAME: _render_json_text(
            {ref: contract.model_dump(mode="json") for ref, contract in artifacts.pipe_io_contracts.items()}
        ),
        INPUT_FORM_FILE_NAME: _render_json_text({ref: descriptor.model_dump(mode="json") for ref, descriptor in artifacts.input_form.items()}),
        OUTPUT_FORM_FILE_NAME: _render_json_text({ref: descriptor.model_dump(mode="json") for ref, descriptor in artifacts.output_form.items()}),
    }


def _render_json_text(payload: dict[str, object]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
