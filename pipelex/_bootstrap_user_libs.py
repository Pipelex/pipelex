import sys
from pathlib import Path

# ------------------------------------------------------------------------
#  Public helper: run once, keep user libs import-able
# ------------------------------------------------------------------------


def activate() -> None:
    # 1) Re-create Poetry’s behaviour: put <cwd> itself on sys.path
    root = Path.cwd()
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)

    # 2) If a pipelex_libraries folder already exists, also touch __init__.py
    #    (helps IDE & static type-checkers) and ensure the *exact* folder is
    #    on sys.path.  When it does **not** exist yet, nothing else to do —
    #    as soon as the user runs `pipelex init-libraries`, the directory will be
    #    created *inside* <root>, which is already import-able thanks to (1).
    for parent in (root, *root.parents):
        lib_dir = parent / "pipelex_libraries"
        if lib_dir.is_dir():
            # 1) make it a *real* package so editors & type-checkers see it
            (lib_dir / "__init__.py").touch(exist_ok=True)
            # 2) put it at the front of sys.path exactly once
            lib_path = str(lib_dir)
            if lib_path not in sys.path:
                sys.path.insert(0, lib_path)
            break
