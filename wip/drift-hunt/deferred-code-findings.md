# Drift Hunt — deferred code findings

Defects the hunt surfaced whose fix belongs in **code**, not docs (Louis' Checkpoint 0 ruling, 2026-07-12: doc-side these are fine; code-side issues get deferred here rather than fixed mid-campaign). One entry per finding; pick these up as ordinary follow-ups after the campaign (or sooner if one becomes pressing).

## 1. `pipelex validate` shortcut forms are invisible in `--help`

**Found:** Stage 0, via the CLI pre-screen near-miss (see `suspects.md` FP pattern 8).

**Behavior:** `pipelex/cli/commands/validate/app.py` defines a custom click group whose `parse_args` rewrites `pipelex validate <pipe_code>` and `pipelex validate --all …` into `pipelex validate pipe …` — but the `--help`/`-h` path deliberately bypasses the rewrite, and the group's help output lists only the `method`/`pipe`/`bundle` subcommands with no mention of the shortcut. `docs/tools/cli/validate.md` documents the shortcut; the CLI's own help contradicts it.

**Why it matters:** any consumer that derives the command surface from `--help` (a human skimming, an agent, tooling like the hunt's pre-screen) concludes the documented forms are dead. That's exactly the false "confirmed defect" Stage 0 produced before live execution disproved it.

**Candidate fix (code):** surface the shortcut in the group help — e.g. an epilog/help line on the `validate` group ("`pipelex validate [PIPE_CODE|--all]` is a shortcut for `validate pipe …`"), or expose the forwarded options on the group so `--help` lists them. Keep the rewrite semantics unchanged; this is a help-surface fix only. Update `docs/tools/cli/validate.md` only if the chosen wording changes the documented contract.

## 2. `plxt lint` does not detect invalid concept references (cross-repo: `vscode-pipelex`)

**Found:** Stage 1 Part 3, as the code side of finding F10 (`docs/features/plxt.md:24`).

**Behavior:** `plxt lint` (v0.6.0) is a pure JSON-Schema structural validation pass (required / type / enum / additionalProperties) plus a type-discriminated per-pipe-blueprint check. There is **no cross-reference resolution step**, so a `.mthds` file referencing a concept that was never declared lints **clean**: `output = "NonExistentConcept"` → exit 0, no diagnostics; `inputs = { topic = "TotallyMadeUpConcept" }` → exit 0. (Control: an unknown *pipe type* IS caught — `error[schema]: "UnknownPipeType" is not one of [...]`, exit 1.) The only concept-reference resolution in the toolchain is `crates/taplo-lsp/src/handlers/mthds_resolution.rs`, which is LSP-only (hover / goto-definition) and emits no diagnostic; `taplo-lsp/src/diagnostics.rs` has no concept logic at all.

**Why it matters:** it is a capability gap, not a bug — but the docs promised it, which is what makes it worth recording. Undefined concept references are caught today only by `pipelex validate`, i.e. only once a human/agent reaches for the runtime. A fast, editor-time diagnostic is exactly what the linter is for.

**Doc-side (in scope, Stage 2):** drop "or invalid concept references" from `docs/features/plxt.md:24` — the claim is currently false. That fix stands on its own and does **not** depend on the code side.

**Candidate fix (code, other repo — `vscode-pipelex`):** add a concept cross-reference resolution pass to the lint path, reusing the resolution logic that already exists for the LSP, and surface it as a diagnostic in both `plxt lint` and the LSP. Out of scope for this campaign (D8: another repo's code); hand off to the toolchain owner. If the team decides `plxt lint` should stay purely structural, then the doc fix is the *whole* fix — and that is a legitimate outcome.

## 3. `GatewayTelemetryManagerInjectedError`'s message names config fields that do not exist

**Found:** Stage 1 Part 4, as a byproduct of the false-negative hand-check on `docs/setup/telemetry.md` (the page itself is clean — this defect is in an error string, not in the docs).

**Behavior:** `pipelex/system/pipelex_service/exceptions.py:126-134` builds a remediation message telling the user to configure `host`, `project_api_key`, `langfuse_enabled`, `otlp_endpoint` and `otlp_headers`. **None of those field names exist** in the telemetry config models. The real names are `endpoint` and `api_key` (`PostHogConfig`, `telemetry_config.py:77-96`), `enabled` (`LangfuseConfig`, `:107-115`), and `endpoint` / `headers` on the `[[otlp]]` table.

**Why it matters:** this is the error a user hits when telemetry is misconfigured — the one moment the message is load-bearing. Every key it hands them is wrong, so following it verbatim cannot work. It is the mirror image of doc drift (the docs are right; the *code's own* user-facing text is stale), and no docs fix can reach it.

**Candidate fix (code):** rewrite the message against the current field names, and ideally derive them from the pydantic models rather than restating them, so the message cannot drift again.

## 4. `ImageRenderable` docstring attributes the field-iterating implementation to the wrong class

**Found:** Stage 2, batch S2-3, while fixing finding F33 of `docs/under-the-hood/stuffartefact-and-image-rendering.md` (the doc-side fix is applied; this is the same stale attribution living in code).

**Behavior:** the docstring in `pipelex/tools/jinja2/image_renderable.py:29` still says "StuffContent (base): iterates model fields" — but `StuffContent` has no `render_with_images`; the field-iterating implementation lives on `StructuredContent` (`pipelex/core/stuffs/structured_content.py:52-71`), and a plain `StuffContent` subclass does not satisfy the protocol.

**Why it matters:** the docstring is the first thing a contributor reads when implementing the protocol; it steers them to override the wrong base class — exactly the mistake the doc page used to teach before F33 was fixed.

**Candidate fix (code):** correct the docstring line to name `StructuredContent`. One-line comment fix; deferred only because Stage 2 is docs-only (D17).

## 5. Two docstrings still name `OrchestratorProtocol.run` after the `execute` rename

**Found:** Stage 2, batch S2-3, by the blind post-fix review of the batch commit (the doc-side rename — finding F27 — is fully applied; these are the same stale name living in code comments).

**Behavior:** `pipelex/runtime_bridge/delivery_mode.py:6` ("Delivery is passed as a parameter to ``OrchestratorProtocol.run``") and `pipelex/plugins/bundle_validator_registry.py:54` ("unlike ``OrchestratorProtocol.run``") both reference the protocol's blocking method by its old name; the method is `execute` (`pipelex/plugins/orchestrator_registry.py:38`).

**Why it matters:** these docstrings describe the SPI seam an out-of-tree orchestrator plugin compiles against — the exact audience the F27 page-wide doc rename was fixed for.

**Candidate fix (code):** rename both references to `OrchestratorProtocol.execute`. Two one-line comment fixes; deferred only because Stage 2 is docs-only (D17).

## 6. CSV codec accepts `datetime` fields but its own error message, docstring, and tests omit the type

**Found:** Stage 2, batch S2-1, as the code side of fix-time finding F52 on `docs/building-methods/pipes/csv-input-and-output.md` (the doc-side fix — adding `datetime` to the accepted flat types — is applied; it was verified to round-trip live).

**Behavior:** the flatness classifier accepts `datetime` — `pipelex/tools/tabular/csv_codec.py:52` `_FLAT_SCALAR_TYPES = frozenset({str, int, float, bool, date, datetime})` — and a `datetime`-typed field round-trips end-to-end (ISO string in via pydantic lax coercion at `:364`, identical ISO string out via `model_dump(mode="json")` at `:402`). But the `CsvFlatnessError` message (`:104-108`) and the `flat_field_names` docstring (`:97`) both enumerate only text/integer/number/boolean/date, and `tests/unit/pipelex/tools/tabular/test_csv_codec.py` has zero `datetime` coverage (only `date`).

**Why it matters:** the codec's own user-facing error text contradicts what the codec accepts, and the doc page's "contract is pinned by tests" claim is not yet true for `datetime` — the coercion table on that page deliberately omits a `datetime` row until tests pin it.

**Candidate fix (code):** decide whether `datetime` is intended-supported. If yes (the classifier comment "Scalar python types a CSV cell can round-trip" suggests so): add it to the error message + docstring enumerations and pin the round trip with tests (then the doc's coercion table can gain its row). If no: remove `datetime` from `_FLAT_SCALAR_TYPES` — and revert the doc bullet.

## 7. String-declared concepts drop their `refines` while basic-blueprint concepts keep `refines="native.Text"`

**Found:** Stage 2, batch S2-1, by the adversarial verifier of fix-time finding F53 while pinning down accurate replacement wording for "native Text concepts" on `docs/building-methods/pipes/index.md`.

**Behavior:** a concept declared as a plain string goes through `ConceptDeclarationType.STRING` → `_handle_basic_blueprint`, which generates a Text-based structure class — but the STRING branch discards the returned refine string and builds the `Concept` with `refines=None` (`pipelex/core/concepts/concept_factory.py:511-523`), whereas the BASIC_BLUEPRINT branch keeps `refines="native.Text"` (`:527-537`). Two spellings of the same declaration produce concepts with different `refines` metadata.

**Why it matters:** anything that branches on `refines` (compatibility checks, tooling, future docs) sees an inconsistency between equivalent declarations. No doc claim currently hinges on it — recorded so the asymmetry is a decision, not an accident.

**Candidate fix (code):** make the STRING branch keep the same `refines` the BASIC_BLUEPRINT branch records (or document why the asymmetry is intended).
