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

!!! warning "The `.mthds` editor hook fights invalid entries"

    The `pipelex` plugin's `PostToolUse` hook lints, formats and **blocks on an invalid verdict** for every `Write`/`Edit` of a `.mthds` file, and has no skip mechanism. Author valid entries with the editing tools to collect the free lint; write an invalid entry's bundle through a shell heredoc, which the hook's matcher does not intercept.

## The tag vocabulary

Tags are namespaced and the vocabulary is closed: an entry covering a tag the vocabulary does not declare fails the gate. `native.*` is generated from `NativeConceptCode`; `feature.*` is reserved for hand-maintained language features; `operator.*`, `controller.*` and `error.*` arrive with their registries.

`vocabulary.toml` is generated in full, so it is never edited by hand:

```bash
make generate-corpus-vocabulary
```

Everything the file says is decided in the generator, `pipelex/cli/dev_cli/commands/generate_corpus_vocabulary_cmd.py` — the registries it walks, and every exclusion reason. It is unshipped dev tooling (the wheel excludes `pipelex/cli/dev_cli`) while the file it writes ships, which is what lets a consumer read the closed tag set without a registry walk. A hand-maintained namespace will be declared there too when one first has content; `feature.*` is reserved in the contract but has no tags yet, and adding one before an entry covers it would simply red the exhaustivity gate.

An **exclusion** marks a registry code that no standalone focused entry could meaningfully exercise. It stays in the vocabulary and stays usable by an entry; it is simply not owed a focused entry. No native code is excluded today — every one of them turned out to support a real entry. The exclusion map is keyed on the registry enum rather than on strings, which is what keeps an exclusion from outliving the code it names: a removed code breaks the generator at import, naming itself.

## The gates, and what a red one means

| Gate | Where | Red means |
|---|---|---|
| Vocabulary drift | `tests/unit/pipelex/test_extras/test_mthds_corpus_vocabulary.py` | A registry changed and the committed vocabulary was not regenerated. Run `make generate-corpus-vocabulary`. |
| Exhaustivity | `tests/unit/pipelex/test_extras/test_mthds_corpus_exhaustivity.py` | A vocabulary tag has no `focused` entry covering it — write the entry, or record an exclusion with a reason. Also fires when an entry covers a tag that is not in the vocabulary. |
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

The corpus is the single source for language-level `.mthds` methods in this repo: `tests/e2e/pipelex/pipes/date/` and `tests/e2e/pipelex/pipes/yes_no/` already reach for their bundles this way rather than keeping local copies.

!!! note "The entries are data, never auto-loaded"

    Nothing boots the corpus into the standard library — libraries load only from explicitly passed `library_dirs`. Be aware, though, that `pipelex/libraries/library_utils.py::get_pipelex_mthds_files_from_package()` recursively sweeps every `.mthds` file under the installed package. It has no callers today; wiring one up would pull the whole corpus into the standard library, so it would need to exclude the corpus tree first.
