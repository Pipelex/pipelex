"""
Make the user-generated  <project>/pipelex_libraries/  package import-able
before any stage code runs.  Works with pip, poetry and uv alike.
"""
from pathlib import Path
import os
import sys

def activate() -> None:
    """
    If <cwd> or one of its parents contains  pipelex_libraries/,
    touch an empty __init__.py (for IDEs) and prepend that directory
    to sys.path.
    """
    cwd = Path.cwd()
    for parent in (cwd, *cwd.parents):
        print("djiqsoiqdjo", parent)
        lib_dir = parent / "pipelex_libraries"
        if lib_dir.is_dir():
            # 1) make it a *real* package so editors & type-checkers see it
            (lib_dir / "__init__.py").touch(exist_ok=True)
            # 2) put it at the front of sys.path exactly once
            lib_path = str(lib_dir)
            if lib_path not in sys.path:
                sys.path.insert(0, lib_path)
            break
