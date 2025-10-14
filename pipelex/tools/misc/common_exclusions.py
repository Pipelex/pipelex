"""Common exclusion patterns for directory scanning operations."""

# Directories to exclude when scanning for Python files or PLX files
# These directories are typically build artifacts, caches, or environment folders
EXCLUDED_SCAN_DIRS = frozenset(
    {
        ".venv",
        ".git",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "node_modules",
        ".env",
        "results",
    }
)
