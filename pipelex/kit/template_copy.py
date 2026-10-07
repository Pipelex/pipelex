"""The one walk that lays the kit's configuration templates into a configuration directory.

`pipelex init` copies the configuration files with it, and the first boot fills the home configuration
directory with it, so the two agree on which files a directory receives and on what "already there"
means. It imports nothing but the standard library, because the boot's configuration loader calls it.

Two rules hold for every write. Nothing is ever written through a symbolic link: a link at a file's path is
kept, or replaced as a link, and the walk never enters a link to a directory, valid or dangling. And a file
appears whole or not at all: it is written under a temporary name beside its destination and renamed into
place, so a copy cut short by a full disk or a killed process leaves no truncated file behind.
"""

import os
import shutil
import tempfile
from pathlib import Path, PurePosixPath


def can_fill_directory(*, directory: Path) -> bool:
    """Whether kit files may be laid into this path as a directory, creating it if need be.

    True when nothing stands there or a real directory does. False for a symbolic link of any kind, valid
    or dangling, since filling it would write wherever it points, and for anything else that is not a
    directory, such as a file, which creating the directory would fail on: whatever stands there is the
    user's, with everything under it.
    """
    if not os.path.lexists(directory):
        return True
    return not directory.is_symlink() and directory.is_dir()


def copy_file_atomically(*, source: Path, destination: Path) -> None:
    """Copy a file so that it appears at its destination whole or not at all.

    The copy, with the metadata `shutil.copy2` carries, is written under a temporary name in the
    destination's directory, which must exist, then renamed over the destination. A link at the destination
    is replaced as a link, never written through. The temporary file is removed when the copy fails; only a
    process killed between the two steps can leave one behind, under a name no reader looks for.
    """
    file_descriptor, temporary_name = tempfile.mkstemp(dir=destination.parent, prefix=f".{destination.name}.", suffix=".partial")
    os.close(file_descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copy2(source, temporary)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


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
    or a directory, is left out at any depth, with everything under it, and so is a kit directory whose
    destination `can_fill_directory` refuses, such as a link or a file standing there. A file the target
    already holds, a symbolic link included even when it dangles, is kept as it is unless `overwrite` is set,
    so without it a directory that holds every file is not written at all. Each file is written with
    `copy_file_atomically`. With `dry_run` nothing is written, and the result says what a real run would copy.

    Returns:
        The paths of the files copied, relative to `template_dir` and in POSIX form, in walk order.
    """
    copied: list[str] = []

    def mirror(*, src_dir: Path, relative_dir: PurePosixPath) -> None:
        for src_item in sorted(src_dir.iterdir()):
            if src_item.name in skip_names:
                continue
            relative_item = relative_dir / src_item.name
            dst_item = target_dir / relative_item
            if src_item.is_dir():
                if can_fill_directory(directory=dst_item):
                    mirror(src_dir=src_item, relative_dir=relative_item)
                continue
            # `lexists` rather than `exists`: a link is there even when it dangles, and copying through it
            # would write wherever it points, or fail on every run when that place does not exist.
            if not overwrite and os.path.lexists(dst_item):
                continue
            if not dry_run:
                dst_item.parent.mkdir(parents=True, exist_ok=True)
                copy_file_atomically(source=src_item, destination=dst_item)
            copied.append(relative_item.as_posix())

    mirror(src_dir=template_dir, relative_dir=PurePosixPath())
    return copied
