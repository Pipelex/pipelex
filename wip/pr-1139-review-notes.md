# PR #1139 review notes — the pytest-standards rules keep getting re-raised

PR: <https://github.com/Pipelex/pipelex/pull/1139> (`feature/MthdsTestCorpus-p3`, "the `error.*` axis: an invalid-method coverage surface for the MTHDS Test Corpus")

Nothing on this PR was deferred. Four of the five review threads were false positives and one was a real gap that got fixed on the branch. This note exists for the pattern behind three of those four, which is now on its third consecutive appearance and is not a question a PR-review pass should keep re-answering.

## The pattern

Three of the five threads on this PR — all from Codex — cited two rules from the same source file and asked for the same two changes that were asked for on #1069 and, in a sibling form, on #1138:

- **`tests/integration/pipelex/pipeline/test_validate_bundle_entry_shape_parity.py:32`** — move the three inline MTHDS payloads into a `test_data.py`, citing `AGENTS.md:375`.
- **`test_validate_bundle_entry_shape_parity.py:1`** and **`tests/e2e/pipelex/cli/test_validate_cmd.py:1`** — move the module-level docstring onto the test method, citing `AGENTS.md:438`.

Both rules are real text, quoted accurately. Both trace to one source, `pipelex/kit/agent_rules/pytest_standards.md` — line 17 for the test-data rule and line 80 for the docstring rule — from which the repo-root `AGENTS.md` and `CLAUDE.md` are generated. That file is **shipped to users** as part of the package kit, which is the same dogfooding shape [`pr-1138-review-notes.md`](pr-1138-review-notes.md) recorded for the one-`TestClass`-per-module rule in the very same document.

## What the tree actually does — measured on this branch

**The `test_data.py` rule, as applied to MTHDS payloads.** Ninety test modules inline an MTHDS bundle literal. **Zero** of them keep it in a `test_data.py`. Not "few" — none. In the flagged file's own directory, thirty-two of the thirty-three modules inline one. Of the fifty-two `test_data.py` files in the tree, the only one holding anything MTHDS-shaped is `tests/unit/pipelex/graph/test_data.py`, and it holds GraphSpec dicts, imported by two sibling modules. That reveals the norm the tree actually follows, and it is a coherent one: **`test_data.py` is where data shared across modules goes.** The three payloads on this PR are `_`-private, each consumed exactly once, in the `pytest.param` list sixty lines below its own definition.

**The docstring rule.** Six hundred and ninety-one of one thousand one hundred and thirty test modules — sixty-one percent — open with a module-level docstring, counted with `ast.get_docstring` on the module node. By directory: thirty-two of thirty-three in `tests/integration/pipelex/pipeline/`, nine of thirteen in `tests/e2e/pipelex/cli/`, four of four in `tests/unit/pipelex/test_extras/`. The other half of the same sentence fares no better: five hundred and fifty-three of one thousand two hundred and sixteen `Test*` classes carry a class docstring. Nothing enforces any of it — `pyproject.toml` selects `ALL` but ignores `D100` and `D101`, and no rule anywhere forbids a module docstring.

[`pr-1069-review-notes.md`](pr-1069-review-notes.md) measured five hundred and seventy-nine of one thousand and eighteen for the same rule. The proportion has not moved; the tree has simply grown.

## Why the three threads were closed rather than acted on

Because acting on them would have moved this PR *away* from the code around it. The new integration module is a deliberate mirror of `tests/integration/pipelex/pipeline/test_validate_bundle_structured_errors.py`, which pre-exists on `dev` and is structurally identical — module docstring, then `_`-private inline MTHDS constants, then one parametrized test class. In `tests/e2e/pipelex/cli/`, the immediate neighbour `test_fix_bundle_cmd.py` opens with a module docstring *and* inlines a bundle literal, both patterns already shipped side by side. And `tests/unit/pipelex/test_extras/test_mthds_corpus_exhaustivity.py` carried a module docstring before this PR touched it, naming the governing spec section — the module docstring is the established house style for this whole feature area.

Content matters too, and the reviewer misread it. The rule targets "this test tests X" boilerplate migrating up to file level. Neither flagged docstring is that: one records why `_load_mthds_files_into_library` used to destroy structured error data and why a third already-parity bundle sits in the parametrize list; the other records why the e2e test now assembles its directory from corpus entries selected by `EntryValidity.VALID` instead of pointing at a path, and why the old path expression became wrong once the corpus grew deliberately invalid entries. Deleting the second one invites someone to "simplify" the `copytree` loop straight back into the bug this PR just fixed. The parity module, meanwhile, already satisfies the rule's positive half — its concise purpose is on the method.

## The open question, unchanged since #1069

Two coherent resolutions, and choosing between them is a judgment call about how much we want to spend on test-file shape:

1. **Make the rules match the practice.** Narrow the test-data rule to data *shared across modules*, which is the norm the tree already follows and which the one real `test_data.py` in the graph package exemplifies. Soften the docstring prohibition to what it was probably reaching for — no per-test purpose docstrings migrating up to file or class level — while allowing a module docstring that explains why the module exists. Both edits go in `pipelex/kit/agent_rules/pytest_standards.md`, the generated `AGENTS.md` and `CLAUDE.md` follow, and our users stop receiving rules we do not hold ourselves to.
2. **Keep the rules and enforce them.** That means a guard in the `check-keyword-only` mould plus a sweep across six hundred and ninety-one modules and ninety inline payloads, which is its own piece of work.

What tips the balance now is the recurring cost. `AGENTS.md` is the Codex-facing file and carries both rules; `CLAUDE.md` carries neither. So every Codex review of every new test module will keep raising these same findings, and someone will keep spending a review pass measuring the tree to close them. Three PRs in, that is no longer a one-off.

Nothing is broken and no gate is failing, so there is no urgency — only accumulation. See also the sibling one-`TestClass`-per-module question in [`pr-1138-review-notes.md`](pr-1138-review-notes.md), which lives in the same source document and wants deciding at the same time.

## For the record — what was fixed rather than deferred

The one real finding on this PR (Codex, `tests/unit/pipelex/test_extras/test_mthds_corpus_exhaustivity.py`) was that the new agreement gate tested membership where the contract landed in the same PR says equality. It is fixed on the branch, and the mutation that proves it bites is described in the thread reply.

The greptile thread on `.pipelex/plxt.toml` was a false positive, but it had one genuine residue: the invalid entries are outside `make lint` and `make format` and the contributor docs never said so. `docs/contribute/mthds-test-corpus.md` now says it.
