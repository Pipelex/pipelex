#!/usr/bin/env bash
# Materialize the five bare-reference demo closures used by ../README.md.
#
# Writes OUTSIDE the repository by default (a fresh mktemp dir), on purpose: these bundles are
# deliberately pathological, and dropping them into the tree would move the corpus counts that
# classify-bare-refs.py reports over `.`.
#
# Usage:  ./wip/pipe-refs/probes/make-demos.sh [target_dir]
# Prints the target directory on stdout as its last line.

set -euo pipefail

TARGET="${1:-$(mktemp -d -t bare-ref-demos)}"
mkdir -p "$TARGET"

# --- 1. ambiguous: two domains declare `summarize`; alpha calls it bare -----------------------
# Standard: resolves to alpha.summarize (found in the own domain, the search stops).
# Runtime:  PipeLibraryError, ambiguous.
mkdir -p "$TARGET/ambiguous"
cat >"$TARGET/ambiguous/alpha.mthds" <<'EOF'
domain      = "alpha"
description = "Alpha domain"

[concept]
Note = "A short note"

[pipe.run_flow]
type        = "PipeSequence"
description = "Alpha's entry point, calling a bare 'summarize' that alpha itself declares"
inputs      = { note = "Note" }
output      = "Note"
steps       = [{ pipe = "summarize", result = "summary" }]

[pipe.summarize]
type        = "PipeLLM"
description = "Alpha's own summarize"
inputs      = { note = "Note" }
output      = "Note"
prompt      = "Summarize $note the alpha way"
EOF
cat >"$TARGET/ambiguous/beta.mthds" <<'EOF'
domain      = "beta"
description = "Beta domain, which happens to reuse the pipe code 'summarize'"

[concept]
Memo = "A short memo"

[pipe.summarize]
type        = "PipeLLM"
description = "Beta's own summarize"
inputs      = { memo = "Memo" }
output      = "Memo"
prompt      = "Summarize $memo the beta way"
EOF

# --- 2. fallthrough: only beta declares `present`; alpha calls it bare ------------------------
# Standard: error, no fall-through.  Runtime: resolves to beta.present.
mkdir -p "$TARGET/fallthrough"
cat >"$TARGET/fallthrough/alpha.mthds" <<'EOF'
domain      = "alpha"
description = "Alpha domain"

[concept]
Note = "A short note"

[pipe.run_flow]
type        = "PipeSequence"
description = "Alpha's entry point, calling a bare 'present' it does not declare"
inputs      = { note = "Note" }
output      = "Note"
steps       = [{ pipe = "present", result = "presented" }]
EOF
cat >"$TARGET/fallthrough/beta.mthds" <<'EOF'
domain      = "beta"
description = "Beta domain, the only declarer of 'present'"

[pipe.present]
type        = "PipeLLM"
description = "Beta's present"
inputs      = { note = "alpha.Note" }
output      = "alpha.Note"
prompt      = "Present $note"
EOF

# --- 3 & 4. export bypass, and its control ----------------------------------------------------
# One package. `beta.helper` is NOT exported. The bare form reaches it; the qualified form is
# rejected. Same pipe, same manifest, same run.
for variant in export-bypass export-bypass-control; do
    mkdir -p "$TARGET/$variant/alpha" "$TARGET/$variant/beta"
    cat >"$TARGET/$variant/METHODS.toml" <<'EOF'
[package]
address       = "github.com/example/bypass-demo"
display_name  = "Bypass Demo"
version       = "1.0.0"
description   = "Two domains; beta exports nothing"
authors       = ["Example"]
license       = "MIT"
mthds_version = "1.0.0"

[exports.alpha]
pipes = ["run_flow"]
EOF
    cat >"$TARGET/$variant/beta/beta.mthds" <<'EOF'
domain      = "beta"
description = "Beta domain; 'helper' is NOT listed in [exports]"

[pipe.helper]
type        = "PipeLLM"
description = "Beta's private helper"
inputs      = { note = "alpha.Note" }
output      = "alpha.Note"
prompt      = "Help with $note"
EOF
done
cat >"$TARGET/export-bypass/alpha/alpha.mthds" <<'EOF'
domain      = "alpha"
description = "Alpha domain"

[concept]
Note = "A short note"

[pipe.run_flow]
type        = "PipeSequence"
description = "Reaches beta's non-exported 'helper' by bare code"
inputs      = { note = "Note" }
output      = "Note"
steps       = [{ pipe = "helper", result = "helped" }]
EOF
cat >"$TARGET/export-bypass-control/alpha/alpha.mthds" <<'EOF'
domain      = "alpha"
description = "Alpha domain"

[concept]
Note = "A short note"

[pipe.run_flow]
type        = "PipeSequence"
description = "Names the same non-exported pipe, qualified"
inputs      = { note = "Note" }
output      = "Note"
steps       = [{ pipe = "beta.helper", result = "helped" }]
EOF

# --- 5. concept-collision: two domains declare `Note`; each references it bare -----------------
# The crate normalizer qualifies each to its own domain; the live ConceptLibrary's bare search
# (search_domain_codes=None) raises "Multiple concepts found" for the same authored text.
mkdir -p "$TARGET/concept-collision"
cat >"$TARGET/concept-collision/alpha.mthds" <<'EOF'
domain      = "alpha"
description = "Alpha domain"

[concept]
Note = "Alpha's note"

[pipe.alpha_summarize]
type        = "PipeLLM"
description = "Uses a bare 'Note'"
inputs      = { note = "Note" }
output      = "Note"
prompt      = "Summarize $note"
EOF
cat >"$TARGET/concept-collision/beta.mthds" <<'EOF'
domain      = "beta"
description = "Beta domain, which also declares 'Note'"

[concept]
Note = "Beta's note"

[pipe.beta_summarize]
type        = "PipeLLM"
description = "Uses a bare 'Note'"
inputs      = { note = "Note" }
output      = "Note"
prompt      = "Summarize $note"
EOF

echo "$TARGET"
