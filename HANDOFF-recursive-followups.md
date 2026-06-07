# Handoff — recursive-building runtime follow-ups (pipelex)

Two follow-ups on the pipelex side, surfaced during the `mthds-plugins` design review. Both build on the additive multi-file model already shipped on this branch (`feature/Support-recursive-design`; see `TODOS.md` for Parts A + B). Neither blocks the additive model; both make it robust/complete. Independent of each other — land in either order.

Verify after each: `make agent-test` (green) + `make agent-check` (clean).

---

## Task 1 — Expose the unsatisfied-signature set on a successful lenient validate

**Why.** The `mthds-plugins` PostToolUse hook wants a non-blocking "these pipes are still unimplemented" nudge on a *successful* `--allow-signatures` run (design.md §5.2). Today the reachable-signature list is surfaced only on *strict* failure (`SignaturesNotAllowedError`); a lenient success emits no machine-readable list of what remains.

**Key simplification (from Part A).** Once a concrete reconciles with a signature, the signature is *replaced* in the merged library. So "unsatisfied signatures" = exactly the pipes still typed `PipeSignature` in the assembled library. No `{signatures} − {concretes}` arithmetic needed — just enumerate `is_signature` pipes.

**Where.**
- `pipelex/pipeline/validate_bundle.py` — `ValidateBundleResult` (l.39) already carries `pipes: list[PipeAbstract]`. Add a projection next to `build_validated_pipes` (l.57):

  ```python
  def build_pending_signatures(pipes: list[PipeAbstract]) -> list[str]:
      """Qualified refs of pipes still declared as PipeSignature (unsatisfied headers)."""
      return sorted(pipe.pipe_ref for pipe in pipes if pipe.is_signature)
  ```

  (`PipeAbstract.is_signature` and `.pipe_ref` already exist.)
- Surface it on the agent-CLI validate JSON envelope, next to `validated_pipes` — find the surface that calls `build_validated_pipes` (the `pipelex-agent validate bundle` command under `pipelex/cli/agent_cli/.../validate/`). Add a `pending_signatures` array. Mirror on the plain `pipelex validate bundle` command if it emits structured output. A one-line human note on success ("N pipe(s) still PipeSignature: …") is optional.

**Scope nuance — compute from the library, not `result.pipes`.** For the file-path path, when the file is already loaded `result.pipes` is only *that file's* pipes (l.262-265). The hook validates one file at a time but wants the *whole-library* pending set. Compute pending from the assembled library (`library.pipe_library`), not from `result.pipes`, so the answer is library-wide regardless of which file triggered the run.

**Tests.** Lenient validate of a bundle with unsatisfied headers → `pending_signatures` lists them; after every header has a concrete definition → empty. Fold into the additive integration test (`tests/integration/pipelex/libraries/test_additive_multi_file_library.py`).

---

## Task 2 — Proper (normalized) contract conformance, replacing raw-string `contract_equals`

**Why.** `PipeBlueprint.contract_equals` (pipe_blueprint.py:111-120) compares raw strings. But Part B resolves concept refs flexibly (bare ↔ domain-qualified), so a header `output = "Brief"` and a definition `output = "thisdomain.Brief"` denote the *same* concept yet fail `contract_equals` → a false mismatch. Raw-string is not a proper check.

**Scope: normalize for _identity_** — bare↔qualified, whitespace, multiplicity parsed structurally. This is **not** refinement substitutability (covariant output / contravariant inputs); that stays deferred (`mthds-plugins/wip/deferred-issues.md` → "Substitutable contract conformance…").

**Normalization (reuse existing helpers).** For each concept spec:
- Parse multiplicity with `parse_concept_with_multiplicity` (already used in `PipeBlueprint.generic_validate_output`) → `(concept_ref_or_code, multiplicity)`.
- Canonicalize the ref: native (`NativeConceptCode`) → keep the native code; cross-package (`QualifiedRef.has_cross_package_prefix`) → keep; external-domain qualified → keep; bare / same-domain → `ConceptFactory.make_concept_ref_with_domain(domain_code, code)`.
- Compare canonical `(qualified_ref, multiplicity)` tuples: `inputs` as a `name → tuple` dict (`None` ≡ `{}`), `output` as a tuple.

**Domain context.** `contract_equals` lives on the blueprint, which doesn't carry its domain. The caller does: `_reconcile_pipe_collision` (library_crate_factory.py:136) runs inside the merge loop that has `domain_code` (l.59), and both declarations share the domain (same `pipe_ref`). So pass `domain_code` into `_reconcile_pipe_collision` and into the comparison. Suggest a focused free function `pipelex/libraries/contract_match.py::contracts_match(a, b, *, domain_code) -> bool` (mirroring `collision_messages.py` / `concept_reference_validation.py`), and replace the `existing.blueprint.contract_equals(incoming.blueprint)` call at l.166. Retire `contract_equals` or keep it as a thin raw fallback — your call.

**Tests.** Header `Brief` + def `thisdomain.Brief` reconcile; whitespace / multiplicity-spelling variants reconcile; native refs reconcile; genuinely different concepts or differing multiplicity still mismatch. Update any existing exact-match tests that assumed raw-string equality.

**Boundary.** Refinement-aware substitutability stays deferred — see `mthds-plugins/wip/deferred-issues.md`.

---

These two follow-ups are tracked from the design doc: Task 1 backs design.md §5.2/§5.4 (the leftover-signature nudge), Task 2 backs §2.7/§4.5 (the exact-match contract rule, which this upgrades from raw-string to normalized).
