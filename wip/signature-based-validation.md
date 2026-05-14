# Signature-Based Validation for Partially-Defined Pipelines

Status: Design v2. Committed to Option A (signatures as first-class pipe type across all three layers). No code yet.

## Goal

Today, validating a bundle dry-runs every pipe with mock inputs. Dry-run requires every sub-pipe of every controller to exist as a fully-defined pipe — there is no way to validate a half-built pipeline.

We want to support `PipeSignature` (already defined in `pipelex/builder/pipe/pipe_signature.py`) as a first-class pipe type that any pipe in a bundle can use as a placeholder. A signature is a contract — inputs, output, type, description — with no implementation.

Use cases:

- AI agents iteratively building pipelines (sketch the orchestration with signatures, fill implementations one pipe at a time, validate at every step).
- Library authors publishing contract bundles for downstream implementation.
- Refactors stubbing out a pipe with its prior contract while the body is rewritten.

## Two validation modes

This is the most important structural decision. Validation has two distinct purposes and they need two distinct modes.

### Strict validation (default)

Fails fast if **any pipe reachable from the target is a `PipeSignature`**. This is the "ready to run in production" semantic. No signatures, no half-builds, no surprises at live-run time.

- `pipelex validate <pipe>` — strict; walks dependency graph from `<pipe>`.
- `pipelex validate --all` — strict; iterates every **non-signature** pipe in the library and runs each one's strict pre-check. (Orphan signatures with no callers don't trigger failures — see open questions.)

Implementation: before any dry-run starts, walk the dependency graph from the target and collect every reachable `is_signature` pipe. If any are found, raise `SignaturesNotAllowedError` listing them with the dep-chain that reached each one and the suggested fix (replace with a real implementation, or re-run with `--allow-signatures`).

### Lenient validation (`--allow-signatures`)

Accepts signatures. They participate in dry-run by minting mock outputs from their declared contract. Used during authoring and agent flows.

- `pipelex validate <pipe> --allow-signatures`
- `pipelex validate --all --allow-signatures`
- `pipelex-agent validate <pipe>` — lenient by default; this is exactly the agent use case.

Implementation: skip the strict pre-check; dry-run proceeds; signatures produce mock outputs via their `_dry_run_pipe`.

### Why two modes and not one

A single "try to detect intent" mode is fragile. CI pipelines, release gates, and production deploys must reject signature-laden bundles. Authoring loops must accept them. The flag is the contract.

The two modes are complementary, not redundant, with live-run safety:

- **Strict mode** is pre-flight: catches signatures before any execution attempt.
- **Live-run error** is runtime enforcement: `_live_run_pipe` on a signature raises `PipeSignatureNotExecutableError`. Even if strict validation is skipped (or a signature is added between validate and run), live execution fails loudly.

## Architecture (Option A)

Three layers, parallel additions:

```
spec/builder    PipeSignature          ← already defined; needs fixes (below)
blueprint/core  PipeSignatureBlueprint
runtime         PipeSignatureRuntime : PipeAbstract
```

New enum values: `PipeType.PIPE_SIGNATURE = "PipeSignature"`, `PipeCategory.PIPE_SIGNATURE`. The discriminator on `PipeSpecUnion` / `PipeBlueprintUnion` stays `type` — no machinery changes.

Why a third pipe category and not "operator" or "controller": signatures aren't operators (no inference) and aren't controllers (no sub-pipe orchestration). A separate category surfaces them cleanly in tooling, reporting, and the `is_signature` property — and the exhaustive-match rule for enums forces all match-cases to acknowledge the new value (which is a feature: linter catches every place that needs to know).

The factory lookup convention (`f"{pipe_type.value}Factory"` in `PipeFactory.make_from_blueprint`) requires no dispatch changes — just register `PipeSignatureFactory`.

## PipeSignature corrections

Three fixes to the existing class before it can fill this role:

### 1. `type` field becomes a literal discriminator

Today it accepts any `PipeType` value (e.g. `"PipeLLM"`). Under Option A, the discriminator must be `Literal["PipeSignature"]`. Move the "intended downstream type" (what the signature will become when implemented) to a separate optional hint field `signature_for: PipeType | None`. This separates the discriminator role from the agent-authoring hint role; otherwise a `PipeSignature` with `type="PipeLLM"` collides with `PipeLLMSpec.type="PipeLLM"` on the union discriminator.

### 2. Input multiplicity allowed

The current description forbids multiplicity brackets in `inputs`. That's a real expressivity gap — `Document[]` and `Image[3]` are common. Reuse `PipeSpec.validate_inputs` so signatures support the same input grammar as real pipes.

### 3. Remove `result`

In Pipelex today the output name is caller-assigned (`SubPipeSpec.result` / `SubPipeBlueprint.result` / `SubPipe.output_name`). A `result` on the pipe contract itself departs from that model — either as a hard rule (breaks caller-assigns-name) or as a soft hint (adds a field nobody enforces). Neither is worth the surface area.

Drop the field. The signature contract is `code`, `type`, `description`, `inputs`, `output`, `signature_for`, `pipe_dependencies` — that's enough.

## Dry-run path for signatures

`PipeSignatureRuntime._dry_run_pipe` does exactly one thing: mint a `Stuff` of the declared output concept and multiplicity, named by the caller's `output_name`, written into `working_memory`. No content generator, no LLM-mock, no image-mock — just `WorkingMemoryFactory.make_mock_content` (which already handles all concept structure classes via `DryRunFactory`).

`needed_inputs()` returns the declared inputs verbatim. `required_variables()` returns the set of declared input names — no dotted-path expansion since signatures have no prompt or template to reference nested attrs from. `validate_inputs_static`, `validate_inputs_with_library`, `validate_output_static`, `validate_output_with_library` are no-ops.

`_live_run_pipe` raises `PipeSignatureNotExecutableError` with a message identifying the pipe's ref and recommending replacement.

## Strict pre-check: signature detection across the graph

Add `is_signature` to `PipeAbstract` (mirrors `is_controller`):

```python
@property
def is_signature(self) -> bool:
    return PipeCategory(self.pipe_category) is PipeCategory.PIPE_SIGNATURE
```

The `PipeCategory.is_controller` match must be updated for the new value (linter will catch this).

Promote `pipe_dependencies` to `PipeAbstract` with an empty default (matches the blueprint layer's design):

```python
def pipe_dependencies(self) -> set[str]:
    return set()
```

`PipeController` retains its abstract override.

Add a graph walk:

```python
def collect_signature_refs(self, visited: set[str] | None = None) -> set[str]:
    """Walk dependency graph; return pipe_refs of all signatures reachable from self."""
    visited = visited if visited is not None else set()
    if self.pipe_ref in visited:
        return set()
    visited.add(self.pipe_ref)

    found: set[str] = set()
    if self.is_signature:
        found.add(self.pipe_ref)

    for dep_code in self.pipe_dependencies():
        sub_pipe = get_optional_pipe(pipe_code=dep_code)
        if sub_pipe is not None:
            found |= sub_pipe.collect_signature_refs(visited)
    return found
```

Strict-mode entry point in `dry_run_pipe`:

```python
async def dry_run_pipe(
    pipe: PipeAbstract,
    *,
    allow_signatures: bool = False,
    raise_on_failure: bool = False,
) -> DryRunOutput:
    if not allow_signatures:
        sig_refs = pipe.collect_signature_refs()
        if sig_refs:
            raise SignaturesNotAllowedError(pipe_ref=pipe.pipe_ref, signature_refs=sig_refs)
    # ... existing logic
```

`validate_bundle`, `dry_run_pipes`, and the CLI thread `allow_signatures` down. Default is `False` everywhere except the agent CLI defaults.

Error UX: `SignaturesNotAllowedError` includes per-signature dependency paths so the user sees not just "X is a signature" but "X is a signature; reached via `seq.step[2]` of `top_pipe`."

## Validation surface — what changes and what doesn't

- `PipelexBundleBlueprint.validate_local_pipe_references`: unchanged. It checks key presence; a signature entry counts as declared.
- `PipeAbstract.generic_validate_inputs_static`: unchanged. `needed_inputs()` equals declared inputs for a signature; the tautology passes.
- `PipeSequence.validate_output_with_library`: unchanged. Reads last step's `output` concept; the signature reports its declared output.
- `PipeFactory.make_from_blueprint`: gains one registered factory via the existing convention.
- `dry_run_pipe`, `dry_run_pipes`, `validate_bundle`, `validate_bundles_from_directory`, CLI entry points: gain `allow_signatures` parameter.

## Live-run behavior

Live execution reaches a signature, calls `run_pipe`, dispatches to `_live_run_pipe`, raises `PipeSignatureNotExecutableError`. The error propagates through controllers and the runner, ending up wrapped in `PipelineExecutionError` with the signature's `pipe_ref` and the calling pipe stack.

This is the desired behavior: live execution of a half-built pipeline must fail loudly. No best-effort, no silent mock fallback.

## Phase plan

### Phase 1 — Type system foundations

- `PipeType.PIPE_SIGNATURE`, `PipeCategory.PIPE_SIGNATURE`. Update `PipeType.category` match and `PipeCategory.is_controller` match.
- `is_signature` property on `PipeAbstract` and on `PipeBlueprint`.
- Promote `pipe_dependencies` to `PipeAbstract` with empty default.

### Phase 2 — Blueprint and runtime

- `PipeSignatureBlueprint(PipeBlueprint)`: literal type, optional `signature_for`, optional `pipe_dependencies` metadata.
- `PipeSignatureRuntime(PipeAbstract)`: no-op validators; `needed_inputs()` returns declared; `_live_run_pipe` raises; `_dry_run_pipe` mints via `WorkingMemoryFactory.make_mock_content`.
- `PipeSignatureFactory(PipeFactoryProtocol)`.
- Add to `PipeBlueprintUnion`.

### Phase 3 — Spec layer

- Fix `PipeSignature` per corrections above (literal `type`, multiplicity in inputs, drop `result`).
- Add `to_blueprint()` returning `PipeSignatureBlueprint`.
- Add to `PipeSpecUnion` and `pipe_type_to_spec_class`.

### Phase 4 — Strict pre-check

- `PipeAbstract.collect_signature_refs(visited=None)`.
- `SignaturesNotAllowedError` with pipe_ref, signature_refs, and dep-path map.
- Thread `allow_signatures: bool` through `dry_run_pipe`, `dry_run_pipes`, `validate_bundle`, `validate_bundles_from_directory`.

### Phase 5 — CLI surface

- `pipelex validate <pipe> [--allow-signatures]`, `pipelex validate --all [--allow-signatures]`.
- `pipelex-agent validate` defaults to `allow_signatures=True` (verify against the agent CLI's existing semantics first).
- Summary line surfaces signature count when lenient.

### Phase 6 — Tests

Strict mode:

- Pipeline with no signatures → strict passes.
- Pipeline with signature anywhere in dep graph → strict fails with all signatures listed and dep paths shown.
- `--all` strict: orphan signature in library doesn't trigger failure (no caller); signature reached by any non-signature pipe does.

Lenient mode:

- Signature-only bundle: validate passes; live-run fails clearly.
- Signature inside PipeSequence step (multiplicity match on output concept).
- Signature inside PipeParallel with `add_each_output`.
- Signature inside PipeBatch — list output flows up.
- Signature with `Document[]` and `Image[3]` inputs.
- Signature with `Dynamic` output → mock falls back to TextContent.
- Mixed bundle: agent replaces signature with real pipe → re-validate.
- Cross-package signature.
- Cycle: signatures listing each other in `pipe_dependencies` don't cause re-entry.

Schema:

- `pipelex-dev generate-mthds-schema` includes `PipeSignature` as a valid pipe-table entry.

### Phase 7 — Docs

- MTHDS docs page for the signature pipe type.
- CLI help text for both modes.
- Comparison table: strict vs lenient.

## Compromises and tradeoffs

- **MTHDS surface grows.** A new pipe type is now visible to authors. Mitigation: keep `PipeSignature` deliberately minimal so it reads as obviously-a-contract.
- **Strict-validation gate must be wired at every entry.** Easy to miss a code path that calls `dry_run_pipe` directly without threading the flag. Default `allow_signatures=False` guards against most misses; tests cover the rest.
- **Mock fidelity has limits.** A signature describes structure, not values. Downstream PipeLLMs whose prompts reference specific content shapes inside the signature's output may dry-run successfully but fail live. This is the same limitation that already affects DRY mode generally.
- **`required_variables` loses dotted-path info.** Signatures have no prompt/template and can't express "I require `foo.bar.baz`." When a signature stands in for a real pipe, deep variable paths aren't visible upstream. Acceptable for the target use cases.
- **No signature mode for concepts.** Concepts still need full definitions. Signature-concepts is a much bigger design and out of scope.
- **`--all` skips signatures.** A signature with no caller is not flagged by `pipelex validate --all`. The strict pre-check on every reachable pipe is the catch-net; an orphan signature is a deliberate placeholder, not an error.

## Open questions

- Should `signature_for` influence dry-run mocking? (e.g. `signature_for = "PipeImgGen"` mints an `ImageContent` URL mock instead of a generic structure mock.) Probably yes for image generation specifically — image structure mocks via `DryRunFactory` aren't useful without a real URL. Defer until phase-2 usage shows it matters.
- Subcommand vs flag for lenient mode: `pipelex validate-draft <pipe>` or `pipelex validate <pipe> --draft`? Flag is simpler; subcommand reads clearer in CI logs. Either works. Lean toward `--allow-signatures` flag for consistency with how other "permissive" options are surfaced.
- Strict `--all` and orphan signatures: confirm that "iterate non-signature pipes only" is the right semantic. Alternative: include signatures in `--all` but mark them as trivially-passed (signature-consistency check at bundle load is the only thing that runs). Lean toward skipping in iteration; bundle-load validation is the right place for signature-shape checks.

## Rejected alternatives (for the record)

- **Compile signatures to PipeFunc at load time.** Layering violation; signatures lose identity at the runtime layer; live execution would silently succeed with mock data.
- **Parallel `signature` table in `.mthds` alongside `pipe`.** Two resolution paths inside controllers; awkward cross-references. Possibly retrofittable as syntactic sugar over Option A later; not a structural alternative.
- **Implicit "skeletal" pipes** (PipeLLM with no prompt = signature). Ambiguous; bug-vs-feature can't be distinguished from field presence.
