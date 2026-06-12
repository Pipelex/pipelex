# Reviewer's guide — `feature/Add-tests`

This branch is a test-coverage grind over the offline-testable layers of pipelex, plus the source bugs that writing those tests surfaced. The diff is almost entirely new unit tests; the source changes are a small, deliberate set of bug fixes, each pinned by a test in the same branch. Overall coverage went from ~72% to ~78% (per-module before/after numbers live in [wip/tests/missing-tests-menu.md](wip/tests/missing-tests-menu.md)).

## How to review this PR

Start with the source changes (next section) — they are the only behavior changes. Then sample the test modules with the conventions section in mind: several patterns that look unusual are deliberate and documented below, so check there before flagging.

## Source changes (the behavior diff)

Every fix below was found by writing a pinning test first, judging the pinned behavior wrong in a review pass, then fixing source and flipping the test. The investigation record is [wip/tests/deferred-source-bugs-pinned-by-tests.md](wip/tests/deferred-source-bugs-pinned-by-tests.md); user-facing wording is in `CHANGELOG.md` under `[Unreleased]`.

- `pipelex/plugins/openai/openai_img_gen_factory.py` + `pipelex/cogt/img_gen/img_gen_setting.py` — the image-moderation mapping was inverted: `is_moderated=true` sent OpenAI's *less* restrictive `"low"` and `false` sent `"auto"`. Now enabled → `"auto"`, disabled → `"low"`. To keep the corrected mapping from silently downgrading default runs (deck alias/handle resolution builds settings without the field, and the old `False` default would have started sending `"low"`), `ImgGenSetting.is_moderated` now defaults to `None` — workers omit the parameter and the provider default applies.
- `pipelex/tools/storage/storage_config.py` + `storage_provider_factory.py` — the biggest source diff. GCP's `lazy_validate` accepted any `uri_format` containing the bare substring `hash` (no substitution slot → every object renders the same URI → silent storage-wide overwrites), and the local/in-memory configs had no validation at all. The per-provider checks and error-message assembly now live on a shared `StorageMethodConfig` base that parses the format string: plain `{hash}` required (escaped/spec'd/indexed forms rejected), unknown placeholders rejected against the supported set, a test rendering as backstop, positive signed-URL lifespans on bucket configs; the factory validates every method; `storage_path` dispatches on the configured method instead of blaming a missing local config.
- `pipelex/builder/bundle_spec.py` + `pipelex/builder/concept/concept_spec.py` — string concept values in bundle specs were unconstructible (a `mode="before"` validator assumed dict input and crashed on the `ConceptSpec | str` union) and `to_blueprint()` mapped the string into `structure`, where the loader rejects anything that isn't a registered structure class. The string now validates cleanly and passes through as the concept's description.
- `pipelex/plugins/mistral/mistral_factory.py` — `make_simple_messages` appended the system message *after* the user message, contradicting its own docstring and the OpenAI-typed sibling. System now comes first.
- `pipelex/observer/local_observer.py` — a payload carrying its own `event_type` key silently overwrote the lifecycle event name in the JSONL record; merge order flipped so the event name wins.
- `pipelex/temporal/worker_cli.py` — startup log said `Starting worker for current project 'None'` when no project was given; it now omits the name.
- `pipelex/core/pipes/output/output_renderer.py` — a `PipeCondition`'s possible outputs were collected by iterating a dependency *set*, so the user-facing `output_option_N` numbering was nondeterministic with two or more mapped pipes; now sorted by pipe code.
- `pyproject.toml` — **pytest's default `norecursedirs` includes `build`**, so everything under `tests/unit/pipelex/cli/commands/build/` (mirroring the source layout) was silently never collected — including a pre-existing regression test. The config now overrides `norecursedirs` to the defaults minus `build`, plus `testpaths = ["tests"]` so bare runs never scan outside the test tree. This is load-bearing for the whole branch: without it a chunk of the new tests wouldn't run in CI.

## Test layout

Tests mirror the source tree under `tests/unit/pipelex/`. The grind covered five areas:

- **CLI internals** — `tests/unit/pipelex/cli/` and `tests/unit/pipelex/cli/commands/build/`: doctor checks, run core + wrapper, build codegen cores, readiness gate, show/which, error handlers.
- **Temporal entry points** — `tests/unit/pipelex/temporal/`: worker CLI, codec HTTP server (driven over real HTTP via `aiohttp.test_utils`), server connection logic. These are deploy-critical surfaces whose bugs previously only showed inside a live cluster.
- **Inference plumbing** — `tests/unit/pipelex/cogt/{llm,img_gen,models,model_backends}/` and `tests/unit/pipelex/plugins/{gateway,mistral}/`: structured-output mode mapping, credentials messages, model-deck reference checks, the per-provider img-gen args factory, both worker-routing factories, gateway request shaping + extract-output parsing, the Mistral factory. None of these tests touch a provider.
- **Core runtime** — `tests/unit/pipelex/{observer,core/pipes/output,graph,builder,pipeline}/`: local observer JSONL sink, output renderer Anything-resolution, bundle-level graph dispatch, bundle-spec validation/`to_blueprint()`/pretty rendering, inputs ops, pipeline runner error paths and MTHDS protocol surfaces.
- **Tools/config** — `tests/unit/pipelex/tools/{misc,storage}/`: the TOML config-sync engine (rewrites user config in place — tests pin the destroy-config guards: never creates keys, preserves comments/structure, dry-run is byte-identical, idempotent), format enums, PIL conversion, storage config validators.

## Conventions the tests follow (read before flagging)

- **One test class per module** (house pytest standard) — that's why e.g. doctor coverage is split across several `test_doctor_*.py` files. pytest-mock (`MockerFixture`) only, never `unittest.mock` imports; strong value asserts; parametrization over copy-paste.
- **The CLI *interface* is deliberately untested here.** Arg parsing, `--help`, Typer wrappers, agent JSON shapes are owned by the sibling `conformance` repo's spec suite. This branch tests the `do_*`/`_core` functions beneath them. Low coverage remaining on `*_cmd.py` wrapper lines is by design.
- **Module-namespace patching, source-module patching for call-time imports.** Collaborators imported at a module's top are patched at the consuming module's namespace; classes imported *inside* functions (the deferred-import pattern in worker factories) are patched at their source module. Worker-factory tests use a fresh real `PluginSdkRegistry()` per test so the booted singleton is never mutated.
- **Real collaborators where cheap, mocks where not:** real TOML files in `tmp_path`, real PIL images, real pydantic SDK models (Mistral OCR, Portkey `GenericResponse`), a real aiohttp server for the codec; AsyncMocks for inference/network/Temporal SDK boundaries.
- **Recorded Rich consoles** (`Console(record=True, color_system=None)` + `export_text()`) for output-rendering asserts.
- **Remaining uncovered lines are deliberate:** `TYPE_CHECKING` blocks, interface-layer wrappers (conformance-owned), lines already pinned by the integration suite (e.g. pipeline runner happy path), and live-call worker paths.

## Known deferred items (not in this PR)

[wip/tests/deferred-source-bugs-pinned-by-tests.md](wip/tests/deferred-source-bugs-pinned-by-tests.md) keeps two intentionally-deferred lists: a design tradeoff (LocalObserver's flat record namespace — nesting the payload is a breaking JSONL-shape change to decide deliberately) and test-quality cleanups (a Pipelex-boot opt-out conftest for pure test dirs, hoisting a few duplicated test scaffolds, minor in-file dedup). Don't treat their absence as gaps.

## Verifying locally

```bash
make agent-check   # lint + typecheck gate
make agent-test    # full offline suite (the new build/ dirs collect thanks to the norecursedirs fix)
```
