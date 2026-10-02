"""The one header that says whose call this is: `x-pipelex-metadata`, a flat JSON object.

**Why the Manifold dialect sends it.** The Pipelex Manifold service attributes the spend of every
inference call it serves and logs the call, and neither is possible from the service token alone —
one token serves every run a deployment executes, for every caller and every tenant. So each request
the dialect makes carries, beside the token, a small JSON object naming the run and the step it
belongs to, and the host's own labels for it.

**What goes in it.** The run's `extras` entries, verbatim and unread, then the runtime's own ids:
`user_id` and `pipeline_run_id` from the run half of the job metadata, `pipe_run_id`, `pipe_code`
and `content_generation_job_id` from the step half. An id the job does not carry (`None`) is left
out rather than sent as `null`, so every value on the wire is a string.

**The runtime's keys win on a collision, deliberately.** `extras` is caller data: the host fills it,
and its key charset (`RUN_EXTRAS_KEY_PATTERN`, lowercase snake_case up to 32 characters) admits every
one of the runtime's key names. Letting an extras entry named `user_id` or `pipeline_run_id` stand
would let whoever supplies the labels restate the run's identity to the service that bills for it.
Writing the runtime's keys after the extras makes the run's own facts the last word.

**The runtime still never reads a key of `extras` by name** — the rule `pipelex.system.run_extras`
states. The mapping is copied across whole; nothing here knows that the hosted platform puts an
organization id in it, and a deployment that sends other labels is served identically.

**Why the value cannot forge a header line.** Every value reaching this module is already bounded —
the extras charset, the request-id check, the hex run ids — but the encoding does not rely on that.
`json.dumps` with ASCII output escapes every control character (CR and LF included) and every
non-ASCII code point, and the one printable-range character JSON leaves raw that an HTTP field value
refuses, DEL, is escaped here too. What reaches the wire is printable ASCII, whatever went in.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pipelex.providers.manifold.manifold_constants import MANIFOLD_METADATA_HEADER

if TYPE_CHECKING:
    from pipelex.system.job_metadata import JobMetadata


def make_manifold_metadata(*, job_metadata: JobMetadata) -> dict[str, str]:
    """The flat mapping the header carries: the run's extras, then the runtime's own ids over them."""
    run_metadata = job_metadata.run_metadata
    runtime_ids: dict[str, str | None] = {
        "user_id": run_metadata.user_id,
        "pipeline_run_id": run_metadata.pipeline_run_id,
        "pipe_run_id": job_metadata.pipe_run_id,
        "pipe_code": job_metadata.pipe_code,
        "content_generation_job_id": job_metadata.content_generation_job_id,
    }
    metadata: dict[str, str] = dict(run_metadata.extras)
    for key, value in runtime_ids.items():
        if value is None:
            # An absent id is not a colliding one: an extras entry of the same name is dropped
            # rather than left standing in for a fact the runtime does not have.
            metadata.pop(key, None)
            continue
        metadata[key] = value
    return metadata


def encode_manifold_metadata(*, metadata: dict[str, str]) -> str:
    """The header value: compact JSON in printable ASCII only."""
    encoded = json.dumps(metadata, ensure_ascii=True, separators=(",", ":"))
    # JSON escapes control characters below 0x20 and, with `ensure_ascii`, everything above 0x7E
    # except DEL itself, which an HTTP field value refuses. `\u007f` is the same JSON string.
    return encoded.replace("\x7f", "\\u007f")


def make_manifold_metadata_headers(*, job_metadata: JobMetadata) -> dict[str, str]:
    """The one-entry header mapping a manifold request adds for the job it serves."""
    return {MANIFOLD_METADATA_HEADER: encode_manifold_metadata(metadata=make_manifold_metadata(job_metadata=job_metadata))}
