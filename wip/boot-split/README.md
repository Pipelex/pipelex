# Boot split

The composition root `pipelex/pipelex.py` was split into a runtime-layer `RuntimeBoot` (`pipelex/runtime_boot.py`) and the interpreter-layer `Pipelex` that subclasses it. **Track complete** — [PR #1073](https://github.com/Pipelex/pipelex/pull/1073) squash-merged into `dev` as `8448c5ca2` on 2026-07-30, and the repo-root `TODOS.md` tracker was archived here as [`boot-split-tracker.md`](boot-split-tracker.md).

The change itself is described in that tracker — the reviewer's guide, the load-bearing decisions, the measured payoff and every review round's record; start at its "Final state at merge" — and in [Where the boot splits](../../docs/contribute/hub-layering.md#where-the-boot-splits). Everything else here is what was **deliberately not done**, each with the analysis and a suggested shape.

Every deferral note was raised by a review pass, verified against the source, and deferred on a stated tradeoff rather than on effort. Production comments point at these files by path, so moving or renaming one means updating its citation.

| Note | What it defers |
|---|---|
| [`runtime-boot-external-interpreter-orchestrator.md`](runtime-boot-external-interpreter-orchestrator.md) | A runtime-only boot rejects an interpreter-layer orchestrator contributed by a *built-in*, but not one contributed by an *external* entry-point plugin — `build_registrar` discovers externals unconditionally. Every remedy needs a layer signal the runtime layer deliberately does not have. Cited from `runtime_boot.py`'s boot-orchestrator gate. |
| [`config-dir-does-not-scope-inference-paths.md`](config-dir-does-not-scope-inference-paths.md) | `config_dir` scopes the main TOML load but not the inference files (backends, routing profiles, model deck), because pinning those needs path overrides that live on the concrete `ModelManager` rather than on the `ModelManagerAbstract` the boot is typed against. Closing it means widening a public injection contract. Cited from both `make()` docstrings and the boot call site. |
| [`failed-boot-does-not-release-every-resource.md`](failed-boot-does-not-release-every-resource.md) | `_teardown_runtime` and `_release_after_failed_boot` are two hand-maintained release lists. The half that *poisons* the next boot is now identical on both; the *dangling* half (`sdk_client_manager`, `reporting_delegate`, `func_registry`) is not. Collapsing them into one list is a lifecycle decision. |
| [`pipelex-setup-narrows-the-runtime-boot-contract.md`](pipelex-setup-narrows-the-runtime-boot-contract.md) | `Pipelex.setup` is an `@override` that does not accept its base's `builtin_plugins` / `core_unconditional_plugin_names`, absorbs them in `**kwargs` and raises — so a caller written against the base type type-checks and fails at run time. Every candidate remedy trades one wart for another. |
| [`boot-split-test-coverage-gaps.md`](boot-split-test-coverage-gaps.md) | The gaps *around* the new tests. A test-quality pass confirmed no new test passes vacuously; these are the coverage tradeoffs it found, each a decision rather than a patch. |

None of these blocked the merge. The two that name a first caller — the external-orchestrator hole and the `config_dir` scoping — are the ones to settle before `RuntimeBoot.make()` becomes reachable from a real entry point.

## Still open outside this repo

One **required cross-repo follow-up**, deliberately out of scope for PR #1073: `pipelex-temporal/tests/conftest.py:86` and `pipelex-transport/tests/conftest.py:89` each patch `"pipelex.pipelex.load_pipelex_service_config_if_exists"` in an autouse session fixture. That symbol now lives in `pipelex.runtime_boot`, so both suites fail at session start once they pick up the new `pipelex`. Repoint both strings. ⚠ Use `git -C <repo> grep` for any cross-repo sweep here — this environment's `grep` is a shell function that does not traverse sibling repos and silently returns zero.
