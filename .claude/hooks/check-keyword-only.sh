#!/usr/bin/env bash
# PostToolUse hook: enforce the keyword-only-arguments convention on the just-edited pipelex source file.
#
# Runs the stdlib-only AST guard (pipelex/cli/dev_cli/commands/keyword_only_guard.py) on the single
# edited file — ~0.04s, because it is invoked by FILE PATH (not `python -m ...`), which skips importing
# the `pipelex` package __init__ chain entirely. On a violation the guard prints the offending
# signatures to stderr and exits 2, which Claude Code surfaces back to the agent as blocking feedback.
#
# Out-of-scope edits exit 0 fast: non-.py files are rejected here in bash (no Python launch), and the
# precise "is it under pipelex/, not __pycache__" decision is made in Python (see relative_source_path).

set -euo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$PWD}"
GUARD="$PROJECT_DIR/pipelex/cli/dev_cli/commands/keyword_only_guard.py"
PYTHON="$PROJECT_DIR/.venv/bin/python"

# Read the tool-call JSON from stdin and extract tool_input.file_path (pure bash, no jq — house style).
# `|| true`: grep exits 1 when a payload carries no file_path, which under `set -o pipefail` would
# abort the assignment before the empty-check below — we want a clean pass-through instead.
input=$(cat)
file_path=$(echo "$input" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/' || true)

# Fast, silent pass-through: no file, not a .py file, or a checkout without the venv / guard in place.
if [ -z "$file_path" ]; then
  exit 0
fi
case "$file_path" in
  *.py) ;;
  *) exit 0 ;;
esac
[ -x "$PYTHON" ] || exit 0
[ -f "$GUARD" ] || exit 0

# Run from the repo root so the guard's cwd-relative path resolution is deterministic, then hand off
# (exec → the guard's exit code 0/2 and its stderr become this hook's, with no extra shell layer).
cd "$PROJECT_DIR"
exec "$PYTHON" "$GUARD" "$file_path"
