# PipeSignature is not a type — drop `type = "PipeSignature"` from the language

Branch: `feature/PipeSignature-not-a-type` (currently even with `main`; the signature *machinery* already landed, this branch is the language-surface cleanup).

## The insight

A `PipeSignature` is a **contract declaration** — "this pipe exists, here is its purpose, here is what it takes and what it produces" — with the implementation deferred to somewhere else (a sibling file, a later refinement, a dependency package). The library loader already accepts signatures and reconciles them against the concrete implementation when it shows up.

Today we write a signature like this:

```toml
[pipe.summarize_doc]
type        = "PipeSignature"
description = "Produces a summary of a document (contract only)."
inputs      = { doc = "SigDocument" }
output      = "Text"
```

That `type = "PipeSignature"` line is a lie about the model. `PipeSignature` is **not** a pipe type — the codebase already knows this: it was deliberately evicted from the `PipeType` and `PipeCategory` enums (`pipelex/core/pipes/pipe_blueprint.py:16`, `44-87`), carries `pipe_category = None`, and is identified by class identity (`is_signature`), not by any enum value. A pipe *type* is an implementation kind (PipeLLM, PipeSequence, …). A signature is the **absence** of one.

So the language should stop pretending. The tag adds ceremony, teaches a wrong mental model, and is the kind of bullsh*t our language claims not to have.

## The rule

**A `[pipe.x]` section with no `type` and no implementation is a signature.**

That's it. The whole feature.

Concretely, a pipe declaration needs only:

- `description` — required (what the pipe is for)
- `output` — required (what concept it produces, multiplicity included)
- `inputs` — optional (defaults to none)

If that's *all* a section has, it's a contract — a `PipeSignature`. The moment you add a `type` (and the implementation fields that type needs — `prompt`, `steps`, `branches`, …), it becomes a concrete, runnable pipe.

```toml
# A signature — no type, no implementation. This IS the contract.
[pipe.summarize_doc]
description = "Produces a summary of a document."
inputs      = { doc = "SigDocument" }
output      = "Text"

# Its implementation — same contract, now with a type and a body.
[pipe.summarize_doc]
type        = "PipeLLM"
description = "Produces a summary of a document."
inputs      = { doc = "SigDocument" }
output      = "Text"
prompt      = "Summarize $doc."
```

This reads exactly like a forward declaration vs. a definition in a real language — which is what it is. No new concept to learn; the shape of the file teaches it.

### Scope guardrail (decided)

This change makes **the type tag optional only for the signature case**. Concrete pipes still declare their `type` explicitly — we are **not** inferring the type from fields. And we *can't*, even in principle: fields are not unique to a type. `prompt` does not mean PipeLLM — PipeImgGen uses `prompt` too. There is no field that reliably implies a single concrete type. So inference is off the table, and the rule stays unambiguous: **no `type` ⟺ signature**, and the *only* legal typeless shape is exactly a contract.

## What "no implementation" has to mean (the guard)

The brief says "no type specified **and** no implementation present." Both clauses are load-bearing. A typeless section is a signature **only if it declares nothing but the contract** — `description`, `inputs`, `output` (+ the optional `signature_for` hint, + the internal `source`). The presence of *any* other field means the author is describing an implementation, and an implementation must name its type.

**Decided behavior (no leniency):** a typeless section carrying any non-contract field is a **hard error**. It is never silently treated as a signature (that would hide a real authoring bug behind a mock output), and never a cryptic pydantic dump.

Crucially, the error does **not** guess a type from the fields — because it can't. A `prompt` field is shared by PipeLLM *and* PipeImgGen; no field reliably maps to one type. So the message points at the general fix, not a specific type:

> Pipe `summarize_doc` has no `type` but declares `prompt`. A pipe without a `type` may declare only `description`, `inputs`, and `output` — that is a signature (contract only). To implement it, add the appropriate `type` (`PipeLLM`, `PipeImgGen`, …). To keep it a contract, remove `prompt`.

The error names the offending field(s), states the rule, and gives both escape routes — reinforcing the mental model every time it fires.

## How it works under the hood

The internal machinery does **not** need to lose its discriminator — only the *language surface* drops the tag. This mirrors the workspace rule "structured fields are the contract; the surface is presentation." The blueprint model keeps `type = "PipeSignature"` as an internal runtime discriminator; the `.mthds` author never writes it.

The dispatch is a Pydantic discriminated union on `type` (`pipelex/core/bundles/pipelex_bundle_blueprint.py:29-43`). A discriminated union *requires* the tag, so a missing `type` currently errors with `union_tag_not_found` ("missing required discriminator field 'type'"). We intercept before the union runs.

There is already a `field_validator("pipe", mode="before")` on `PipelexBundleBlueprint` (`validate_pipe_keys`, `:125`). That's the single choke point. It gains a per-section normalization step:

1. **`type` is a real `PipeType`** → leave untouched. Concrete pipe, dispatched as today.
2. **`type` absent, only signature-allowed fields present** → inject `type = "PipeSignature"` so the union routes to `PipeSignatureBlueprint`. The user never saw the tag; the model still discriminates cleanly.
3. **`type` absent, any non-contract field present** → raise the teaching error above (no type inference, no leniency). Legal typeless keys are exactly `{description, inputs, output, signature_for, source}`; anything else fails here.
4. **`type = "PipeSignature"` written explicitly** → raise a migration error (see Migration). It's now an internal-only value.

Everything downstream is unchanged:

- `PipeSignatureBlueprint` still carries the internal tag, `pipe_category = None`, `is_signature = True`.
- Blueprint → runtime factory dispatch keys off `blueprint.is_signature` (`pipe_factory.py:110-117`) — untouched.
- Library reconciliation keys off `is_signature` class identity (`library_crate_factory.py:170-201`) — untouched. Concrete still beats signature; contracts must still match.
- Validation semantics — strict mode refusing bundles that contain signatures, `--allow-signatures` dry-running them as mocks — all key off `is_signature` / the pending-signatures set (`validate_bundle.py`, `_validate_core.py`) — untouched.

## Surfaces to change (implementation checklist)

- **Blueprint parse** — `pipelex/core/bundles/pipelex_bundle_blueprint.py`: extend the `pipe` before-validator with the 4-way normalization + the two teaching errors. This is the heart of the change.
- **Spec parse (authoring layer)** — `pipelex/builder/pipe/pipe_spec_union.py` + a matching before-validator wherever spec dicts are validated into `PipeSpecUnion`. Same 4-way logic so AI-authored specs get the identical clean surface. `PipeSignatureSpec` keeps its internal tag (`pipe_signature_spec.py`).
- **Allowlist / messaging** — `pipelex/core/pipes/pipe_blueprint.py`: `PIPE_SIGNATURE_TYPE_TAG` stays valid *internally* (the injected value must pass `validate_pipe_type`), but the user-facing rejection of an explicitly-written `PipeSignature` lives in the before-validator with a tailored message. Confirm no user path still requires the tag.
- **MTHDS JSON Schema** — `pipelex/language/mthds_schema_generator.py`: today `_require_type_on_pipe_definitions` (`:125`) forces `type` required on *every* pipe arm so a typeless table fails. New behavior: the signature arm must **omit** `type` and become the "no-type" branch (`{description, output, inputs?}`, `additionalProperties: false`). Disambiguation still holds in Draft-4 (no discriminator): a typed table fails the signature arm (extra `type` property under `additionalProperties: false`) and matches its own arm; a typeless table matches only the signature arm. Regenerate `derived/mthds_schema.json` via `pipelex-dev generate-mthds-schema`. **This is the subtlest piece — verify the Taplo/editor lint accepts a typeless section and still rejects a typo'd type.**
- **Pretty rendering** — `pipe_signature_spec.py` `rendered_pretty` prints `Type: PipeSignature (...)`. Reword to present it as a signature without a type line (e.g. "Signature (contract only)").
- **Fixtures** — 8 bundle files under `tests/e2e/` write `type = "PipeSignature"`; delete the line from each. They double as the regression corpus for "typeless ⟹ signature."
- **Tests** — add: typeless section parses to `PipeSignatureBlueprint`; typeless-with-`prompt` raises the teaching error; explicit `type = "PipeSignature"` raises the migration error; reconciliation of a typeless header against a typed definition still collapses. Existing signature tests (`tests/unit|integration|e2e/.../pipe_signature/`) update to the new surface.
- **Docs** — `docs/building-methods/pipes/signature-pipes.md`, `docs/building-methods/pipes/index.md`, `docs/tools/cli/validate.md`, `docs/tools/cli/agent-cli.md`, error pages, and `pipelex/cli/agent_cli/CLAUDE.md`: teach "omit the type" instead of "set `type = PipeSignature`."

## Migration

Per the workspace "no backward compatibility" rule, we do **not** keep `type = "PipeSignature"` as a silent alias. We reject it — but with a friendly, one-line migration error so anyone with an old bundle knows exactly what to do:

> `PipeSignature` is no longer a pipe type. Delete the `type` line — a pipe with no type and no implementation is a signature.

Same for the spec layer. All in-repo fixtures are migrated in this change, so nothing internal breaks.

## Cross-repo ripple (gated, not in this change)

The MTHDS JSON Schema is copied into downstream repos (`mthds`, `vscode-pipelex`, `mthds-ui`) — see the `mthds-schema-sync` skill. The schema shape changes here (signature arm no longer requires `type`), so those copies drift. That propagation is **gated on a released pipelex version** and handled by the schema-sync skill, not folded into this branch. Flag it in the changelog as a schema change.

## Decisions (settled)

**D1 — Scope: signatures only.** `type` is optional *only* for the signature case. Concrete pipes keep explicit `type`. No inference from fields — it isn't even possible reliably (`prompt` ⟹ PipeLLM *or* PipeImgGen).

**D2 — Typeless + non-contract field = hard error, no leniency.** The only legal typeless shape is exactly a contract (`description`, `inputs`, `output`, `signature_for`). Any other field is a hard error with a teaching message that does **not** guess a type.

**D3 — Explicit `type = "PipeSignature"` is rejected** with a one-line migration error (per the no-backcompat rule). No transitional alias.

**D4 — Keep `signature_for`.** The optional hint stays — harmless, orthogonal, useful to agents.

## Remaining risk to watch during implementation

The JSON-Schema arm (Draft-4, no discriminator) is the one place the disambiguation is non-trivial: the signature arm must omit `type`, forbid extra properties, and still not collide with a typed arm. Verify the editor/Taplo lint (a) accepts a bare `{description, output}` section, (b) rejects a typeless section with a stray field, and (c) rejects a typo'd `type`. Everything else keys off `is_signature` and is mechanical.

## Deferred follow-ups (from the Checkpoint-1 cold review)

**Categorization completeness for a typeless section missing a required contract field.** A typeless `[pipe.x]` whose keys are all contract-legal but that omits a *required* contract field (`description` or `output`) — e.g. a section with only `signature_for`, or an empty stanza — is normalized to a `PipeSignature` and then fails deep in the union with a bare pydantic `type=missing` "Field required" residual at loc `('pipe', <code>, 'PipeSignature', 'output')`. That residual is not matched by any categorizer branch, so it is dropped from the structured `validation_errors[]` (only the raw message survives). The safety invariant still holds — it errors, it is never silently accepted as a mock, and the missing field is named in the raw message (pinned by `test_typeless_section_missing_required_contract_field_still_errors`). This is a **pre-existing, general** gap, not introduced here: a concrete `PipeLLM` missing `output` produces the identical uncategorized residual today. Fixing it properly means a general categorizer branch for pydantic `type=missing` / `extra_forbidden` errors under a `('pipe', <code>, …)` loc (recover `pipe_code` from `loc[1]`, the field from `loc[-1]`), which also changes categorization for concrete pipes — a broader change that deserves its own scoped commit and tests, not this signature-feature change.
