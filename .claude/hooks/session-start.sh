#!/bin/bash
set -euo pipefail

# Only run in remote Claude Code sessions (web)
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# Set CI so the runtime boots in CI integration mode
echo 'export CI=true' >> "$CLAUDE_ENV_FILE"

# Install all dependencies (creates venv if needed, runs uv sync --all-extras)
make install
