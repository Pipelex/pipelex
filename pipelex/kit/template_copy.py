"""The one walk that lays the kit's configuration templates into a configuration directory.

`pipelex init` copies the configuration files with it, and the first boot fills the home configuration
directory with it, so the two agree on which files a directory receives and on what "already there"
means. It imports nothing but the standard library, because the boot's configuration loader calls it.

A symbolic link is treated according to `overwrite`. Without it, the first boot's mode, a link is never
followed: one at a file's path is kept, even when it dangles, and the walk never enters a link to a
directory. With it, the mode `init_config(reset=True)` copies in, a link is followed as a plain copy
follows it: a linked file's target receives the template and the link survives, so a configuration file
linked from a dotfiles repository stays linked, and a linked directory is entered. Every run of
`pipelex init`, `pipelex init config` and `pipelex-agent init` that copies configuration files takes that
mode, since configuration updates are not supported and they always reset; `init_config` copies without
`overwrite` only in its dry run, which counts the missing files and writes nothing. Either way a file appears whole or not at all:
it is written under a temporary name beside the place it lands and renamed into place, so a copy cut short
by a full disk or a killed process leaves no truncated file behind. The kit manifests the fill stamps are
written the same way, through `write_text_atomically`.
"""

import os
import secrets
import shutil
from collections.abc import Callable
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


def _write_atomically(*, destination: Path, write_temporary: Callable[[Path], object]) -> None:
    """Have `write_temporary` write a file under a temporary name, then rename it into place.

    A destination that is a symbolic link is followed, as a plain write follows it: the file lands at the
    link's resolved target and the link survives. A dangling link's target is created when its directory
    exists, and the write raises `FileNotFoundError` when it does not. A caller that must never write through
    a link, as the first boot's fill must not, checks for one before calling.

    The temporary file sits in the directory the file lands in, which must exist. It is created exclusively,
    so nothing already standing at its name is written through, and with the mode a plain write gives a new
    file, the process umask applied. It is removed when the write fails; only a process killed between the
    two steps can leave one behind, under a name no reader looks for.
    """
    landing = Path(os.path.realpath(destination)) if destination.is_symlink() else destination
    temporary = landing.with_name(f".{landing.name}.{secrets.token_hex(8)}.partial")
    os.close(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666))
    try:
        write_temporary(temporary)
        temporary.replace(landing)
    finally:
        temporary.unlink(missing_ok=True)


def copy_file_atomically(*, source: Path, destination: Path) -> None:
    """Copy a file, with the metadata `shutil.copy2` carries, so that it appears whole or not at all.

    It lands at its destination, or at the target of a link standing there, as `_write_atomically` explains.
    """
    _write_atomically(destination=destination, write_temporary=lambda temporary: shutil.copy2(source, temporary))


def write_text_atomically(*, destination: Path, text: str) -> None:
    """Write a text file in UTF-8 so that it appears whole or not at all.

    It lands at its destination, or at the target of a link standing there, as `_write_atomically` explains.
    """
    _write_atomically(destination=destination, write_temporary=lambda temporary: temporary.write_text(text, encoding="utf-8"))


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
    or a directory, is left out at any depth, with everything under it.

    Without `overwrite`, a file the target already holds, a symbolic link included even when it dangles, is
    kept as it is, and a kit directory whose destination `can_fill_directory` refuses, such as a link or a
    file standing there, is left out with everything under it: a directory that holds every file is not
    written at all, and nothing is written through a link. With `overwrite`, every file is written, through
    a link to its target as `copy_file_atomically` does, and a linked directory is entered. With `dry_run`
    nothing is written, and the result says what a real run would copy.

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
                if overwrite or can_fill_directory(directory=dst_item):
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
