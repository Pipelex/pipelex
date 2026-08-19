"""Stamp headers: every generated file self-describes so a lone file can testify about itself.

A stamp is a small, machine-parseable comment block prepended to a generated file (see the Stamp
header format in the codegen spec). It records the source crate fingerprint, the engine
version that produced the file, the projection (`kind` / `target`, plus `pipe_ref` for per-pipe
artifacts), any output-affecting options, and a **content hash of the body below the stamp** — so a
hand edit anywhere under the stamp is detectable without the engine, the network, or the lock.

The stamp hashes the crate fingerprint (the semantic hash), not raw authored bytes: reformatting or
commenting a `.mthds` file never changes a stamp; changing a method's effective type surface always
does. The block is emitted in the target language's comment syntax (`#` for Python, `//` for
TypeScript), delimited by `>>> … >>>` / `<<< … <<<` fences so the offline check can split stamp from
body byte-exactly and recompute the hash.
"""

import hashlib
import json
from pathlib import Path
from typing import NoReturn, cast

from pydantic import BaseModel, ConfigDict

from pipelex.codegen.emitters.target import CodegenKind, CodegenTarget
from pipelex.codegen.exceptions import CodegenStampError

_BEGIN_MARKER = ">>> pipelex-codegen-stamp >>>"
_END_MARKER = "<<< pipelex-codegen-stamp <<<"

_COMMENT_PREFIX_BY_SUFFIX = {".py": "#", ".ts": "//"}

# The file suffixes codegen stamps — the single source of truth (the offline check derives from this).
STAMPABLE_SUFFIXES = frozenset(_COMMENT_PREFIX_BY_SUFFIX)


class CodegenStamp(BaseModel):
    """The self-describing header of one generated file (everything but the body it protects)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    crate_fingerprint: str
    """The semantic hash of the crate the file was generated from (the standard's crate `fingerprint`)."""

    engine_version: str
    """The `pipelex` codegen engine version that produced the file."""

    kind: CodegenKind
    """The projection `kind` axis (`types`, `inputs`, …)."""

    target: CodegenTarget
    """The projection `target` axis (the language / idiom flavor)."""

    pipe_ref: str | None = None
    """The qualified pipe ref for a per-pipe projection; `None` for a concept-set projection."""

    options: dict[str, str]
    """Output-affecting projection options (empty when none apply)."""

    content_hash: str
    """SHA-256 hex digest of the body below the stamp (recomputed by the offline check)."""


class ParsedStamp(BaseModel):
    """A stamp parsed back off disk, paired with the body text it protects (below the stamp block)."""

    model_config = ConfigDict(frozen=True)

    stamp: CodegenStamp
    body: str


def comment_prefix_for(filename: str) -> str:
    """The line-comment prefix for a generated file, by suffix (`.py` → `#`, `.ts` → `//`)."""
    prefix = _COMMENT_PREFIX_BY_SUFFIX.get(Path(filename).suffix)
    if prefix is None:
        msg = f"Cannot stamp '{filename}': no known comment syntax for its file type (expected .py or .ts)."
        raise CodegenStampError(msg)
    return prefix


def compute_content_hash(body: str) -> str:
    """The canonical content hash of a generated body: lowercase SHA-256 hex over its UTF-8 bytes."""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _projection_line(*, kind: CodegenKind, target: CodegenTarget, pipe_ref: str | None) -> str:
    parts = [f"{kind} / {target}"]
    if pipe_ref is not None:
        parts.append(pipe_ref)
    return " / ".join(parts)


def apply_stamp(
    body: str,
    *,
    crate_fingerprint: str,
    engine_version: str,
    kind: CodegenKind,
    target: CodegenTarget,
    pipe_ref: str | None,
    options: dict[str, str],
    comment_prefix: str,
) -> str:
    """Prepend a stamp block to `body`, hashing the body so tampering below the stamp is detectable.

    The returned text is `<stamp block>` + `body`, so a producer that regenerates the same body against
    the same crate and engine writes byte-identical output (the enabler for write-if-changed).
    """
    content_hash = compute_content_hash(body)
    projection = _projection_line(kind=kind, target=target, pipe_ref=pipe_ref)
    fields = {
        "crate_fingerprint": crate_fingerprint,
        "engine_version": engine_version,
        "projection": projection,
        "options": json.dumps(options, sort_keys=True, ensure_ascii=False, separators=(",", ":")),
        "content_hash": content_hash,
    }
    lines = [f"{comment_prefix} {_BEGIN_MARKER}"]
    lines += [f"{comment_prefix} {key}: {value}" for key, value in fields.items()]
    lines.append(f"{comment_prefix} {_END_MARKER}")
    return "\n".join(lines) + "\n" + body


def parse_stamped(text: str, *, comment_prefix: str) -> ParsedStamp | None:
    """Split a stamped file back into its stamp and the body below it, or `None` if no stamp is present.

    The body is everything after the end-marker line (byte-exact), so recomputing its hash reproduces
    the value the stamp recorded.
    """
    begin_line = f"{comment_prefix} {_BEGIN_MARKER}"
    end_line = f"{comment_prefix} {_END_MARKER}"
    if not text.startswith(begin_line):
        return None
    end_index = text.find(f"\n{end_line}\n")
    if end_index == -1:
        return None
    header_region = text[len(begin_line) + 1 : end_index]
    body = text[end_index + len(end_line) + 2 :]

    # Every line we ever write inside the fence carries the comment prefix, so anything else in there
    # was injected by hand — and it would otherwise verify as pristine, since the hash covers only the
    # body below the fence. An executable line hiding inside a "DO NOT EDIT" block is not a valid stamp.
    #
    # `splitlines` is the deliberate choice over splitting on `"\n"` alone: it also breaks on U+2028,
    # U+2029 and U+0085, and the first two terminate a `//` comment in ECMAScript. Split narrowly, a `.ts`
    # header carrying a raw U+2028 followed by a statement is one prefixed line to this gate and two lines
    # to the JavaScript engine — so `codegen check` would report the file current while it executes the
    # injected code, since the header itself is not hashed. The SDK's mirror of this parser splits on the
    # same set for the same reason (`PYTHON_LINE_BOUNDARY` in `@pipelex/sdk`'s `codegen-check.ts`).
    #
    # Nothing legitimate is rejected, because the emitter cannot write such a header: no caller supplies
    # `pipe_ref` or `options`, and the four fields that are written are two hex digests, a package version
    # and two enum members. If either field ever carries real data, escape the line terminators *at the
    # emitter* then — this gate stays correct, because the emitter will never write a raw one.
    if any(not line.startswith(comment_prefix) for line in header_region.splitlines()):
        return None

    fields = _parse_fields(header_region, comment_prefix=comment_prefix)
    projection = fields.get("projection")
    if projection is None:
        return None
    parsed_projection = _parse_projection(projection)
    if parsed_projection is None:
        return None
    kind, target, pipe_ref = parsed_projection

    options_raw = fields.get("options", "{}")
    options = _parse_options(options_raw)
    if options is None:
        return None
    stamp = CodegenStamp(
        crate_fingerprint=fields.get("crate_fingerprint", ""),
        engine_version=fields.get("engine_version", ""),
        kind=kind,
        target=target,
        pipe_ref=pipe_ref,
        options=options,
        content_hash=fields.get("content_hash", ""),
    )
    return ParsedStamp(stamp=stamp, body=body)


def has_stamp(text: str, *, comment_prefix: str) -> bool:
    """Whether `text` opens with a codegen stamp block for the given comment syntax."""
    return text.startswith(f"{comment_prefix} {_BEGIN_MARKER}")


def _parse_fields(header_region: str, *, comment_prefix: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    # Same split rule as the gate in `parse_stamped`, and it has to stay the same one: a narrower split
    # here would rejoin a line the gate had already split, so a field value would swallow the injected
    # text the gate exists to catch.
    for raw_line in header_region.splitlines():
        # `parse_stamped` has already rejected any line without the prefix, so stripping it is unconditional.
        stripped = raw_line[len(comment_prefix) :].strip()
        key, separator, value = stripped.partition(":")
        if separator:
            fields[key.strip()] = value.strip()
    return fields


def _parse_projection(projection: str) -> tuple[CodegenKind, CodegenTarget, str | None] | None:
    parts = [segment.strip() for segment in projection.split("/")]
    if len(parts) < 2:
        return None
    kind = _kind_from_value(parts[0])
    target = _target_from_value(parts[1])
    if kind is None or target is None:
        return None
    pipe_ref = parts[2] if len(parts) > 2 else None
    return kind, target, pipe_ref


def _kind_from_value(value: str) -> CodegenKind | None:
    return next((member for member in CodegenKind if member == value), None)


def _target_from_value(value: str) -> CodegenTarget | None:
    return next((member for member in CodegenTarget if member == value), None)


def _reject_json_constant(value: str) -> NoReturn:
    """Refuse `NaN` / `Infinity` / `-Infinity`: Python's `json` accepts them, conformant parsers do not."""
    msg = f"Non-standard JSON constant in stamp options: {value}"
    raise ValueError(msg)


def _parse_options(options_raw: str) -> dict[str, str] | None:
    try:
        # The stamp header is a cross-language interchange format, so a stamp only Python can read is
        # not a valid stamp: `parse_constant` turns those literals into the `ValueError` below.
        loaded = json.loads(options_raw, parse_constant=_reject_json_constant)
    except ValueError:  # JSONDecodeError is a subclass, so this one clause covers malformed JSON too
        return None
    if not isinstance(loaded, dict):
        return None
    typed = cast("dict[str, object]", loaded)
    return {str(key): str(value) for key, value in typed.items()}
