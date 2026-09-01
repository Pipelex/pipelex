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
- `inputs_template/manifest.json` — what the corpus covers (bundles, pipes, shapes, formats), the declared divergences, each with worked sites a consumer repo can check with no engine present, and the templates the input shaper refuses to take back.
- `engine/` — the engine's own renderings of the same pipes. **Not committed.** It is what the divergence record is measured against, not part of the contract.

A pipe declaring no inputs is captured from the projection alone: an empty input form is a valid form and the projection renders it as `{}` (an empty TOML document), but the engine's renderer refuses one with `NoInputsRequiredError`, so that pipe gets its templates and no `engine/` file, and nothing is compared for it.

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
- `object-native-keeps-envelope` — a native carrying an optional field beside its required one (`native.Date`) renders as an object once the optional field is included, and the shaper's bare-value arm dispatches a native on its scalar kind, so the object form is only re-shapable inside its `{concept, content}` envelope. The projection keeps that envelope; the engine unwraps to a bare scalar, which it can only do because it drops the optional field. A consequence of `optional-field-included`.
- `unknown-empty-object` — an `unknown` node renders as the empty object, because the descriptor withholds the payload shape at that position and a projection that invented one would stop projecting the descriptor. The engine reflects the runtime content class instead and fills a required dict with a sample key/value pair whoever fills the template in has to delete. Reached by `json_obj` inside `native.JSON`, the corpus's first *required* dict; the optional dict fields elsewhere never reach it, because the engine drops those entirely and that is `optional-field-included`.

Most are `pipelex` defects filed in the workspace ledger rather than differences of taste, and the manifest names the item whose fix would retire each one. Some carry no item, deliberately: `file-leaf-not-expanded` and `unknown-empty-object` are the descriptor's vantage rather than engine bugs, and `object-native-keeps-envelope` is a consequence of `optional-field-included` rather than a defect of its own. The manifest is what records that the corpus knowingly departs from the engine, and why.

### What the gate can and cannot separate

The walk visits both sides' keys, so a field the projection *stopped* rendering is a difference like any other — it is recorded under an id with no entry in `DIVERGENCE_REASONS`, which makes the capture refuse rather than pass silently. Beyond that, each arm classifies on the two values' shapes plus one descriptor fact the shapes cannot supply: the declared `item_count` of a fixed-count slot. So `fixed-count-honoured` means the slot's declared count was met, not merely that the projection rendered more elements than the engine's one; a variable `[]` slot rendering two, or a `[2]` slot rendering four, is unclassified and fails the capture. Likewise the file-leaf arm compares the URL both sides carry instead of returning on the expansion alone.

What it still cannot separate is a *wrong value at a site that already carries a class*: a projection inventing a field reads as `optional-field-included`, and a garbled placeholder at a url-named text field reads as `text-named-url`. Telling those apart needs each node's kind and presence carried through the whole walk, which is a redesign rather than a fix, and the two shipped projections are pinned against the committed bytes anyway.

## The shaping round-trip

A fill-in template exists to be filled in and handed back to the runtime, so surviving `InputShaper.shape` is part of what the corpus asserts — and until this gate existed, nothing checked it. Twice the corpus pinned slots the runtime rejects outright, and both times a human review round caught it rather than the capture; the second time the divergence gate absorbed the broken sites into a declared class and exited 0, because "differs from the engine" and "the engine refuses this value" are not the same question.

So every projected template goes straight back through the shaper, assembled exactly as an entry-pipe run assembles it: the pipe's own declared inputs as the signature, its domain as the search scope. Both shapes, both pipes' worth — the explicit template is as much a runnable scaffold as the compact one. The round-trip is offline: the file-ish arms wrap a mock URL without fetching it.

The verdict follows the same declared-never-discovered discipline as the divergence record, through the `EXPECTED_UNSHAPEABLE` registry in `generate_projection_corpus_cmd.py`, which maps a `(pipe_ref, shape)` to the ledger item tracking the gap:

- A refusal **not** in the registry fails the command, naming the pipe, the shape, the error class and the error's first line. This is the mechanism that would have caught both prior escapes at capture time.
- A registry entry whose template **now shapes** fails the command too — *delete the entry, the gap closed* — so a fix retires its declaration deliberately rather than leaving the manifest claiming a defect that no longer exists.
- A registry entry this capture **never walked at all** fails it as well, and is worded apart from the one above because the two call for opposite actions: a key addressing no pipe and shape the run produced is a renamed pipe or a run over a subset of the bundles, so it wants re-keying or the full bundle list — deleting it would drop a gap that is still open.
- A declared entry is recorded in the manifest as an `unshapeable` entry (`pipe_ref`, `shape`, `error_type`, `ledger_item`) and printed, and generation proceeds. A known-open gap therefore never blocks the capture; it is simply stated.

The manifest holds the error's **class name**, never its message. The class name is contract-stable — the error-identity snapshot makes a rename a reviewable diff — while the message is wording that would churn these committed bytes across pydantic versions, so it goes to the console and to the refusal only. Passing verdicts are printed as a count, never committed: a template the shaper takes back is the state every entry is working towards, not a fact worth pinning.

The entries declared today are all one descriptor gap — a nested list inside a structure — which takes both shapes of the two probe pipes that reach it. Closing it deletes the four entries; the lapse rule fails the command until somebody does.

## The bundles

`tests/data/input_semantics/` holds the corpus bundles. `probe_bundle.mthds` exercises every construct the language accepts and `hinted_bundle.mthds` the intent hints; `scaffold_bundle.mthds` was added for this corpus and covers what the other two do not — a text field merely named `url` beside a real file position, an optional nested structure, optional `native.Image` and `native.Document` fields inside a structure, and both a fixed `[N]` and a variable `[]` slot over a structured concept. Its `scaffold_open_natives` pipe holds the natives whose payload shape the descriptor states openly, at slot positions: `native.Dynamic` and `native.Composite`, which the standard calls structureless and whose node is therefore `unknown`, beside `native.JSON`, which is not — its pinned blueprint carries a required `json_obj`, so it expands like any other pinned native and its dict is where `unknown-empty-object` is measured.

`native.Anything` belongs in that pipe and is not there yet: an `Anything` input crashes the engine's contract builder, which resolves a structure class for every input and so asks for the one class the standard says does not exist. Its slot coverage waits on `L-260831-8f7c8c`.

## When to rerun it

Rerun and re-commit the capture in both consumer repos whenever the descriptor derivation changes, a `kind` is added to the standard, or a bundle changes. The per-repo harness asserts that the set of kinds appearing across the corpus **equals** the closed `FieldKind` vocabulary, so a kind added without a fixture fails by name rather than passing silently.

`tests/unit/pipelex/cli/dev_cli/test_generate_projection_corpus.py` keeps the capture complete and byte-stable and measures the registry against the real round-trip, `test_projection_divergence_gate.py` and `test_projection_shaping_gate.py` state each gate's guarantee as the regressions it must not absorb, and `test_projection_reference.py` pins the projection's rules one at a time, so a rule that changed fails by name instead of as a wall of differing bytes.
