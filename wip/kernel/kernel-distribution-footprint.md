# Kernel distribution footprint — B0 measurement

**Status:** measured 2026-08-11 on `refactor/Kernel-4`, at the Part A end-state (the entry-point group split, merged into this branch). Read-only: nothing in `pipelex/` was changed to produce it.

This is B0 of [`kernel-plugin-groups-and-distribution-plan.md`](kernel-plugin-groups-and-distribution-plan.md). It answers three questions with numbers instead of intuition — **what would the kernel package contain, what would it require, and how big would it be** — and it exists to drive B1's content line (D-B2) now, and to inform a Part C greenlight and its extras design (OQ-2) later.

**On the counts in this document.** The workspace rule against hardcoding counts targets prose that goes stale silently. Here the counts *are* the deliverable, and the plan explicitly asks Checkpoint B to point at this doc rather than inline its numbers. They are therefore dated, attributed to a commit, and reproducible — see [Reproducing](#reproducing-this-measurement). Treat any number here as a snapshot, not as a contract.

## Headline

| | |
| --- | --- |
| Declared kernel-layer modules | **560 of 981** in `pipelex/` — 57% of modules, 52% of source bytes (2.65 MiB of 5.07 MiB) |
| Non-kernel modules a kernel-only boot actually loads | **11** — the concrete addendum to the content line |
| Third-party top-levels the kernel layer imports at module level | **35**, of which **24** outside the provider extras |
| Kernel core install (deps only, no extras) | **57 distributions, 61.1 MiB** |
| Full `pipelex` core install today | **89 distributions, 93.5 MiB** |
| Shed by dropping interpreter-only deps | **32 distributions, 32.4 MiB** (~35%) |
| Booted process, kernel-only vs full | 1511 vs 1884 modules; 91.7 vs 108.7 MiB max RSS |

The headline for a hypothetical Part C is therefore **not** "look how little you need". A kernel install is roughly two-thirds of a full one, and the ~61 MiB floor is dominated by four dependencies that have nothing to do with the interpreter: `pillow`, `faker` (via `polyfactory`), `pypdfium2` and `portkey-ai`. If a small headline is wanted, it has to be bought by extras design, not by the layer split — see [What this means for extras](#what-this-means-for-extras-oq-2).

## 1. The module set

### Declared kernel layer, by package

Source of truth is `KERNEL_LAYER_PACKAGES` in `pipelex/cli/dev_cli/commands/hub_layering_guard.py` — the declaration the hub-layering guard polices.

| Package | Modules | Source | Lines |
| --- | ---: | ---: | ---: |
| `pipelex.cogt` | 135 | 634 KiB | 14 770 |
| `pipelex.tools` | 96 | 421 KiB | 11 361 |
| `pipelex.core` | 76 | 450 KiB | 10 374 |
| `pipelex.providers` | 111 | 425 KiB | 9 615 |
| `pipelex.system` | 48 | 223 KiB | 5 478 |
| `pipelex.graph` | 27 | 157 KiB | 4 124 |
| `pipelex.kernel` | 19 | 105 KiB | 2 181 |
| `pipelex.plugins` | 17 | 76 KiB | 1 632 |
| `pipelex.tracing` | 12 | 62 KiB | 1 560 |
| `pipelex.runtime_boot` | 1 | 60 KiB | 963 |
| `pipelex.errors` | 3 | 31 KiB | 687 |
| `pipelex.runtime_hub` | 1 | 26 KiB | 605 |
| `pipelex.reporting` | 6 | 27 KiB | 603 |
| `pipelex.test_extras` | 4 | 16 KiB | 383 |
| `pipelex.observer` | 4 | 4 KiB | 124 |

Plus `pipelex/kit/` data files (0.30 MiB) — not modules, but shipped, and reached by the kernel layer (see the `kit.paths` leak below).

### What must move with it

A kernel-only boot (`RuntimeBoot.make(needs_inference=False)`, measured in a fresh interpreter) loads exactly **11 modules that are not in the declared kernel layer**:

```
pipelex                              (__init__: `log`, `pretty_print` — re-exported from pipelex.tools)
pipelex.base_exceptions
pipelex.config
pipelex.urls
pipelex.suggested_fix
pipelex.kit  /  pipelex.kit.paths
pipelex.language  /  pipelex.language.mthds_config
pipelex.runtime_bridge  /  pipelex.runtime_bridge.orchestration_mode
```

The static import graph agrees and adds one the boot does not reach (the `*_list` modules are lazy): **`pipelex.cli.exceptions`**, imported at module level by `cogt.model_backends.model_lists`, `providers.anthropic.anthropic_list` and `providers.bedrock.bedrock_list`.

D-B2 already anticipated the top-level modules ("config/system, base exceptions, urls"). The measurement confirms them and adds four the plan did not name. Full static leak census — kernel-layer module importing a non-kernel-layer `pipelex` module:

| Destination | Kernel importers | Kind | Reading |
| --- | ---: | --- | --- |
| `pipelex` (`log`, `pretty_print`) | 79 | module-level | **The single biggest B2 edit.** `pipelex/__init__.py` is itself pure kernel content — it re-exports from `pipelex.tools.log` and `pipelex.tools.misc.pretty`. So the symbol moves to `pipelex_kernel/__init__.py` and 79 modules change one import line. |
| `pipelex.config` | 33 | module-level | Imports only kernel-layer modules. Moves whole. |
| `pipelex.base_exceptions` | 32 | module-level | Moves whole (already anticipated). |
| `pipelex.urls` | 6 | module-level | Moves whole (already anticipated). |
| `pipelex.cli.exceptions` | 3 | module-level | **A genuine layering smell, not a move.** Kernel-layer model-listing code raises `PipelexCLIError`. Either the error gets a kernel home or these raise a kernel error the CLI maps. D-B4 says the kernel package ships no CLI — this is the only thing standing in the way. |
| `pipelex.runtime_bridge.orchestration_mode` | 3 | module-level | 34 lines, imported by the plugin registrar and two registries. Moves, or the value type it defines does. |
| `pipelex.kit.paths` | 2 (+1 deferred) | module-level | The kit *data* is arguably interpreter-side; `paths` is reached from `cogt.models.deck_manifest` and the service agreement. Decide whether the kernel owns a kit path accessor. |
| `pipelex.language.mthds_config` | 1 | module-level | **The structural one.** `MthdsConfig` is a *field* of `PipelexConfig` in `system.configuration.configs` — the kernel-layer main config model embeds an interpreter-layer submodel. Not fixable by moving a file; it is a config-composition decision. |
| `pipelex.builder.pipe.pipe_spec`, `…pipe_batch_spec` | 1 | **deferred** | See the finding below. |
| `pipe_run.delivery_assignment`, `pipe_run.pipe_job`, `runtime_bridge.payloads`, `pipe_operators.func.pipe_func_executor_protocol` | 1 each | `TYPE_CHECKING` | Runtime-harmless; matters only for how D-B5's ban is written (below). |

Everything on that list except the `TYPE_CHECKING` block is work B2 must do. None of it is large; the `pipelex` → `log` edit is broad but mechanical.

## 2. Findings that change the plan's assumptions

### The tools subset is not a subset

D-B2 says the content line includes "the tools subset the closure actually reaches". Measured: of 96 `pipelex.tools` modules, **88 have at least one kernel-layer importer**. The 8 that do not are:

```
tools.jinja2.jinja2_optional_guards   <- pipe_machinery.template_guard_lint
tools.misc.async_utils                <- pipe_controllers.batch.pipe_batch
tools.misc.diff                       <- cli.dev_cli.commands.check_config_sync_cmd
tools.misc.semver                     <- libraries.library_manager
tools.misc.toml_sync                  <- cli.dev_cli.commands.sync_main_config_cmd
tools.network.ssrf_guard              <- pipe_run.delivery_executor
tools.typing.annotation_utils         <- pipe_operators.compose.structured_content_composer
tools.typing.class_utils              <- libraries.concept.concept_library
```

**Recommendation: move `pipelex.tools` whole.** Splitting 8 modules out of 96 buys ~1 MiB of source and one `semantic_version` dependency, and costs a permanent per-module judgement call on every future tools addition. The "subset" framing in D-B2 should be retired.

### The tree has three buckets, not two — and that is why every gate is green

The kernel layer is *declared* (`KERNEL_LAYER_PACKAGES`); the interpreter layer is *named* by the closure test's `INTERPRETER_PACKAGES`. Those two sets do not partition `pipelex/`. The remainder — `pipelex.cli`, `pipelex.language`, `pipelex.kit`, `pipelex.runtime_bridge`, and the top-level modules `config`, `base_exceptions`, `urls`, `suggested_fix`, `exceptions` — is in neither.

**Every module-level leak in the table above lands in that third bucket.** That is not a coincidence, it is the mechanism: the hub-layering guard asks "does this reach `interpreter_hub`?" and the closure test asks "is this in a named interpreter package?", and each of those nine destinations answers no to both. The gates are working exactly as specified; the specification has a gap the size of the third bucket.

This is the same shape as the already-recorded lesson that an undeclared package is unpoliced rather than neutral — see the `KERNEL_LAYER_PACKAGES` note about `graph`, `tracing`, `observer` and `errors`. D-B5's ban (`nothing under pipelex_kernel/ may import pipelex`) is the first rule that closes it, because it is stated over the *package boundary* rather than over a curated set of names. That is the strongest argument for Part B that the measurement produced, and it is stronger than the legibility argument the plan currently leads with.

### One live layer breach, invisible to both gates

`pipelex/core/memory/working_memory_factory.py` — kernel-layer, and a listed `KERNEL_LAYER_ENTRY_POINTS` entry — has a function-local import of `pipelex.builder.pipe.pipe_spec` and `pipelex.builder.pipe.pipe_batch_spec` inside `_get_concrete_class_for_mocking`, under a `# Import here to avoid circular imports` comment.

`builder` **is** a named interpreter package. Importing `pipelex.builder.pipe.pipe_spec` in a fresh interpreter pulls 6 interpreter modules. It escapes both gates for two independent reasons: the closure test only sees module-level imports, and the hub-layering guard is satisfied because that path does not reach `interpreter_hub`.

The boot-contract test's post-call sweep is the mechanism that exists to catch exactly this — but it only covers the ops it calls, and this mocking helper is not on any of them. Deferred rather than fixed here, per the standing "when in doubt, defer" constraint: B0 is a read-only measurement, and the fix (a circular-import workaround in dry-run mock generation) is a design decision, not a measurement. Recorded as **KF-18** in [`deferred-follow-ups.md`](deferred-follow-ups.md).

### D-B5's ban needs to be written against runtime imports, not text

Four `TYPE_CHECKING`-only imports cross the boundary (`pipe_run.delivery_assignment`, `pipe_run.pipe_job`, `runtime_bridge.payloads`, `pipe_operators.func.pipe_func_executor_protocol` — all from `pipelex.plugins`, which types against interpreter-layer objects it never constructs). A textual "reject any `import pipelex`" AST scan flags all four; they are runtime-harmless and are the plugin mechanism doing its job. Either the ban exempts `TYPE_CHECKING` blocks (the guard already has this exemption — reuse it) or those four type-only references become strings. The cold-import closure half of D-B5 is unaffected either way.

### Two direct dependencies are undeclared

The kernel layer imports **`tenacity`** (5 modules, including `tools.misc.tenacity_utils`) and **`httpcore`** (`tools.network.ssrf_guard`) at module level. Neither is in `pyproject.toml`'s `dependencies` — both arrive transitively today (`tenacity` via `instructor`, `httpcore` via `httpx`). This is a latent break in `pipelex` *now*, independent of Part B: dropping `instructor` from the core deps would break `tools.misc.tenacity_utils` with no dependency change to point at. A kernel distribution would have to declare both explicitly.

### `pipelex.test_extras` is the only reason `pytest` is a kernel import

`test_extras.shared_pytest_plugins` imports `pytest` at module level, and `pipelex.pipelex` imports `test_extras` at boot. It is declared kernel-layer for good reasons (it ships, it measures clean). Whether it belongs in a kernel *distribution* is a separate question that Part C would have to answer; it is excluded from the dependency numbers below.

## 3. Third-party dependency closure

Split by which layer imports each top-level, module-level imports only (`TYPE_CHECKING` excluded):

- **Kernel-only (28):** `PIL`, `aioboto3`, `aiofiles`, `anthropic`, `boto3`, `botocore`, `datamodel_code_generator`, `docling`, `docling_core`, `dotenv`, `fal_client`, `filetype`, `google`, `httpcore`, `huggingface_hub`, `instructor`, `jinja2`, `json2html`, `linkup`, `mistralai`, `openai`, `portkey_ai`, `pypdfium2`, `pytest`, `semantic_version`, `tenacity`, `tomli`, `types_aiobotocore_bedrock_runtime`
- **Shared (12):** `httpx`, `kajson`, `mthds`, `opentelemetry`, `polyfactory`, `posthog`, `pydantic`, `pydantic_core`, `rich`, `shortuuid`, `tomlkit`, `typing_extensions`
- **Interpreter-only (3):** `click`, `typer`, `yaml`

Of `pipelex`'s 37 declared core dependencies, **9 are never imported anywhere in the kernel layer**: `idna`, `markdown`, `networkx`, `pipelex-tools-py`, `pyyaml`, `reportlab`, `requests`, `typer`, `urllib3`.

Four of the kernel-side imports are **deferred-only** — imported inside functions, never at module scope — which is the shape of an optional dependency: `instructor` (14 sites), `datamodel_code_generator` (2), `docling` (1), `docling_core` (1).

## 4. Install size

Measured as installed bytes in this venv (Python 3.13.9, macOS, arm64), transitively closed over each distribution's non-extra requirements.

| | Distributions | Size |
| --- | ---: | ---: |
| Full `pipelex` core dependency closure | 89 | 93.5 MiB |
| Kernel core closure (extras and `test_extras` excluded) | 57 | 61.1 MiB |
| Shed | 32 | 32.4 MiB |

Shed: `aiohappyeyeballs`, `aiohttp`, `aiosignal`, `annotated-doc`, `argcomplete`, `attrs`, `black`, `click`, `datamodel-code-generator`, `docstring-parser`, `frozenlist`, `genson`, `inflect`, `instructor`, `isort`, `markdown`, `more-itertools`, `multidict`, `mypy-extensions`, `networkx`, `packaging`, `pathspec`, `pipelex-tools-py`, `platformdirs`, `propcache`, `pytokens`, `pyyaml`, `reportlab`, `shellingham`, `typeguard`, `typer`, `yarl`.

Note what dominates that list: `instructor` and `datamodel-code-generator` (with `black`, `isort`, `genson`, `inflect`) are shed not because they are interpreter-side but because they are **deferred-only** imports — they would come back the moment the kernel declared them. The genuinely interpreter-side shed is `typer`/`click`/`shellingham`/`argcomplete` (the CLI), `pyyaml`, `networkx`, `markdown`, `reportlab`, `pipelex-tools-py` — roughly 10 MiB.

Heaviest in the kernel core closure:

| Distribution | Size | Pulled by |
| --- | ---: | --- |
| `pillow` | 12.57 MiB | direct (`tools.misc.image_utils`, 2 img-gen workers) |
| `faker` | 8.47 MiB | `polyfactory` |
| `pypdfium2` | 5.77 MiB | direct (`tools.pdf.pypdfium2_renderer`) |
| `portkey-ai` | 4.97 MiB | direct (the gateway + portkey providers) |
| `openai` | 4.76 MiB | direct |
| `pygments` | 4.31 MiB | `rich` |
| `pydantic-core` | 4.30 MiB | `pydantic` |

Provider extras, measured as what each adds *on top of* the kernel core:

| Extra | Added | New dists |
| --- | ---: | ---: |
| `docling` | 62.89 MiB | 22 |
| `aioboto3` (s3, bedrock) | 21.60 MiB | 16 |
| `google` | 21.21 MiB | 14 |
| `boto3` (dynamodb, bedrock) | 19.33 MiB | 6 |
| `huggingface_hub` | 12.71 MiB | 10 |
| `mistralai` | 3.59 MiB | 6 |
| `anthropic` | 2.28 MiB | 2 |
| `fal_client` | 1.17 MiB | 5 |
| `linkup` | 0.04 MiB | 1 |

Runtime cost of a booted process, same venv, fresh interpreter each time:

| Scenario | `sys.modules` | `pipelex.*` modules | max RSS |
| --- | ---: | ---: | ---: |
| bare interpreter | 63 | 0 | 15.4 MiB |
| `import pipelex.kernel.pipelex_kernel` | 927 | 280 | 67.7 MiB |
| `RuntimeBoot.make()` (kernel-only) | 1511 | 365 | 91.7 MiB |
| `Pipelex.make()` (full interpreter) | 1884 | 642 | 108.7 MiB |

A kernel-only boot loads 353 of the 560 declared kernel-layer modules — the remainder is provider adapters and tools reached lazily or not at all.

## 5. What this means

### For B1/B2 (the content line, D-B2)

The content line is **the declared `KERNEL_LAYER_PACKAGES` set, whole, plus five top-level modules** (`__init__`, `base_exceptions`, `config`, `urls`, `suggested_fix`), with four boundary decisions to take deliberately:

1. `pipelex.cli.exceptions` — give `PipelexCLIError` a kernel home, or stop raising it from kernel-layer model listing. Blocks D-B4's "no CLI in the kernel package".
2. `pipelex.language.mthds_config` — `PipelexConfig` embeds `MthdsConfig`. A config-composition decision, not a file move.
3. `pipelex.runtime_bridge.orchestration_mode` — 34 lines the plugin registrar needs.
4. `pipelex.kit.paths` — does the kernel own a kit-path accessor, or does the kit data move with it?

`pipelex.tools` moves whole (the "subset" is 92% of the package). `pipelex.test_extras` is the one package whose membership is genuinely open.

### For extras (OQ-2)

If Part C is ever greenlighted, the extras question is **not** about the provider backends — those are already extras and already behave correctly (each adds its weight only when installed, from 0.04 to 63 MiB). It is about the ~61 MiB kernel core, where four dependencies carry 32 MiB between them:

- **`polyfactory` → `faker` (8.5 MiB)** is reached from three modules, all dry-run mock generation. The best extras candidate in the set: a kernel that cannot mock is still a kernel.
- **`pypdfium2` (5.8 MiB)** is one module, `tools.pdf.pypdfium2_renderer`.
- **`pillow` (12.6 MiB)** is three modules, but one of them is `tools.misc.image_utils` — likely load-bearing.
- **`portkey-ai` (5.0 MiB)** is the Pipelex Gateway provider, arguably not core to a *kernel* at all.

None of this needs deciding before Checkpoint B. It is recorded so the greenlight conversation starts from numbers.

## Reproducing this measurement

The scripts were throwaway and live in the session scratchpad, not in the repo — deliberately, since a measurement harness nobody runs is a maintenance liability, and the two properties worth *pinning* are already pinned by `test_kernel_layer_import_closure.py` and `test_kernel_boot_contract.py`. To redo it:

1. **Module set / leak census:** AST-walk every `pipelex/**/*.py`, resolve each `pipelex.*` import target to an existing module (folding `from pkg.mod import Name` onto `pkg.mod`), classify source and destination against `KERNEL_LAYER_PACKAGES`, and report edges where the source is kernel and the destination is not — split by module-level / function-local / `TYPE_CHECKING`.
2. **Runtime closure:** run each boot scenario in a **fresh subprocess** (both hubs are sticky class-attribute singletons; an in-process check answers from a stale boot and passes vacuously) and dump `sys.modules`.
3. **Dependency closure and size:** `importlib.metadata.packages_distributions()` to map top-level import names to distributions, then close over each distribution's non-extra `Requires-Dist` and sum `dist.files` sizes on disk.

Caveats: sizes are one venv on one platform (`pillow`, `pypdfium2` and the `google`/`boto3` families are wheel-size-sensitive to platform); `packages_distributions()` maps a top-level to *every* distribution that provides it, which is why `google` fans out to eight; and the static graph cannot see genuinely dynamic imports, which is the blind spot the runtime cross-check exists to cover — the two agreed everywhere they overlap.
