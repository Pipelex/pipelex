"""The one walk that lays the kit's configuration templates into a configuration directory.

`pipelex init` copies the configuration files with it, and the first boot fills the home configuration
directory with it, so the two agree on which files a directory receives and on what "already there"
means. It imports nothing but the standard library, because the boot's configuration loader calls it.
"""

import shutil
from pathlib import Path, PurePosixPath


def copy_kit_templates(
    *,
    template_dir: Path,
    target_dir: Path,
    skip_names: frozenset[str],
    overwrite: bool,
    dry_run: bool = False,
) -> list[str]:
    """Mirror a kit template tree into a configuration directory, one file at a time.

    Every file under `template_dir` is copied to the same relative path under `target_dir`, and the
    directories a copied file needs are created on the way. An entry whose name is in `skip_names`, a file
    or a directory, is left out at any depth, with everything under it. A file the target already holds is
    kept as it is unless `overwrite` is set, so without it a directory that holds every file is not written
    at all. With `dry_run` nothing is written, and the result says what a real run would copy.

    Returns:
        The paths of the files copied, relative to `template_dir` and in POSIX form, in walk order.
    """
    copied: list[str] = []

    def mirror(*, src_dir: Path, relative_dir: PurePosixPath) -> None:
        for src_item in sorted(src_dir.iterdir()):
            if src_item.name in skip_names:
                continue
            relative_item = relative_dir / src_item.name
            if src_item.is_dir():
                mirror(src_dir=src_item, relative_dir=relative_item)
                continue
            dst_item = target_dir / relative_item
            if dst_item.exists() and not overwrite:
                continue
            if not dry_run:
                dst_item.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_item, dst_item)
            copied.append(relative_item.as_posix())

    mirror(src_dir=template_dir, relative_dir=PurePosixPath())
    return copied
