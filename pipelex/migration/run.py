"""What a migration run is pointed at — the real registry, the packaged ledgers, and which directories.

`runner.py` answers *how* a file is migrated and takes everything it needs as a parameter, which is
what lets the gates replay the same code over documents that are never written anywhere. This
module answers *what a real run is aimed at*, and it is the only place in the migration package
that reads the machine: the surfaces the package owns, the ledgers shipped beside it, and the two
configuration directories a user actually has.

The separation is deliberate. Every consumer that migrates real files — both `migrate` commands,
and the validation error that reports a plan — must aim at exactly the same set of files, or a
user would be told one thing by their boot and another by their tool.

> **The walk is the global `~/.pipelex/` and the project `.pipelex/`, and nothing else.** A
> `config_dir=` load and `./tests/pipelex_{run_mode}.toml` are outside it. Both are deliberate:
> the first is a caller pointing the loader at a directory of its own choosing, and the second is
> this repository's own test fixture. Neither is a user's configuration, and migrating a
> directory nobody asked about is how a tool earns a reputation for touching things.

> **The walk is each surface's own directory, one level, and nothing else.** Most surfaces live
> directly in a configuration directory; a surface may instead own a subdirectory of it, and then
> that subdirectory is walked one level in the same way. A subdirectory no surface owns —
> `inference/deck/` — is never entered at all.
>
> **A file is claimed by the pair (directory, name), never by its name alone.**
> `.pipelex/inference/backends/pipelex_gateway.toml` is the specimen: its name matches the
> `pipelex-config` tier glob `pipelex_*.toml` exactly, and the directory it sits in is what says
> it belongs to `inference-backend` instead. Depth used to be what protected it, back when no
> surface owned a subdirectory; now the claim rule is.

See `docs/migration-ledger.md` → "Surfaces" and "Applying".
"""

from pathlib import Path

from pipelex.migration.gitignore import ensure_config_dir_gitignore
from pipelex.migration.ledger import packaged_migration_dir
from pipelex.migration.plan import MigrationReport
from pipelex.migration.runner import migrate_directories
from pipelex.migration.surfaces import build_config_surface_registry
from pipelex.system.configuration.config_loader import config_manager


def config_directories_to_migrate() -> list[Path]:
    """The configuration directories a migration run walks, in tier order, each of which exists.

    **The walk is the loader's own set of configuration directories, and this is the sentence that
    says so.** The derivation lives on `ConfigLoader.existing_config_dirs` rather than here, because
    the loader is also what must decide — at boot, on the failure path, before any part of the
    migration package is reachable from it — whether a stale file it just carried forward is one
    this command would reach. One derivation, read from both ends; a second one would let a boot
    warning name a remedy the walk then declines.
    """
    return config_manager.existing_config_dirs


def migrate_config_directories(*, config_dirs: list[Path], dry_run: bool) -> MigrationReport:
    """Replay every surface's shipped ledger over every claimed file in the given directories.

    The registry and the ledger directory are the package's own, which is what makes this the
    real run rather than a gate's rehearsal over synthetic models.

    A real run is also where each walked directory gets the `.gitignore` that keeps the backups
    it is about to write out of the user's `git status` — here rather than in `migrate_directories`
    on purpose, because that function is replayed by the gates over documents that are never
    written anywhere, and a filesystem side effect there would follow them. A user who already had
    a `.pipelex/` before this shipped therefore gets the rule from the very run that would
    otherwise dirty their repository, and not only from a fresh `init`.
    """
    if not dry_run:
        for directory in config_dirs:
            ensure_config_dir_gitignore(directory=directory)
    return migrate_directories(
        registry=build_config_surface_registry(),
        migration_dir=packaged_migration_dir(),
        config_dirs=config_dirs,
        dry_run=dry_run,
    )


def scan_config_surface(*, surface_id: str, config_dirs: list[Path] | None = None) -> MigrationReport:
    """What a `pipelex migrate` would find for one surface, without writing anything.

    The read-only half of the run, and the one a *diagnosis* wants: a configuration validation
    error is raised against the merged configuration and carries no provenance — it says a key is
    wrong, not which of the files that were merged put it there — so the way to answer "is this
    machine's configuration simply stale?" is to look at the files themselves.

    Scoped to the surface whose model refused, and to the same directories a real migration walks.
    Both halves matter: reporting a pending `telemetry.toml` migration underneath a
    `pipelex.toml` error would answer a question nobody asked, and scanning a directory the
    `migrate` command would not touch would offer a remedy that then does nothing.

    The scoping is a filter on the *answer*, and the full registry still decides which surface
    owns which file — see `migrate_directories`. Handing it a one-surface registry instead looks
    equivalent and is not: `pipelex_service.toml` is another surface's base file *and* a match for
    `pipelex-config`'s `pipelex_*.toml`, and with that other surface absent the glob wins.

    Args:
        surface_id: The surface to answer for.
        config_dirs: The directories to look in. The default — the ones a real migration walks —
            is what a boot failure wants, since it has no directory of its own to speak of. A
            caller that was pointed at one directory and is reporting on *that* passes it here
            rather than inheriting the walk: `pipelex doctor --global` inspects a file in
            `~/.pipelex/` and must not answer with a finding about the project directory beside it.
    """
    return migrate_directories(
        registry=build_config_surface_registry(),
        migration_dir=packaged_migration_dir(),
        config_dirs=config_dirs if config_dirs is not None else config_directories_to_migrate(),
        dry_run=True,
        only_surface_id=surface_id,
    )
