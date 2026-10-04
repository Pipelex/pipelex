"""Shared constants for unit tests.

Each test class assembles a tiny FastAPI app with a couple of throwaway
routes used purely to exercise the auth dependencies through `TestClient`.
Centralising the path strings here means the route names never drift out
of sync between the `add_api_route` call and the `client.get(...)` call.
"""

from enum import StrEnum


class RoutePath(StrEnum):
    """Route paths registered by the test helper apps.

    Named `RoutePath` (not `TestRoute`) so pytest's `Test*` class-collection
    scanner doesn't try to collect this StrEnum.
    """

    WHOAMI = "/whoami"
    PING = "/ping"


# The stubbed method-package fixtures (`install_method_package` in conftest.py) present a fake
# fetched clone in the library-repo layout: `methods/documents/METHODS.toml` declaring this
# manifest, so the package's full address is `github.com/pipelex/methods/documents`.
STUB_METHOD_ADDRESS = "github.com/pipelex/methods/documents"
STUB_METHOD_COMMIT_SHA = "0123456789abcdef0123456789abcdef01234567"
STUB_METHOD_MANIFEST = """\
[package]
name = "documents"
address = "github.com/pipelex/methods"
version = "0.1.0"
description = "A stub package for method_ref route tests."
main_pipe = "echo"

[exports.smoke]
pipes = ["echo"]
"""

# The same stub manifest with `main_pipe` naming `shout` — a pipe the closure's own declarations
# would NOT default to (and, beside a second declared main_pipe, could not default at all). Exercises
# the manifest outranking the closure in the tooling routes' pipe-default chain.
STUB_METHOD_MANIFEST_MAIN_PIPE_SHOUT = """\
[package]
name = "documents"
address = "github.com/pipelex/methods"
version = "0.1.0"
description = "A stub package whose manifest names an entry pipe the closure would not default to."
main_pipe = "shout"

[exports.smoke]
pipes = ["echo"]

[exports.other]
pipes = ["shout"]
"""

# The same stub manifest declaring NO `main_pipe` — the chain then falls through to the closure's
# own declaration, exactly as for inline `files[]`.
STUB_METHOD_MANIFEST_NO_MAIN_PIPE = """\
[package]
name = "documents"
address = "github.com/pipelex/methods"
version = "0.1.0"
description = "A stub package whose manifest declares no entry pipe."

[exports.smoke]
pipes = ["echo"]
"""

# A stub manifest naming `echo` as the entry pipe of a package whose only bundle is
# `NO_MAIN_PIPE_MTHDS` (domain `nomain`): the manifest is then the only place the entry pipe is
# declared, as in a published package whose bundles leave `main_pipe` to `METHODS.toml`.
STUB_METHOD_MANIFEST_NOMAIN_ENTRY = """\
[package]
name = "documents"
address = "github.com/pipelex/methods"
version = "0.1.0"
description = "A stub package whose entry pipe only its manifest declares."
main_pipe = "echo"

[exports.nomain]
pipes = ["echo"]
"""

# A minimal, valid single-pipe bundle used across the build/validate/pipeline route tests.
VALID_MTHDS = """\
domain = "smoke"
main_pipe = "echo"

[pipe.echo]
type = "PipeLLM"
description = "Echo"
inputs = { text = "Text" }
output = "Text"
prompt = "@text"
"""

# A second bundle in the `smoke` domain, referencing VALID_MTHDS's pipe — proves the closure is
# merged across files[] entries before resolution, and gives the closure a second, non-entry pipe.
SIBLING_MTHDS = """\
domain = "smoke"

[pipe.wrap_echo]
type = "PipeSequence"
description = "Wrap the echo pipe"
inputs = { text = "Text" }
output = "Text"
steps = [{ pipe = "echo", result = "echoed" }]
"""

# One pipe whose contracts and forms carry multiplicity (a variable list input, a fixed-count
# output) and a structured concept with an optional field — the shapes an I/O artifact must carry.
SHAPES_MTHDS = """\
domain = "shapes"
main_pipe = "digest"

[concept]
Brief = "A short brief"
Note = "A working note"

[concept.Card]
description = "A structured card"

[concept.Card.structure]
title = { type = "text", description = "The card title", required = true }
score = { type = "number", description = "A score" }

[pipe.digest]
type = "PipeLLM"
description = "Digest a brief and some notes into two cards"
inputs = { brief = "Brief", notes = "Note[]" }
output = "Card[2]"
prompt = '''
Digest this brief: $brief

@notes
'''
"""

# A valid single-pipe bundle that declares NO main_pipe — validates fine (D2: no main-pipe
# precondition on /validate) and simply yields no graph. On `/pipe-io` it is also the closure that
# cannot default its pipe selector: an omitted `pipe_ref` is a 422 there.
NO_MAIN_PIPE_MTHDS = """\
domain = "nomain"

[pipe.echo]
type = "PipeLLM"
description = "Echo"
inputs = { text = "Text" }
output = "Text"
prompt = "@text"
"""

# A second domain declaring its own main_pipe. Submitted alongside VALID_MTHDS it makes the closure's
# main_pipe *ambiguous* — the other arm an omitted `pipe_ref` must reject with a 422.
SECOND_MAIN_PIPE_MTHDS = """\
domain = "other"
main_pipe = "shout"

[pipe.shout]
type = "PipeLLM"
description = "Shout"
inputs = { text = "Text" }
output = "Text"
prompt = "@text"
"""

# A pipe whose BARE code collides with VALID_MTHDS's `echo`, in a different domain, and whose output
# carries the opposite multiplicity (a list). Submitted alongside VALID_MTHDS it catches any lookup
# that matches a pipe by bare code alone: a bare `echo` must be refused as ambiguous, never resolved
# to whichever `echo` came first.
COLLIDING_ECHO_LIST_MTHDS = """\
domain = "twin"

[pipe.echo]
type = "PipeLLM"
description = "Echo, but many"
inputs = { text = "Text" }
output = "Text[]"
prompt = "@text"
"""

# An invalid `main_pipe` deterministically fails blueprint validation, producing a categorized
# BLUEPRINT_VALIDATION error that carries the blueprint's `source` — the cheapest way to exercise
# the structured `validation_errors` 422 and its `source` threading. (Mirrors the pipelex
# integration fixture in `tests/integration/pipelex/pipeline/test_validate_bundle_source_threading.py`.)
INVALID_MAIN_PIPE_MTHDS = """\
domain = "broken"
description = "Invalid main_pipe"
main_pipe = "Not A Valid Pipe Code!"

[concept.Customer]
description = "A customer"
"""

# Multi-file batches mirroring pipelex's additive-multi-file-library E2E fixtures
# (`tests/e2e/pipelex/pipes/additive_multi_file_library/` in the pipelex repo) — the same
# scenarios the protocol-alignment baseline snapshots were captured from. Copied, not read
# from the pipelex checkout: the suite must stay self-contained once the editable pin is
# replaced by the PyPI pin (whose wheel ships no tests).

# signature_only/: concepts + a PipeSignature header referenced by a sibling controller —
# valid only in lenient mode (`allow_signatures=True`), reports the pending signature.
SIGNATURE_ONLY_BATCH: list[str] = [
    """\
domain      = "research"
description = "Research method domain"

[concept]
KeyFinding = "A key finding extracted from a source document"
""",
    """\
domain      = "research"
description = "Research method headers"

[pipe.find_key_findings]
description = "Find the key findings in a document (contract only)."
inputs      = { doc = "Text" }
output      = "KeyFinding"

[pipe.research_brief]
type        = "PipeSequence"
description = "Produce a research brief from a document."
inputs      = { doc = "Text" }
output      = "KeyFinding"
steps       = [{ pipe = "find_key_findings", result = "findings" }]
""",
]

# header_and_definition/: the same header plus a concrete definition satisfying it —
# valid in strict mode, nothing pending.
HEADER_AND_DEFINITION_BATCH: list[str] = [
    """\
domain      = "research"
description = "Research method domain"

[concept]
KeyFinding = "A key finding extracted from a source document"
""",
    """\
domain      = "research"
description = "Research method headers"

[pipe.find_key_findings]
description = "Find the key findings in a document (contract only)."
inputs      = { doc = "Text" }
output      = "KeyFinding"
""",
    """\
domain      = "research"
description = "Research method definitions"

[pipe.find_key_findings]
type        = "PipeLLM"
description = "Find the key findings in a document."
inputs      = { doc = "native.Text" }
output      = "research.KeyFinding"
model       = "$quick-reasoning"
prompt      = "List the key findings in $doc."
""",
]

# VALID_MTHDS with its output concept misspelled: the load refuses it as an `unresolved_concept`
# item located on `pipe.echo.output`. A run of it used to escape the load as a raw 500.
MISSPELLED_CONCEPT_MTHDS = """\
domain = "smoke"
main_pipe = "echo"

[pipe.echo]
type = "PipeLLM"
description = "Echo"
inputs = { text = "Text" }
output = "Summry"
prompt = "@text"
"""

# VALID_MTHDS naming a model the model deck does not define: the load refuses it as an
# `unknown_model` item located on `pipe.echo.model`. A run of it used to raise the raw
# `PipeOperatorModelChoiceError`, with no validation item.
UNKNOWN_MODEL_MTHDS = """\
domain = "smoke"
main_pipe = "echo"

[pipe.echo]
type = "PipeLLM"
description = "Echo"
inputs = { text = "Text" }
output = "Text"
model = "no-such-model-in-any-deck"
prompt = "@text"
"""

# A bundle that loads but whose run fails one step down, in a live run and a dry run alike since no
# pipe calls a model: `review_topic` runs the parallel `analyze_topic`, whose branch `draft_idea` gives
# one `Idea` for the field `ideas`, which `TopicReview` declares as a list. The combine of the branch
# results refuses it at `analyze_topic`, and the refusal is the caller's own method to fix.
MISMATCHED_PARALLEL_MTHDS = """\
domain      = "brainstorm"
description = "A parallel feeding a single branch into a list field"
main_pipe   = "review_topic"

[concept.Idea]
description = "One idea about a topic"
refines     = "Text"

[concept.Overview]
description = "A one-line overview"
refines     = "Text"

[concept.TopicReview]
description = "Ideas and an overview"

[concept.TopicReview.structure]
ideas    = { type = "list", item_type = "concept", item_concept_ref = "Idea", description = "The ideas", required = true }
overview = { type = "concept", concept_ref = "Overview", description = "The overview", required = true }

[pipe.review_topic]
type        = "PipeSequence"
description = "Review a topic"
inputs      = { topic = "Text" }
output      = "TopicReview"
steps       = [ { pipe = "analyze_topic", result = "review" } ]

[pipe.analyze_topic]
type        = "PipeParallel"
description = "Draft the idea and the overview at the same time"
inputs      = { topic = "Text" }
output      = "TopicReview"
branches    = [
  { pipe = "draft_idea", result = "ideas" },
  { pipe = "write_overview", result = "overview" },
]

[pipe.draft_idea]
type        = "PipeCompose"
description = "Draft one idea about the topic"
inputs      = { topic = "Text" }
output      = "Idea"
template    = "An idea worth exploring about $topic"

[pipe.write_overview]
type        = "PipeCompose"
description = "Write a one-line overview"
output      = "Overview"
template    = "One idea."
"""

# A bundle whose PipeSequence references an unimplemented PipeSignature step. It loads and wires
# cleanly, so the only thing that rejects it in strict mode is the signature pre-pass — isolating
# the `allow_signatures` behavior from any other validation failure.
SIGNATURE_MTHDS = """\
domain = "sig_api"
main_pipe = "caller_seq"

[concept]
ApiDoc = "A document used in API signature tests."
ApiSummary = "A summary used in API signature tests."

[pipe.caller_seq]
type = "PipeSequence"
description = "Caller sequence referencing a signature step."
inputs = { doc = "ApiDoc" }
output = "ApiSummary"
steps = [ { pipe = "summary_sig", result = "summary" } ]

[pipe.summary_sig]
description = "Signature placeholder for the summary step."
inputs = { doc = "ApiDoc" }
output = "ApiSummary"
"""
