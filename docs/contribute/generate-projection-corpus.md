# Generating the Projection Fixture Corpus

The MTHDS build routes no longer render a pipe's fill-in inputs template on the server. Each client SDK projects it from the input-form descriptor it already has — once in TypeScript (`mthds`) and once in Python (`mthds-python`) — and the two projections must agree **exactly**, TOML comment lines included, or the JS/Python asymmetry the change set out to remove is simply rebuilt one layer up.

`pipelex-dev generate-projection-corpus` writes the fixture corpus that makes that agreement checkable. It is the **sole producer** of the capture committed byte-identically in `mthds-js/tests/fixtures/protocol/` and `mthds-python/tests/fixtures/protocol/`; `trace-input-semantics` stays what its own page says it is, a debugging tracer.

```bash
.venv/bin/pipelex-dev generate-projection-corpus \
  tests/data/input_semantics/hinted_bundle.mthds \
  tests/data/input_semantics/probe_bundle.mthds \
  tests/data/input_semantics/scaffold_bundle.mthds \
  -o /tmp/projection-corpus
```

Bundle order is part of the capture: it fixes the key order of every emitted map, so pass the bundles exactly as the corpus README in each consumer repo records them. Adding a bundle at the end keeps the existing bytes stable; inserting one in the middle rewrites the whole capture.

## What it writes

- `input_form.json` and `pipe_io_contracts.json` — the descriptor and contract capture, keyed by namespaced `pipe_ref`. Byte for byte what `trace-input-semantics` dumps at hop 5, so migrating the existing committed copies to this command is a no-op diff.
- `inputs_template/<pipe_ref>.<shape>.<format>` — the **expected** template each projection must produce, in both shapes (`compact`, `explicit`) and both formats (`json`, `toml`).
- `inputs_template/manifest.json` — what the corpus covers (bundles, pipes, shapes, formats) plus the declared divergences, each with worked sites a consumer repo can check with no engine present.
- `engine/` — the engine's own renderings of the same pipes. **Not committed.** It is what the divergence record is measured against, not part of the contract.

## Where the expectation comes from

The expected templates are not the engine's output. They come from the reference projection in `pipelex/cli/dev_cli/commands/projection_reference.py`, which walks the **descriptor** — the authored facts a method states — where the engine's renderer (`pipelex/pipe_machinery/rendering/input_renderer.py`) reflects the **runtime content classes**. That is the whole design: the shipped projections have only the descriptor, so the contract has to be authored from the descriptor too.

The reference projection lives in the dev CLI rather than in the runtime because nothing in `pipelex` consumes it. Its only job is to author the corpus bytes.

## The divergence record

Where the two disagree, the difference is **declared, never discovered**. The generator classifies every difference between its own rendering and the engine's, and fails if it meets one it has no declaration for — or if a declared class no longer occurs, so an engine fix retires its entry deliberately instead of leaving the manifest claiming a difference that has gone.

The classes it declares today:

- `optional-field-included` — the engine passes `include_optional=False` at the top of an input's own structure class and not through the recursion, so it hides an optional field at depth one and shows one nested deeper. The projection renders every field the descriptor states, at every depth.
- `file-leaf-not-expanded` — the descriptor states a file-ish node as a leaf whose only fill-in value is a URL; the engine expands the runtime content class and asks whoever fills the template in for a width, a mime type and a caption.
- `fixed-count-honoured` — a `Concept[N]` slot renders `N` elements. The engine emits one whatever the count, and `InputShaper` then rejects that template with `MultiplicityCountMismatchError`, so the scaffold it produced does not run.
- `text-named-url` — the engine picks a placeholder by field **name**, so a text field merely named `url` renders as a URL. The projection reads the descriptor's `kind`.
- `scalar-vs-structured-native` — a native carrying an optional field beside its required one (`native.Date`) no longer collapses to a single-key content once the optional field is rendered, so it stays an object where the engine unwrapped it to a bare scalar. A consequence of `optional-field-included`.

Each is a `pipelex` defect filed in the workspace ledger, not a difference of taste; the manifest is what records that the corpus knowingly departs from the engine and why.

## The bundles

`tests/data/input_semantics/` holds the corpus bundles. `probe_bundle.mthds` exercises every construct the language accepts and `hinted_bundle.mthds` the intent hints; `scaffold_bundle.mthds` was added for this corpus and covers what the other two do not — a text field merely named `url` beside a real file position, an optional nested structure, optional `native.Image` and `native.Document` fields inside a structure, and both a fixed `[N]` and a variable `[]` slot over a structured concept.

## When to rerun it

Rerun and re-commit the capture in both consumer repos whenever the descriptor derivation changes, a `kind` is added to the standard, or a bundle changes. The per-repo harness asserts that the set of kinds appearing across the corpus **equals** the closed `FieldKind` vocabulary, so a kind added without a fixture fails by name rather than passing silently.

`tests/unit/pipelex/cli/dev_cli/test_generate_projection_corpus.py` keeps the capture complete and byte-stable, and `test_projection_reference.py` pins the projection's rules one at a time, so a rule that changed fails by name instead of as a wall of differing bytes.
