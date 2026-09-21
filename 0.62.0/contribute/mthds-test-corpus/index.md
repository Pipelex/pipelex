# The MTHDS Test Corpus

The MTHDS Test Corpus is one canonical, tagged set of `.mthds` methods that every repo in the workspace draws its language-level fixtures from. It lives at `pipelex/test_extras/mthds_corpus/`, ships in the wheel, and is gated on both sides: the corpus must cover every feature the runtime registers, and each consumer must exercise every entry in the slice it declares.

The cross-repo contract — the one other repos are written against — is the workspace-root spec `docs/specs/mthds-test-corpus.md`. This page is the pipelex-side working guide: where things are, how to add an entry, and what each gate is telling you when it goes red.

!!! note "Why it exists"

    Every repo grew its own pile of `.mthds` fixtures, and coverage of the MTHDS language surface is a cross-repo invariant asserted locally in each of them. The `Time` native concept had no pipelex fixture at all, and mthds-ui had independently patched the same gap in its own corpus. The exhaustivity gate makes that a red build instead of a thing someone has to remember.

## Layout

```
pipelex/test_extras/mthds_corpus/
  vocabulary.toml     generated, committed, ships — the closed tag set
  manifest.py         the strict entry.toml model
  vocabulary.py       the vocabulary reader
  loader.py           iter_entries() / get_entry()
  resources.py        package-data path resolution
  exceptions.py
  entries/
    native_time_departure/
      entry.toml
      bundle.mthds
      inputs.json     optional
```

An entry directory holds either exactly one `.mthds` file, or several with a `bundle.mthds` acting as the entry point — which is exactly what `pipelex validate bundle <dir>` already resolves, so an entry directory is a valid CLI argument as it stands.

## Adding an entry

1. **Pick an ordinary-world subject.** An entry's subject matter is never AI, machine learning, language models, agents, prompting or embeddings, and never MTHDS's own vocabulary either. The corpus *uses* `PipeLLM` constantly; it never *talks about* it. The reason is legibility under failure: an entry exists so a red gate can be narrated in one sentence, and *"the model output the model"* is not a sentence anyone can act on. Train timetables, invoices, recipes, weather observations, shipping manifests all work. The full rule, including the carve-out that lets an invalid entry be named for the defect it triggers, is in the spec.

2. **Create the directory** under `entries/`, named in `snake_case`, and write the bundle.

3. **Write `entry.toml`.** `name` must repeat the directory name; `covers` names the axes the entry exists for and must draw only on tags the vocabulary declares.

    ```toml
    name = "native_time_departure"
    description = "The departure time of day read off a printed timetable line"

    validity = "valid"
    tier = "dry"
    granularity = "focused"

    covers = [
      "native.time",
    ]
    ```

4. **Name no model.** Presets and aliases are resolved by the validation engine, not only at run time, so an entry pinning one fails validation outright on any consumer whose deck does not define it — which turns an entry about a language feature into an entry about model selection. Leave the choice to each consumer's deck.

5. **Validate it locally** — against the local runtime, never the hosted API, which lags it:

    ```bash
    .venv/bin/pipelex validate bundle pipelex/test_extras/mthds_corpus/entries/native_time_departure/
    ```

6. **Run the gates**: `.venv/bin/pytest tests/unit/pipelex/test_extras tests/integration/pipelex/test_extras`.

An **invalid** entry additionally declares the exact wire `error_type` it must produce. Read that string off the runtime rather than inferring it from the source:

```bash
.venv/bin/pipelex-agent validate bundle <path> -L <entry_dir>/ --format json --error-format json
```

Two rules shape an invalid entry beyond that. Its **`covers` list is its `error.*` tag and nothing else** — it is tempting to also tag the pipe kind that carries the fault, but the exhaustivity gate reads `covers` as the claim that a tag has a focused entry, and a deliberately broken bundle must never be what satisfies that claim for a working feature. And the two ways it names its fault have to agree: `expected_error` carries the wire string, `covers` carries the normalized tag, and the exhaustivity gate requires the entry to cover the tag whose `code` is its `expected_error`, so an entry cannot advertise coverage it does not produce. The rule has a second half, gated alongside it: a **valid** entry may not carry an `error.*` tag at all, because its bundle produces no diagnostic and the claim would go unhonoured in exactly the same way.

!!! warning "The `.mthds` editor hook fights invalid entries"

    The `pipelex` plugin's `PostToolUse` hook lints, formats and **blocks on an invalid verdict** for every `Write`/`Edit` of a `.mthds` file, and has no skip mechanism. Author valid entries with the editing tools to collect the free lint; write an invalid entry's bundle through a shell heredoc, which the hook's matcher does not intercept.

    `make lint` and `make format` cover an invalid entry's bundle like any other `.mthds` file in the tree, with one carve-out: `.pipelex/plxt.toml` excludes the corpus's **schema-fault** entries — those whose tag says `fails_at = "schema"` — because a linter reporting them would be reporting the very defect the entry exists to carry, and that list is gated against the vocabulary rather than hand-maintained (see [`fails_at`](#fails_at-which-layer-catches-a-fault-first)). Nothing formats those, so match the layout of the entry next door by hand; every other invalid bundle is formatted for you. Its `entry.toml` is linted normally either way.

## The tag vocabulary

Tags are namespaced and the vocabulary is closed: an entry covering a tag the vocabulary does not declare fails the gate. `native.*` is generated from `NativeConceptCode`. `operator.*` and `controller.*` are generated from `PipeType` — one registry, split by its own `category` property, so a pipe kind added tomorrow lands in the right namespace with nothing to update here. Their local names drop the `Pipe` prefix every code carries, since the namespace already says which half it is: `PipeLLM` becomes `operator.llm`, `PipeSequence` becomes `controller.sequence`. `error.*` is generated from `VALIDATION_ERROR_TYPES`, the closed registry of `error_type` values a validation diagnostic can carry — and it needs no rule of its own even though its registry mixes two spellings: the normalization steps leave an already-snake_case stage code (`missing_input_variable`) untouched and turn the dry-run residual `DryRunError` into `error.dry_run_error`, exactly as they turn `YesNo` into `native.yes_no`.

`feature.*` is the one hand-maintained namespace, because a language feature is a human-named cluster of behaviour rather than a registry entry — some span several blueprint fields (optionals show up as `?` in a concept spec), some none at all (a multi-file library is a property of the entry *directory*), and there is no feature registry in `pipelex` to walk. A tag there carries a `description` where a generated one carries `code`, since that sentence is the only place its meaning can live. **Add a feature tag in the same commit that lands its first covering entry, never ahead of it** — declaring one reds the exhaustivity gate until an entry covers it.

`vocabulary.toml` is generated in full, so it is never edited by hand:

```bash
make generate-corpus-vocabulary
```

Everything the file says is decided in the generator, `pipelex/cli/dev_cli/commands/generate_corpus_vocabulary_cmd.py` — the registries it walks, and every exclusion reason. It is unshipped dev tooling (the wheel excludes `pipelex/cli/dev_cli`) while the file it writes ships, which is what lets a consumer read the closed tag set without a registry walk. The hand-maintained `feature.*` tags are declared in that same file, beside the registry walks — see above for how to add one.

An **exclusion** marks a registry code that no standalone focused entry could meaningfully exercise. It stays in the vocabulary and stays usable by an entry; it is simply not owed a focused entry. The exclusion map is keyed on the registry enum rather than on strings, which is what keeps an exclusion from outliving the code it names: a removed code breaks the generator at import, naming itself.

No native concept is excluded — every one of them turned out to support a real entry. `PipeFunc` is excluded: it names a Python function that the runtime resolves against its function registry *at validation time*, so an entry declaring one fails with `Function '<name>' not found in registry` in every consumer that has not registered that exact function — and a cross-language consumer cannot register a Python function at all. Exercise `PipeFunc` in a consumer's own fixtures, where the function exists.

`error.*` carries the rest of the exclusions, and the distinction they turn on is worth stating: **membership in the registry means a value is reachable on the wire, never that a focused entry can produce it.** A corpus entry is a `.mthds` bundle validated through `validate bundle`, so a fault the validate path cannot reach is excluded here rather than pruned from the runtime's own truth. Two are unreachable by construction — `circular_dependency_error` is raised only by the pipe sorter, which runs on the builder's spec-to-blueprint conversion and never on a parsed `.mthds` file, and `unknown_concept` fires in the pipe factory under exactly the condition the earlier concept-reference resolution has already rejected as `unresolved_concept`. Several have no shape an entry could take: the advisory-only codes — `optional_force_redundant`, `input_presence_vacuous`, and the three `hint_*` lints — ride the validation report's `warnings` array and never make a verdict invalid, so the bundle they fire on is valid and has no `expected_error` to carry, and the manifest models no warnings axis. The two `unknown_*` fallbacks are excluded because an entry pinning one would be pinning the absence of a diagnosis, and would have to be rewritten the moment the fault got a code of its own.

**Measure an exclusion, do not reason your way to one.** Every `error.*` exclusion reason above was established by writing the bundle that ought to trigger it and reading what the runtime actually said — which is how the first two turned out to be shadowed rather than merely awkward, and how the two the registry made look unreachable (`missing_pipe_type`, `native_concept_redeclaration`) turned out to have entries after all.

### `fails_at` — which layer catches a fault first

An `error.*` tag that is *not* excluded carries one more field: `fails_at`, either `schema` or `runtime`. It names the earliest layer of checking that rejects a bundle carrying the fault. `schema` means a pass over the raw document's shape already catches it — a section missing a required key, a value outside a closed set — so a JSON-Schema validator, an editor diagnostic, or `plxt lint` reports it without ever interpreting the document. `runtime` means the document has to be *interpreted* to notice: an unresolved reference, an input the flow never supplies, an output whose concept does not fit.

**The consumer rule is one sentence: a structural sweep expects a diagnostic on an entry exactly when its tag says `fails_at = "schema"`, and expects silence on every other entry.** That is what the field exists for. Before it, a consumer running a schema checker over the corpus had to hardcode which faults it thought were structural — a second, downstream reading of `pipelex`'s own registry, guaranteed to drift from it. Now the corpus being swept carries the answer.

A `schema` fault is still rejected by the runtime; the field names where a fault is caught *first*, not who is allowed to catch it. That is why a schema-fault entry declares the same `expected_error` as any other invalid entry — the runtime's diagnostic is what the entry pins. The two spellings line up on purpose, too: `schema` is also `plxt`'s own `error[schema]` diagnostic category, so a consumer branching on the field and a human reading a linter's output use one word for one thing.

Only non-excluded tags carry it, for the same reason exclusion reasons are measured: an excluded tag has no entry, so there is nothing to have measured on, and a value invented for one would be an argument dressed as a measurement.

**And it stays measured, because this repo consumes it first.** `.pipelex/plxt.toml` excludes the corpus's schema-fault entries from `plxt lint` — they *should* produce a diagnostic, which is the entry's whole point — and lints every other invalid entry like any ordinary `.mthds` file. That exclusion list is not hand-maintained: `tests/unit/pipelex/test_extras/test_mthds_corpus_plxt_exclusions.py` fails when it disagrees with the vocabulary. The config is gated rather than generated because `plxt` is a static binary reading a static file, with nothing to hook a generation step onto — but the loop still closes in the direction that matters. Declare a fault `runtime` when the schema in fact rejects it, and its entry stays linted, so `make plxt-lint` goes red naming it.

## The gates, and what a red one means

| Gate | Where | Red means |
|---|---|---|
| Vocabulary drift | `tests/unit/pipelex/test_extras/test_mthds_corpus_vocabulary.py` | A registry changed and the committed vocabulary was not regenerated. Run `make generate-corpus-vocabulary`. |
| Exhaustivity | `tests/unit/pipelex/test_extras/test_mthds_corpus_exhaustivity.py` | A vocabulary tag has no `focused` entry covering it — write the entry, or record an exclusion with a reason. Also fires when an entry covers a tag that is not in the vocabulary, when an invalid entry's `covers` is not exactly the tag its `expected_error` names, when a valid entry covers an `error.*` tag it cannot produce, and when a required `error.*` tag declares no `fails_at`. |
| Linter exclusions | `tests/unit/pipelex/test_extras/test_mthds_corpus_plxt_exclusions.py` | `.pipelex/plxt.toml`'s corpus exclusions disagree with the vocabulary's `fails_at` signal — an entry whose fault the schema rejects must be excluded, every other invalid entry must be linted. |
| Manifest | `tests/unit/pipelex/test_extras/test_mthds_corpus_manifest.py` | The strict `entry.toml` model rejected something. |
| Layout and filters | `tests/unit/pipelex/test_extras/test_mthds_corpus_loader.py` | An entry's name does not match its directory, its bundle does not resolve, or the loader's filter semantics changed. |
| Entry validation | `tests/integration/pipelex/test_extras/test_mthds_corpus_entries.py` | A valid entry stopped validating, or an invalid one stopped failing with exactly its declared error. Runs over every entry regardless of tier, so an `inference`-tier entry that broke is caught without spending a token. |
| Packaging | `tests/integration/pipelex/test_extras/test_mthds_corpus_packaging.py` | A corpus file stopped shipping in the wheel, or the generator started shipping. It builds a real wheel and derives what it expects from the corpus tree, so a new entry is covered with no wiring. |

## Consuming the corpus from a test

```python
from pipelex.test_extras.mthds_corpus.loader import get_entry, iter_entries
from pipelex.test_extras.mthds_corpus.manifest import EntryTier

entry = get_entry(name="native_time_departure")
runner = PipelexMTHDSProtocol(library_dirs=[str(entry.directory)], pipe_run_mode=PipeRunMode.DRY)

for entry in iter_entries(tier=EntryTier.DRY):
    ...  # every entry a dry-tier consumer can afford
```

`iter_entries()` filters compose conjunctively and each is optional: `tags` (the entry covers **all** of them), `tier` (a ceiling — the entry's tier is that one or cheaper), `validity`, `granularity`. Ordering is entry-name lexicographic and stable, so parametrized test ids do not churn.

The same two calls are how a **consumer outside this repo** reaches the corpus: it ships as package data in the wheel, so anything that already depends on `pipelex` — our own hosted services, most immediately — reads it with no vendored copy and no drift, in lockstep with its pinned version. Paths handed out are real filesystem paths, resolved through `importlib.resources.files`; wheels install unzipped, and a zip-imported distribution is not supported.

The corpus is the single source for language-level `.mthds` methods in this repo, and this repo's own tests are consumers of it like any other: a growing number of trees under `tests/e2e/pipelex/pipes/` call `get_entry(...)` for their bundle rather than keeping a local copy. `grep -rl mthds_corpus tests/` is the current list — the enumeration is deliberately not written down here, since it moves with every migration.

!!! note "The entries are data, never auto-loaded"

    Nothing boots the corpus into the standard library — libraries load only from explicitly passed `library_dirs`. Be aware, though, that `pipelex/libraries/library_utils.py::get_pipelex_mthds_files_from_package()` recursively sweeps every `.mthds` file under the installed package. It has no callers today; wiring one up would pull the whole corpus into the standard library, so it would need to exclude the corpus tree first.
