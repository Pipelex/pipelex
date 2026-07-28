# Review follow-ups — assessed and ready to implement

The three items the modularity track's review rounds recorded but did not fix. Each was **re-verified against the tree on 2026-07-28 at `7ddb77f87`** before being written down here; every claim below is measured, and the commands that produced it are inline so a new session can re-take them rather than trust them.

**Where implemented:** branch `refactor/Modularity-4`, on top of the merged PR #1067. All three are independent of each other and of the release-gated cross-repo sweep — except **FU-1**, which had to land *before* the sweep ships the `MthdsParserError` rename to its consumers.

**Stable IDs:** cite these as **FU-1**, **FU-2**, **FU-3**. They supersede the unnumbered bullets in the tracker's "Follow-ups from the review" section, which points here.

| id | one line | verdict | size | status |
| --- | --- | --- | --- | --- |
| [FU-1](#fu-1--nothing-flags-an-error-class-rename-and-it-is-a-wire-break) | Nothing flags an error-class rename, and it is a wire break | still true — **do this first** | small | ✅ **DONE** |
| [FU-2](#fu-2--the-img-gen-neutrality-guard-is-weaker-than-its-comment-and-its-recorded-remedy-is-wrong) | The img-gen neutrality guard overclaims; its recorded remedy rests on a false measurement | still true, **remedy corrected here** | two small edits | ✅ **DONE** |
| [FU-3](#fu-3--the-bookkeeping-files-a-bulk-rewrite-breaks-are-still-ungated) | The bookkeeping files a bulk rewrite breaks are still ungated | gate absent, artifacts currently clean | small, do half | ✅ **DONE** |

---

## FU-1 — Nothing flags an error-class rename, and it is a wire break

> ✅ **DONE** — see [what shipped](#what-shipped) at the end of this section.

### Verified still true

`pipelex/base_exceptions.py:595` builds the report identity straight off the class:

```python
report = ErrorReport(
    error_type=type(self).__name__,
    ...
)
```

`error_type` **is** the Python class name, with no indirection. Consumers branch on that string, so a rename does not break their build — they silently fall through to a generic error branch. All four consumer sites confirmed live and still switching on the **retired** name:

| repo | site | shape |
| --- | --- | --- |
| `mthds-starter-js` | `src/lib/errors.ts:176` | `case "PipelexInterpreterError":` |
| `pipelex-starter-js` | `src/lib/errors.ts:257` | `case "PipelexInterpreterError":` |
| `vscode-pipelex` | `editors/vscode/src/pipelex/__tests__/cliValidationBackend.test.ts:99` | `error_type: 'PipelexInterpreterError'` |
| `playroom` | `src/app/api/graph/route.ts:119` | `message.includes("PipelexInterpreterError")` |

The `redirect_maps` workaround is at `mkdocs.yml:60`, with a comment naming this exact rename. It fixes the docs URI; it does nothing for the four sites above.

### What the original item did not say, and it changes the cost

**`title` and `type_uri` are already decoupled.** Both read a `_declared_*` class attribute via `cls.__dict__` (inheritance deliberately bypassed) — `base_exceptions.py:532` and `:547`, added during M1's review round to fix the `"Mthds parser"` brand defect. Measured today: error classes discoverable through `iter_pipelex_error_subclasses()` = **294**; carrying a `_declared_title` = **31**; carrying a `_declared_type_uri` = **0**.

So of the three identity fields on every `ErrorReport`, the two that are *presentation* have an override hatch, and the one that is the **machine contract** does not. That asymmetry is backwards, and it is also why the fix is cheap.

### Recommendation — do the cheap half now, defer the design change

**Do: a golden snapshot of `(error_type, title, type_uri)` for every `PipelexError` subclass.**

The complaint is *"nothing in the repo flags it"*. A snapshot closes exactly that, needs no change to the error model, and needs no matching spec/conformance edit. Every future rename then lands as a reviewable diff on a committed file instead of a silent fallthrough in four TypeScript repos.

Everything needed already exists:

- **The enumerator:** `iter_pipelex_error_subclasses()` in `pipelex/errors/error_pages_generator.py:130`. It force-loads deferred-import error modules first and filters synthetic/fixture subclasses, so it is the population the docs and the wire agree on. Do **not** hand-roll a `__subclasses__()` walk — `tests/unit/pipelex/errors/test_error_class_location_convention.py:141` documents why (a naked walk is green for the wrong reason).
- **The precedent and the home:** `tests/unit/pipelex/errors/`, alongside the location-convention test that already consumes the same helper.
- **The one-class version to generalize:** `test_mthds_parser_error_identity_is_pinned` (added in M1's review round for `MthdsParserError`).

Shape it as a committed golden file plus a regeneration command, in the style the repo already uses for generated artifacts — not as an inline literal in the test body. A 294-row inline list is the *inventory* shape this track spent four review rounds deleting; a golden file diff is a review artifact, which is the point.

⚠ **Anti-vacuity:** assert the enumerated set is non-empty, in a **non-parametrized** test. If you parametrize over the class list, pytest reports `SKIPPED [1] got empty parameter set` and exits 0 for an empty list — an assertion at the top of a parametrized body is unreachable by construction. This is the F1 defect; see `tests/unit/pipelex/cogt/img_gen/test_img_gen_mapping_neutrality.py` for the worked fix.

**Defer: the `_declared_error_type` refactor.** Mirroring the existing `_declared_title` / `_declared_type_uri` pattern for `error_type` is ~10 lines against code that already exists. But it buys less than it looks like here: the workspace forbids backward compatibility, so it cannot be used to keep `"PipelexInterpreterError"` alive for the four consumers — they must be updated in the sweep either way. Its value is purely forward, making the *next* rename free. Worth doing when a rename is actually wanted; it touches the error model and the agent-CLI JSON envelope, so it needs a matching `docs/specs/` + `conformance/` change (`error_type` appears in `docs/specs/pipelex-mthds-protocol.md`, `pipelex-hosted-envelope.md`, `mthds-agent-cli.md`, `hook-lint-pipeline.md`).

### Ordering

Land the snapshot **before** the release-gated cross-repo sweep. The sweep is what actually ships `MthdsParserError` to those four consumers, and the snapshot is what makes the next such rename visible at the moment it is made rather than at the moment something breaks in a different repo.

### What shipped

Re-verification held on both counts before starting: `error_type=type(self).__name__` is still at `base_exceptions.py:595`, and all four consumer sites still switch on `"PipelexInterpreterError"` (plus two test files in the starter repos that the original survey did not list — `mthds-starter-js/src/lib/errors.test.ts:145` and `pipelex-starter-js/src/lib/errors.test.ts:170`). The cheap half was done as recommended; the `_declared_error_type` refactor stays deferred.

| file | role |
| --- | --- |
| `pipelex/errors/error_identity_snapshot.py` | pure renderer — `iter_error_identity_rows()` + `render_error_identity_snapshot()`, population from `iter_pipelex_error_subclasses()` |
| `pipelex/cli/dev_cli/commands/generate_error_identity_cmd.py` | `pipelex-dev generate-error-identity`, owns the repo-relative output path |
| `tests/data/errors/error_identity.txt` | the committed golden — a preamble, then one `error_type \| title \| type_uri` row per class |
| `tests/unit/pipelex/errors/test_error_identity_snapshot.py` | the gate |
| `Makefile` | `make generate-error-identity`, alias `make gei` |

Decisions taken, and why:

- **Pytest is the gate; there is no `check-error-identity` command.** The doc asked for "a committed golden file plus a regeneration command"; a second freshness command wired into `make check` would duplicate what the test already does. The regeneration command exists, the *checking* lives in one place.
- **The renderer takes no Pipelex bootstrap.** `title()` / `type_uri()` read class attributes and a module-level URL constant, and discovery imports error modules by filename — so unlike `generate-error-pages` this runs anywhere, including an environment with no configured backend.
- **The anti-vacuity guard is honoured.** `test_enumerated_identity_set_is_not_empty` is non-parametrized and additionally asserts `PipelexError` itself is present, so the guard is count-free and cannot be skipped into a green run.
- **A third test pins format integrity** — no identity field may contain the `" | "` column separator, which is what keeps the rendering unambiguous.

Negative-tested: rewriting the `MthdsParserError` row to `PipelexInterpreterError` fails the gate with the diff shown inline and the "this is a WIRE BREAK" framing, which is exactly the review artifact the item asked for.

Docs updated in the same change: [Error Model](../../docs/under-the-hood/error-model.md) gains an "identity triple" subsection explaining why `error_type` has no declaration hatch and what the snapshot is for; the kit agent-rules sources (`commands.md`, `codex_commands.md` — `CLAUDE.md` / `AGENTS.md` are *generated* from these, via `make rules`) list the new dev CLI command; `docs/contribute/drift-contracts.md` adds the artifact to the Derived tier and to the never-review-generated-output corollary; CHANGELOG under `[Unreleased] / Added`.

**Still open, deliberately:** the four (six, counting the starter test files) consumer sites are untouched — they are the release-gated cross-repo sweep's job, and the workspace forbids backward compatibility, so there is nothing to ship them early. The snapshot is what makes the *next* rename visible; this one still needs the sweep.

Gates: `make agent-check`, `make drift-check`, and the errors / CLI / kit test slice all green.

---

## FU-2 — The img-gen neutrality guard is weaker than its comment, and its recorded remedy is wrong

> ✅ **DONE** — see [what shipped](#what-shipped-1) at the end of this section.

### Verified still true

Both holes are real, in `tests/unit/pipelex/cogt/img_gen/test_img_gen_mapping_neutrality.py`:

- **(a) Transitive vendor SDKs are unguarded.** `_import_roots` AST-parses only each mapping module's *own* file, and `_CLOSURE_SCRIPT` counts only names starting with `pipelex.providers`. A vendor SDK reached through some other `pipelex.cogt` module passes both checks.
- **(b) The glob under-claims its own coverage.** `_MAPPING_DIR.glob("img_gen_*_mapping.py")` is non-recursive and suffix-keyed, while its comment reads *"so a third taxonomy family is covered the day it lands"*. That holds only for a family landing in that exact directory under that exact name.

### ⚠ The recorded remedy rests on a claim that is false

The tracker's version of this item says:

> Measured clean today — **zero** vendor-SDK imports anywhere in `pipelex/` outside `providers/` — and *that* is the stronger invariant, unguarded and worth a repo-wide test of its own rather than a denylist bolted onto this one.

**That measurement does not hold.** Re-taken 2026-07-28 with an AST walk over `pipelex/` excluding `pipelex/providers/`:

| module | SDK | form |
| --- | --- | --- |
| `pipelex/tools/pdf/pypdfium2_renderer.py:8-10` | `pypdfium2`, `pypdfium2.raw` | **module-level** |
| `pipelex/tools/storage/s3_storage_provider.py` | `botocore.config`, `botocore.exceptions` | deferred |
| `pipelex/tools/storage/gcp_storage_provider.py` | `google.cloud`, `google.api_core.exceptions` | deferred |
| `pipelex/tracing/dynamodb_event_log.py` | `boto3`, `boto3.dynamodb.conditions`, `botocore.exceptions` | deferred |
| `pipelex/reporting/reporting_manager.py:28-29` | `botocore.exceptions` | deferred |

These are legitimate — they are *infrastructure* SDKs, not inference-provider SDKs, and they are exactly the split M2's own review recorded: `providers/storage/` is a registration shim while the implementations live under `pipelex/tools/`. But **a repo-wide "no vendor SDK outside `providers/`" test would be red on day one.** Do not write it.

Reproduce with:

```bash
.venv/bin/python - <<'PY'
import ast, os, sys
VENDOR={"openai","anthropic","google","mistralai","boto3","botocore","fal_client","docling",
        "linkup","huggingface_hub","transformers","azure","portkey_ai","pypdfium2","vertexai"}
for dp,dn,fs in os.walk("pipelex"):
    dn[:]=[d for d in dn if d!="__pycache__"]
    if dp.startswith("pipelex/providers"): continue
    for f in sorted(fs):
        if not f.endswith(".py"): continue
        p=os.path.join(dp,f)
        for n in ast.walk(ast.parse(open(p,encoding="utf-8").read())):
            if isinstance(n,ast.Import): rs=[(a.name.split(".")[0],a.name) for a in n.names]
            elif isinstance(n,ast.ImportFrom) and n.level==0 and n.module: rs=[(n.module.split(".")[0],n.module)]
            else: continue
            for r,full in rs:
                if r in VENDOR: print(f"{p}:{n.lineno}  {full}")
PY
```

### The invariant that *is* true and worth pinning

Measured the same day: **`pipelex/cogt/**` imports zero vendor SDKs.** Its only third-party import roots are framework and infrastructure deps — `pydantic`, `httpx`, `instructor`, `opentelemetry`, `polyfactory`, `tenacity`, `rich`, `PIL`, `typing_extensions`, `datamodel_code_generator`. And `cogt → pipelex.providers` is exactly the documented set:

```
pipelex/cogt/config_cogt.py:7-10          → providers.{anthropic,google,mistral,openai}.*_config   (4, documented — D-M2-2)
pipelex/cogt/model_backends/backend_factory.py:53 → providers.openai.vertexai_factory              (1, deferred, known)
```

### Recommendation — two small edits, no machinery

1. **Soften the glob comment (b)** to what it proves: the glob covers a new family only if it lands in `pipelex/cogt/img_gen/` under the `img_gen_*_mapping.py` name. One line. Do not bind the convention with a test — this track's whole argument was placement over indirection, and F1 is not the place to grow machinery.

2. **Replace the proposed repo-wide test (a) with a golden set of the `cogt → pipelex.providers` statements.** Pin the five above; any new edge fails. It is true today, it is the invariant `docs/contribute/hub-layering.md` → "Known inversions" already documents in prose, and it catches the realistic regression (someone adds a sixth `cogt → vendor` import) — which is precisely the class of defect F1 existed to remove and which **no other gate in the repo can see**, since `pipelex.cogt` and `pipelex.providers` are both runtime-layer and the hub guard is blind to an edge between them by construction.

3. **Correct the false claim** wherever it is recorded, so nobody builds the wrong test later on the strength of it.

The transitive hole (a) is then still technically open — a vendor SDK reached through a third `cogt` module would pass — but it is unreachable while `cogt/` imports no vendor SDK at all, which item 2 pins directly. That is a better trade than a denylist.

### What shipped

Both measurements re-taken before starting, and both held: the vendor-SDK scan still returns the same five infrastructure-SDK modules outside `providers/` (so the recorded remedy is still false), and `cogt`'s third-party roots are still exactly the ten framework/infrastructure packages with the same five `cogt → pipelex.providers` statements.

| file | change |
| --- | --- |
| `tests/unit/pipelex/cogt/test_cogt_dependency_boundaries.py` | new — the two golden sets |
| `tests/unit/pipelex/cogt/img_gen/test_img_gen_mapping_neutrality.py` | glob comment softened to what it proves; header notes where the transitive hole is closed |
| `docs/contribute/hub-layering.md` | "Known inversions" gains the bullet binding the prose list to the test, and the refutation of the repo-wide generalization |
| `CHANGELOG.md` | `[Unreleased] / Added` |

Decisions taken, and why:

- **Two golden sets, not one.** Item 2 asked for the `cogt → pipelex.providers` edges, but that set alone does not close its own closing argument: a bare `import openai` inside a `cogt` module is not a providers edge, so it would pass. The vendor-free claim is pinned as its own assertion — as an **allowlist of third-party import roots**, not a vendor denylist. Same golden-set shape as the edges, no list of vendor names to keep current, and a new framework dependency surfaces for review as one line rather than slipping through a denylist's gaps.
- **Edges are addressed by `source -> target [form]`, never by line number.** Line numbers are pure churn. The **form** (`module-level` / `deferred` / `type-checking`) is carried on purpose: promoting the deferred `vertexai_factory` import to module level is a real change — it is what would put the target in every closure touching `backend_factory` — and a set keyed on the statement alone would not see it.
- **Relative imports are resolved, not skipped.** The sibling neutrality test's helper skips `level > 0`, which is safe there (one directory) but would be a hole here: `from ...providers.openai import x` inside `pipelex/cogt/llm/` resolves to a real edge. Negative-tested with a probe at that exact shape.
- **The glob convention stays unbound by a test.** Item 1 said one line; softening the comment is the whole fix. A naming rule enforced by machinery is the shape this track spent four review rounds deleting, and the unglobbed-mapping worry is answered by the vendor-free assertion instead — an uncovered mapping module still cannot carry an SDK.

Negative-tested by planting a probe module under `pipelex/cogt/` carrying `import openai`, a module-level provider import, a `TYPE_CHECKING` one and a deferred one: both tests fail, all three forms are classified correctly, and the messages name added/removed rows. A second probe under `pipelex/cogt/llm/` confirmed the relative-import resolution.

**On item 3 (correct the false claim).** The tracker section that carried it no longer exists — the claim survives only in the quote block above, where it is already refuted in place. So the correction was put somewhere durable instead: `docs/contribute/hub-layering.md` now states, in the section whose stated job is keeping the document honest, that the repo-wide generalization is false and why. That is where someone would reason their way to the wrong test; `wip/` is archived at track end.

Gates: `make agent-check`, `make drift-check`, `make agent-test` all green.

---

## FU-3 — The bookkeeping files a bulk rewrite breaks are still ungated

> ✅ **DONE** — see [what shipped](#what-shipped-2) at the end of this section.

### Verified: the gate is absent, the artifacts are clean

No sort check and no durations check exist anywhere in `Makefile`, `scripts/` or `tests/` — confirmed by grep across all three. Neither `make check` nor `make agent-check` covers either file.

But both artifacts are healthy right now, so there is no fire:

| artifact | measured 2026-07-28 | verdict |
| --- | --- | --- |
| `subject_grants.toml` | grants present, **0 out-of-order pairs** | the `bc22ba934` re-sort holds |
| `.test_durations` | entries vs live tests collected with `-m ""`; **2 orphan node ids**, **0 dead file paths** | clean |

The two orphans are the `pipe_img_gen` parametrizations keyed on the generated model-set fixture — profile-dependent, already identified as such during F1's third review round, not stale. Live tests carrying no duration entry are expected (tests added since the last `--store-durations` run); pytest-split treats an unknown id as average duration.

So the issue as stated is precisely: **nothing would tell us if it drifted again.** Three instances on the modularity branch, each found by hand well after the fact.

### Recommendation — do the sort check; reshape the durations check before writing it

**Do: the `subject_grants.toml` sort assertion.** It is the one of the three that broke silently and stayed broken across three commits, and it is genuinely trivial — `pipelex/cli/dev_cli/commands/keyword_only_guard.py` already parses the file (`SUBJECT_GRANTS_FILE`, `load_subject_grants()` at `:261`). Add the key-order assertion inside the existing guard so it rides `make check-keyword-only` → `make agent-check` → CI. No new Make target. The invariant is already written down as one in `docs/contribute/keyword-only-arguments.md:37` (*"machine-written and sorted by key"*) — this just enforces what the docs claim.

Note `load_subject_grants()` returns a `dict`, which does not preserve evidence of file order; read the raw text for the key sequence.

**Reshape: gate `.test_durations` on the file path, not the node id.**

A bulk path rewrite breaks **file paths**. Parametrization churn breaks **node ids** and is benign. Asserting `{k.split("::")[0] for k in durations}` all exist on disk is:

- unambiguous — no tolerance policy, no explaining away legitimately-stale parametrizations,
- **green today** (0 dead paths out of 907 distinct files),
- cheap — pure filesystem check, no pytest collection run at all.

Whereas a strict node-id check needs a full unfiltered collection *and* a policy for both current false positives.

⚠ **Two traps for whoever writes it**, both of which cost real time already:

- If you do collect node ids for any reason, run with **`-m ""`**. The marker filter in `addopts` hides a large slice of the suite (mostly `tests/e2e/`), so a naive `--collect-only` reports every e2e entry as an orphan.
- Parse a collect dump with `.splitlines()`, **never `.split()`**. Parametrized ids contain spaces (`[CV Batch-tests/data/graphs/cv_batch.json]`), so whitespace-splitting shreds them into tokens and manufactures hundreds of phantom orphans. I hit this while measuring for this doc — same family as M2's `[a-z_]*` character class, and worse than a rewrite bug, because the verification is what licenses "done".

**Skip the third instance.** The matched triple (guard tuple / closure predicate / `hub-layering.md` snippet) is already mechanically bound by tests as of M1c; only the design doc's fourth copy is unasserted, and that lives in `wip/`, which is archived at track end.

### What shipped

Both measurements re-taken before starting, and both held: no sort or durations check exists in `Makefile` / `scripts/` / `tests/` (the only `.test_durations` mentions are the regeneration target's own comment and two CI workflow comments), and both artifacts are still clean — 1757 grants with **0 out-of-order pairs**, 9242 duration entries across 907 distinct files with **0 dead paths**. Both halves were done, the durations one in the reshaped form the item prescribed.

| file | role |
| --- | --- |
| `pipelex/cli/dev_cli/commands/keyword_only_guard.py` | `ViolationKind.UNSORTED_GRANT` + `find_unsorted_grants()` — the registry-order rule |
| `pipelex/cli/dev_cli/commands/check_keyword_only_cmd.py` | folds the registry-order violations into the full-scan gate |
| `tests/unit/pipelex/cli/dev/test_subject_grant_registry.py` | `TestSubjectGrantRegistryOrder` |
| `tests/unit/repo/test_test_durations_paths.py` | the `.test_durations` file-path gate |
| `docs/contribute/keyword-only-arguments.md`, `Makefile`, `CHANGELOG.md` | docs |

Decisions taken, and why:

- **The order rule reads the raw text, and cross-checks the scan against the parser.** The item warned that `load_subject_grants()` returns a `dict`, which is not evidence of file order. It is worth being precise about *why*, because the shortcut is tempting: CPython dicts do preserve insertion order and `tomllib` does insert in document order, so reading order off the parsed dict would in fact work today — it would just be resting on undocumented behaviour of a parser for a format that declares table order insignificant. So the scan is a line-anchored regex over table headers. That opens its own hole (a multi-line rationale can carry a line that looks like a header), closed by asserting the scanned key set equals the parsed key set and raising `SubjectGrantRegistryError` when it does not. An entry the scan cannot see must fail loudly, not silently drop out of the rule's domain — the FU-1 anti-vacuity concern in a different costume.
- **Registry order is a full-scan rule, wired at the command layer, not in `collect_all_violations`.** Two reasons. It is a whole-file property, so the per-file `PostToolUse` hook cannot see it — exactly the boundary `dead-grant` already sits on. And `collect_all_violations` is filesystem-pure with respect to the registry (its callers pass `grants` in, and its tests run from a `tmp_path` with no `subject_grants.toml` at all); making it read the registry off disk would have broken four existing tests for no gain.
- **No re-sorting fixer.** `--fix` rewrites signatures; the registry has exactly one writer, the `subject-grant` command, and the guard module is stdlib-only by design (the writer needs tomlkit). The remedy is stated instead: re-record any grant, which rewrites the whole file sorted.
- **The durations gate is on the file path only, and not parametrized.** Per the item. The two known orphan node ids are profile-dependent parametrizations, and a node-id gate would need a full unfiltered collection plus a tolerance policy for them; the path gate needs neither, and it is the one that catches a bulk rewrite. Anti-vacuity is a non-parametrized "the file is committed and not empty" test, plus a shape assertion that every key really is `<path.py>::<test>` — without which "every extracted path exists" could pass over keys that are not paths at all.
- **Both traps in the item were avoided by not collecting node ids at all** — no `-m ""` run, no collect dump to parse, so neither the marker-filter nor the `.split()` trap is reachable. That is a third argument for the path gate the item did not make: the cheap check is also the one with no way to mis-measure.

Negative-tested, all four: swapping two adjacent registry entries fails with the offending key, the registry line number, and the entry it sorts before; a multi-line rationale carrying a phantom `["…"]` header fails with the scan/parser count mismatch; a `.test_durations` entry under a moved-away path fails naming the dead path; a non-node-id key fails the shape assertion. Both real artifacts restored clean afterwards (`git diff --stat` empty).

Docs updated in the same change: `docs/contribute/keyword-only-arguments.md` in five places (the kinds table, the order paragraph under "Staleness is symmetric", the hook bullet, the auto-fix paragraph — which listed only `grant-param-mismatch` as never-rewritten and silently omitted `dead-grant` — and a pointer after the top-of-page rule list, since that list is scoped to *signatures* and registry order is not a signature property); the `store-test-durations` comment in the `Makefile` names its new gate; CHANGELOG under `[Unreleased] / Added`. The `keyword-only-convention` drift contract was reviewed and acked, with its dogfood-log entry.

**Noticed, not fixed:** `make check-test-badge` is red on this branch — badge 9146 vs 9241 collected. It was already off by 88 before this change (7 tests added here), the badge is refreshed at release time by the release skill, and its CI job only runs on PRs into `main`. Bumping it mid-branch would just make it stale differently before the release.

---

## Re-verify before starting

Numbers above are dated, not eternal. Re-take them first — the *shape* (zero vs non-zero, present vs absent) is the criterion, not the absolute count.

```bash
# FU-1 — is error_type still the bare class name? are the four consumers still on the old string?
git grep -n "error_type=type(self).__name__" -- pipelex/base_exceptions.py
cd .. && /usr/bin/grep -rn "PipelexInterpreterError" \
  mthds-starter-js/src pipelex-starter-js/src vscode-pipelex/editors playroom/src 2>/dev/null

# FU-2 — the vendor-SDK scan above, plus the cogt edges
git grep -n "pipelex\.providers" -- pipelex/cogt/

# FU-3 — do the gates exist? are the artifacts still clean?
git grep -n "test_durations\|sorted" -- Makefile | head
.venv/bin/python -c "
import json,pathlib
d=json.load(open('.test_durations'))
dead=[f for f in {k.split('::')[0] for k in d} if not pathlib.Path(f).exists()]
print('dead duration file paths:',len(dead))"
```

⚠ Use `git grep` or `/usr/bin/grep` for any completeness sweep — this shell's `grep` is a ugrep wrapper that honours `.gitignore`, so from the workspace root it silently skips every sibling repo and returns a false clean.
