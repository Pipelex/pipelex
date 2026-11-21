"""`pipe_id`, the stable identifier of a pipe, and the run attributes that ride every span beside it.

**Why a pipe needs an identifier that is not its code.** A deployment that keeps pipe codes out of its telemetry
(`custom_posthog.tracing.capture.pipe_codes = false`, the hosted plane's setting) reports each span by its pipe type
alone, so no step of a method can be followed from one run to the next. `pipe_id` names the step without naming it:
the same value for one pipe of one method across runs, and across the runner and the worker of a deployment, and a
value nobody can turn back into the pipe code.

**A keyed digest, never a plain hash.** Pipe codes are short snake_case words, so a plain hash of one could be
confirmed by hashing candidate codes. `pipe_id` is an HMAC-SHA256 under the deployment's secret `pipe_id_key`
(`telemetry.toml`), truncated to `PIPE_ID_HEX_LENGTH` hexadecimal characters. A runtime with no key configured, a
local install or a self-hosted one that set none, sends no `pipe_id` at all: never a fallback value. Changing the key
starts a new series of identifiers.

**Its input is the method's identity and the pipe.** The method's identity is, by precedence, the run's `method_id`
(the host's id of the stored method it belongs to), else the address of the published package the run addressed
(`RunMetadata.method_address`), else the pipe's own domain. Each kind is tagged, so a domain can never collide with
a method id of the same spelling, and the pipe is its domain-qualified reference, so two pipes of one method that
share a code in different domains stay apart.
"""

import hashlib
import hmac
from enum import StrEnum

from pipelex.system.job_metadata import RunMetadata
from pipelex.system.telemetry.otel_constants import PipelexSpanAttr
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract

# 128 bits of the digest: ample to keep the pipes of every method apart, and short enough to read in a chart.
PIPE_ID_HEX_LENGTH = 32

# Between the parts of the digested message; it appears in no method id, package address or pipe reference.
_PART_SEPARATOR = "\n"


class MethodIdentityKind(StrEnum):
    """Where the method's identity behind a `pipe_id` came from, tagged into the digested message."""

    METHOD_ID = "method_id"
    METHOD_ADDRESS = "method_address"
    DOMAIN = "domain"


def method_identity_of(*, run_metadata: RunMetadata, domain_code: str) -> str:
    """The method's identity a pipe's `pipe_id` is computed from: the run's `method_id`, else its package address, else the pipe's domain.

    Args:
        run_metadata: The run the pipe runs in.
        domain_code: The pipe's own domain, the identity when the run names no method.

    Returns:
        The identity, tagged with its kind.
    """
    if run_metadata.method_id is not None:
        return f"{MethodIdentityKind.METHOD_ID}:{run_metadata.method_id}"
    if run_metadata.method_address is not None:
        return f"{MethodIdentityKind.METHOD_ADDRESS}:{run_metadata.method_address}"
    return f"{MethodIdentityKind.DOMAIN}:{domain_code}"


def make_pipe_id(*, key: str, method_identity: str, pipe_ref: str) -> str:
    """The keyed digest of a pipe's method identity and reference.

    Args:
        key: The deployment's `pipe_id_key`.
        method_identity: The method's identity, from `method_identity_of`.
        pipe_ref: The pipe's domain-qualified reference.

    Returns:
        The first `PIPE_ID_HEX_LENGTH` hexadecimal characters of the HMAC-SHA256 of the two under the key.
    """
    message = f"{method_identity}{_PART_SEPARATOR}{pipe_ref}"
    digest = hmac.new(key=key.encode("utf-8"), msg=message.encode("utf-8"), digestmod=hashlib.sha256).hexdigest()
    return digest[:PIPE_ID_HEX_LENGTH]


def make_pipe_id_for_run(*, run_metadata: RunMetadata, domain_code: str, pipe_ref: str) -> str | None:
    """The `pipe_id` of a pipe running in this run, under this process's key, or None when the runtime has no key.

    Args:
        run_metadata: The run the pipe runs in.
        domain_code: The pipe's own domain.
        pipe_ref: The pipe's domain-qualified reference.

    Returns:
        The pipe's `pipe_id`, or None when no `pipe_id_key` is configured.
    """
    key = TelemetryManagerAbstract.get_pipe_id_key()
    if key is None:
        return None
    return make_pipe_id(key=key, method_identity=method_identity_of(run_metadata=run_metadata, domain_code=domain_code), pipe_ref=pipe_ref)


def make_run_method_span_attributes(*, run_metadata: RunMetadata, pipe_id: str | None) -> dict[str, str | bool]:
    """The attributes a pipe span or an inference span carries about its run's method, its pipe and its pipe-code setting.

    Each is absent, never empty, when there is nothing to say: the run's `method_id` when it has none, `pipe_id`
    when the runtime has no key, and the run's pipe-code setting when the host set none, so the exporter that redacts
    falls back to its own configuration.

    Args:
        run_metadata: The run the span belongs to.
        pipe_id: The pipe's `pipe_id`: the span's own pipe on a pipe span, the pipe that made the call on an inference span.

    Returns:
        The attributes to merge into the span's attribute dict.
    """
    attributes: dict[str, str | bool] = {}
    if run_metadata.method_id is not None:
        attributes[PipelexSpanAttr.RUN_METHOD_ID] = run_metadata.method_id
    if pipe_id is not None:
        attributes[PipelexSpanAttr.PIPE_ID] = pipe_id
    if run_metadata.capture_pipe_codes is not None:
        attributes[PipelexSpanAttr.RUN_CAPTURE_PIPE_CODES] = run_metadata.capture_pipe_codes
    return attributes
