# MTHDS Standard — Client Project Update Brief

## Context

The core **Pipelex** library has been updated to implement the **MTHDS standard**. Client projects — cookbooks, example repos, tutorials, starter kits — must now be updated to match.

This brief tells you exactly what to change and what to leave alone.

### What changed in Pipelex core

1. **File extension**: `.plx` → `.mthds` (hard switch, no backward compatibility)
2. **User-facing terminology**: "workflow" → "method" where it refers to the MTHDS concept
3. **Hierarchical domains**: domain codes now support dotted paths (e.g., `legal.contracts`)
4. **Pipe namespacing**: pipes can now use domain-qualified references (e.g., `scoring.compute_score`)
5. **Concept reference parsing**: uses split-on-last-dot rule for hierarchical domains (e.g., `legal.contracts.NonCompeteClause`)
6. **Package manifest**: `METHODS.toml` declares package identity, dependencies, and exports
7. **Visibility model**: pipes are private by default when a manifest exists; exported via `[exports]`
8. **Cross-package references**: `alias->domain.pipe_code` syntax for referencing pipes/concepts from dependency packages
9. **Local path dependencies**: dependencies with `path = "..."` in `METHODS.toml` are resolved from the local filesystem
10. **CLI commands**: `pipelex pkg init`, `pipelex pkg list`, `pipelex pkg add`, `pipelex pkg lock`, `pipelex pkg install`, `pipelex pkg update`, `pipelex pkg index`, `pipelex pkg search`, `pipelex pkg inspect`, `pipelex pkg graph`, `pipelex pkg publish`
11. **Remote dependencies**: VCS dependencies with semver constraints, resolved via `pipelex pkg lock` and fetched via `pipelex pkg install`
12. **Reserved domains**: `native`, `mthds`, and `pipelex` are reserved — user packages must not use these as domain prefixes

---

## Step 1: Rename all `.plx` files to `.mthds`

Rename every `.plx` file in the project to `.mthds`. This includes:

- Example bundles
- Tutorial files
- Template files
- Test fixtures
- Any file with a `.plx` extension, regardless of directory

```bash
# Find all .plx files
find . -name "*.plx" -type f
```

Use `git mv` if the project is a git repo to preserve history.

---

## Step 2: Update file content — references to `.plx`

Search the entire codebase for the string `.plx` and replace with `.mthds` where it refers to the file extension. This includes:

- **Code files** (`.py`, `.ts`, `.js`, etc.): file path strings, glob patterns, file loading logic
- **Configuration files** (`.toml`, `.yaml`, `.json`, `Makefile`, `Dockerfile`, etc.): any path or pattern referencing `.plx`
- **Documentation** (`.md`, `.rst`, `.txt`): inline code, code blocks, file references
- **Shell scripts** (`.sh`, `.bash`): file paths, find/glob commands
- **CI/CD configs** (`.github/workflows/`, `.gitlab-ci.yml`, etc.): artifact paths, test commands

```bash
# Find all references
grep -rn "\.plx" --include="*" .
```

**Be precise**: `.plx` inside a word like `complex` or `display` is not a match. Target `.plx` as a file extension (typically preceded by a filename or followed by whitespace/punctuation/quote).

---

## Step 3: Replace "workflow" with "method" in user-facing text

Replace "workflow" → "method" (and "workflows" → "methods", "Workflow" → "Method", "Workflows" → "Methods") in:

- README files
- Tutorial prose and instructions
- Docstrings and comments that face the user
- CLI usage examples
- Error messages or log messages in example code
- Page titles, headings, and navigation labels

### What to replace

| Before | After |
|---|---|
| workflow | method |
| workflows | methods |
| Workflow | Method |
| Workflows | Methods |
| workflow file | method file |
| workflow bundle | method bundle |
| build a workflow | build a method |
| run the workflow | run the method |
| define workflows | define methods |

### What NOT to replace

- Generic programming usage of "workflow" unrelated to MTHDS/Pipelex (e.g., "CI/CD workflow", "development workflow", "GitHub Actions workflow")
- Internal Pipelex class names — these stay as-is (Pipelex is the implementation; MTHDS is the standard)
- Third-party documentation quotes
- The word "workflow" inside proper nouns or product names other than Pipelex

**Judgment call**: if "workflow" refers to what a user creates/runs/defines in a `.mthds` file, replace it. If it refers to a general software process, keep it.

---

## Step 4: Update README and documentation content

Beyond the search-and-replace above, review each documentation file for:

### File extension references in prose

Update sentences like:
- "Create a file called `my_example.plx`" → "Create a file called `my_example.mthds`"
- "Files use the `.plx` extension" → "Files use the `.mthds` extension"

### Code blocks and examples

Update every code block that shows:
- File names with `.plx`
- CLI commands referencing `.plx` files
- TOML content from `.plx` files (the TOML structure inside is unchanged — only the extension in the filename changes)
- Directory listings showing `.plx` files
- Import/load statements referencing `.plx` paths

### Hierarchical domain examples (if applicable)

If the project's documentation or examples discuss domains, update to reflect that domains can now be hierarchical:
- `domain = "contracts"` is still valid
- `domain = "legal.contracts"` is now also valid
- Concept references like `legal.contracts.NonCompeteClause` use split-on-last-dot parsing

### Cross-domain pipe references (if applicable)

If examples reference pipes from other domains, they should now use the domain-qualified syntax:
- Before: bare reference relying on same-domain resolution
- After: `domain_path.pipe_code` (e.g., `pipe_design.detail_pipe_spec`)

---

## Step 5: Update any programmatic references

If the client project contains code (scripts, utilities, helpers) that interacts with Pipelex:

- Update file extension constants or variables (e.g., `PLX_EXT = ".plx"` → `MTHDS_EXT = ".mthds"`)
- Update glob patterns (e.g., `**/*.plx` → `**/*.mthds`)
- Update any hardcoded file paths
- Update any CLI invocations that pass `.plx` file paths

---

## Step 6: Update `.gitignore` and similar configs

Check for `.plx`-related patterns in:
- `.gitignore`
- `.dockerignore`
- Editor configs (`.vscode/`, `.idea/`)
- Linter configs
- Build tool configs

---

## What NOT to do

- **Do NOT rename Python classes or internal Pipelex types.** Pipelex is the implementation brand. MTHDS is the open standard. Class names like `PipelexBundleBlueprint` stay as-is.
- **Do NOT change the TOML structure** inside `.mthds` files. The internal format is identical to what `.plx` used — only the extension changes.
- **Do NOT add backward-compatible `.plx` support.** This is a clean break.
- **Remote VCS dependencies are now supported.** If the project uses remote dependencies, run `pipelex pkg lock` and `pipelex pkg install` after adding them with `pipelex pkg add`. Only use `--path` for local development overrides.

---

## Step 7: Set up `METHODS.toml` if the project uses multiple domains

If the client project has multiple `.mthds` bundles across different domains, it should have a `METHODS.toml` manifest:

```bash
# Scaffold a manifest from existing bundles
pipelex pkg init
```

This creates a `METHODS.toml` with auto-discovered domains and all pipes exported. Review and trim the exports to only expose the intended public API.

To inspect the manifest:

```bash
pipelex pkg list
```

---

## Step 8: Declare dependencies for cross-package references

If the project depends on another MTHDS package (locally on disk):

```bash
pipelex pkg add github.com/org/scoring-lib --alias scoring_lib --version "^2.0.0" --path ../scoring-lib
```

This adds a `[dependencies]` entry to `METHODS.toml`. The `--path` flag points to the dependency's local directory. The `--alias` flag sets the name used in `->` references (auto-derived from the address if omitted).

In `.mthds` files, reference the dependency's pipes and concepts with the `->` syntax:

```toml
steps = [
    { pipe = "scoring_lib->scoring.compute_score", result = "score" },
]
inputs = { profile = "scoring_lib->scoring.CandidateProfile" }
```

---

## Acceptance criteria

- No remaining references to `.plx` as a file extension anywhere in the project (code, docs, configs, test fixtures)
- No remaining user-facing uses of "workflow" where "method" is the correct MTHDS term
- All renamed `.mthds` files are valid (same TOML content, just new extension)
- All code examples and CLI invocations in documentation use `.mthds`
- If the project has tests or a CI pipeline, they pass after the changes
- The project README accurately describes the MTHDS file format and terminology
- If the project uses multiple domains, a `METHODS.toml` exists with correct exports
- If the project depends on other packages, dependencies are declared with `pipelex pkg add` and `->` references resolve correctly
