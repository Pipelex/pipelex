---
description: "Run, validate, and build against a method fetched straight from a public GitHub repository, addressed as github.com/owner/repo[/name][@tag]."
---

# Run a Method by Address

Every command that takes an installed method name — `pipelex run method`, `pipelex validate method`, the `pipelex build` method commands, and their agent-CLI twins — also accepts a **method reference**: a globally resolvable address pointing at a package in a public GitHub repository. Pipelex fetches the repository, locates the package inside it, and runs it, with no install step.

```bash
# Run a method from the public library at a pinned tag
pipelex run method github.com/Pipelex/methods/documents@v0.1.0 --inputs inputs.json

# Same method, default branch at HEAD (no tag)
pipelex run method github.com/Pipelex/methods/documents --pipe extract_document_text

# Validate a method by address
pipelex validate method github.com/Pipelex/methods/documents --pipe extract_document_text
```

## The reference grammar

A method reference is `<address>[@<tag>]`:

- **The address** is `github.com/<owner>/<repo>[/<selector>]` (GitHub only for now). The first two path segments name the repository — the clone URL is derived as `https://github.com/<owner>/<repo>.git` — and anything after them selects a package *within* the repository.
- **A bare address** (no `@<tag>`) means the repository's default branch at HEAD.
- **`@<tag>`** pins the repository at that git tag. The recommended form is `vX.Y.Z` (e.g. `@v0.2.0`).

Full browser URLs keep working: `https://github.com/owner/repo` (with or without `.git`) is normalized into the address form, and a `/tree/<branch>/...` deep link is accepted with the branch segment discarded — only tags pin a revision.

Every fetch prints its provenance — the resolved package address, the tag when one was named, and the **commit SHA of what was actually cloned**. Tags can move; the SHA is what makes a run reproducible and explainable.

## How the package is located: manifest identity

The package inside the clone is located by **manifest identity, not directory path**. Pipelex scans the clone for `METHODS.toml` files and selects the one whose identity matches the requested address:

- A **repo-root package** matches when its manifest `address` equals the requested address.
- A **package in a library repo** matches when its manifest `address + "/" + name` equals the requested address. For example, in [`Pipelex/methods`](https://github.com/Pipelex/methods) the documents package's manifest carries `address = "github.com/Pipelex/methods"` and `name = "documents"`, so its full address is `github.com/Pipelex/methods/documents` — wherever it sits in the repository tree.

Address comparison is case-insensitive, matching GitHub's own behavior for owner and repository names.

No match, or more than one, is a loud error listing the packages the clone does contain — so requesting a library repo's bare address tells you which packages it offers.

## The entry pipe

The pipe to run defaults to the manifest's `main_pipe`; `--pipe <code>` overrides it. A method with no `main_pipe` requires `--pipe`.

## Python in fetched methods: the hosted rule

What decides whether Python in a method is acceptable is **where it would execute**:

- `.mthds` content is data — always fine.
- **PipeFunc `.py`** is supported: on hosted deployments it executes in a network-blocked sandbox, never in the runner's process.
- **Python structure classes** (`StructuredContent` subclasses) are imported into the runner's own process, so *hosted execution accepts MTHDS concepts and sandboxed PipeFuncs, not in-process Python*. A fetched method declaring structure classes runs locally, but the CLI prints a hosted-parity warning: express the types as MTHDS concepts (inline structures) to keep the method hosted-runnable.

## Bounds

Fetched packages are bounded: the clone has a fixed timeout, and the selected package is capped in file count and total bytes (tunable via the `PIPELEX_MAX_FETCHED_PACKAGE_FILES` and `PIPELEX_MAX_FETCHED_PACKAGE_TOTAL_KIB` environment variables). A package exceeding the caps is rejected with a clear error.

## Related Documentation

- [CLI Run](run.md)
- [CLI Validate](validate.md)
- [Methods & Packages](../../building-methods/packages.md)
