"""Shared renderers for the explicit absence artifact.

A run whose declared output resolved absent is a first-class success, and every surface that
would render the main value renders an explicit absence document instead — never an error,
never a silently empty envelope. These helpers are the one source of that document's shape so
the delivery executor, the CLI run cores, and telemetry cannot drift:

- the JSON payload carries an ``"absent": true`` discriminator beside the record fields, so a
  consumer can tell an absence document from a value dump;
- the markdown is a human-readable summary with the provenance chain;
- the HTML is the JSON payload escaped inside a ``<pre>`` block.
"""

import html
from typing import Any

from pipelex.core.memory.absence import AbsenceRecord
from pipelex.tools.misc.json_utils import clean_json_dumps


def build_absence_payload(absence_record: AbsenceRecord) -> dict[str, Any]:
    """The JSON-safe absence document: ``{"absent": true, ...record fields...}``."""
    return {"absent": True, **absence_record.model_dump()}


def build_absence_json(absence_record: AbsenceRecord) -> str:
    """The absence payload serialized as indented JSON (one serializer for every surface)."""
    return clean_json_dumps(build_absence_payload(absence_record), indent=2)


def build_absence_html(absence_record: AbsenceRecord) -> str:
    """The HTML absence document: the JSON payload escaped inside a ``<pre>`` block.

    Escaping before embedding is the same XSS-hardening as the raw-JSON value fallback —
    record fields carry user-controlled strings.
    """
    return f"<pre>{html.escape(build_absence_json(absence_record))}</pre>"


def build_absence_markdown(absence_record: AbsenceRecord) -> str:
    """A human-readable absence summary with the provenance chain, as markdown."""
    md_lines = [
        "# Output absent",
        "",
        "The run completed with no value for its declared output.",
        "",
        f"- **Slot:** `{absence_record.variable_name}`",
        f"- **Kind:** {absence_record.kind}",
        f"- **Reason:** {absence_record.reason}",
    ]
    if absence_record.producing_pipe:
        md_lines.append(f"- **Produced by:** pipe `{absence_record.producing_pipe}`")
    chain = absence_record.provenance_chain()
    if len(chain) > 1:
        md_lines.extend(["", "## Provenance", ""])
        for chain_index, chained_record in enumerate(chain):
            producer_suffix = f" (pipe `{chained_record.producing_pipe}`)" if chained_record.producing_pipe else ""
            md_lines.append(f"{chain_index + 1}. `{chained_record.variable_name}` — {chained_record.kind}: {chained_record.reason}{producer_suffix}")
    return "\n".join(md_lines) + "\n"
