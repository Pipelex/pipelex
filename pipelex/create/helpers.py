from pathlib import Path
from typing import Dict, List, Optional

from pipelex.tools.misc.file_utils import load_text_from_path


class PipelexSupportFiles:
    """Dictionary-like interface to access all files in .pipelex by their subpath."""

    def __init__(self, base_path: str = ".pipelex"):
        self.base_path = Path(base_path)
        self._file_cache: Dict[str, str] = {}

    def __getitem__(self, subpath: str) -> str:
        """Get file content by subpath (e.g., 'design_pipelines.md')."""
        if subpath not in self._file_cache:
            file_path = self.base_path / subpath
            if not file_path.exists():
                raise KeyError(f"File '{subpath}' not found in {self.base_path}")
            self._file_cache[subpath] = load_text_from_path(str(file_path))
        return self._file_cache[subpath]

    def __contains__(self, subpath: str) -> bool:
        """Check if a file exists by subpath."""
        file_path = self.base_path / subpath
        return file_path.exists() and file_path.is_file()

    def get(self, subpath: str, default: Optional[str] = None) -> Optional[str]:
        """Get file content by subpath with optional default."""
        try:
            return self[subpath]
        except KeyError:
            return default

    def keys(self) -> List[str]:
        """Get all available file subpaths."""
        if not self.base_path.exists():
            return []

        files: List[str] = []
        for file_path in self.base_path.rglob("*"):
            if file_path.is_file():
                subpath = str(file_path.relative_to(self.base_path))
                files.append(subpath)
        return sorted(files)

    def clear_cache(self) -> None:
        """Clear the internal file cache."""
        self._file_cache.clear()


def get_support_file(subpath: str) -> str:
    """Get pipeline creation rules from design_pipelines.md."""
    support_files = PipelexSupportFiles()
    return support_files[subpath]
