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

> **The walk is not recursive.** A surface's tier files sit beside its base file; a subdirectory
> under a configuration directory holds a different kind of thing — `inference/backends/`,
> `deck/` — whose files are not configuration surfaces even when their names would match a tier
> glob. `.pipelex/inference/backends/pipelex_gateway.toml` is the specimen: it matches the
> `pipelex-config` tier glob `pipelex_*.toml` and must never be claimed by it.

See `docs/migration-ledger.md` → "Surfaces" and "Applying".
"""

from pathlib import Path

from pipelex.migration.ledger import packaged_migration_dir
from pipelex.migration.plan import MigrationReport
from pipelex.migration.runner import migrate_directories
from pipelex.migration.surfaces import build_config_surface_registry
from pipelex.system.configuration.config_loader import config_manager


def config_directories_to_migrate() -> list[Path]:
    """The configuration directories a migration run walks, in tier order, each of which exists.

    The global directory comes first and the project one second, which is the order the loader
    merges them in and therefore the order a report reads most naturally. A machine with only one
    of them is an ordinary machine; a project directory that *is* the global one — a project rooted
    at the home directory — is walked once rather than twice.
    """
    directories: list[Path] = []
    global_dir = config_manager.global_config_dir
    if global_dir.is_dir():
        directories.append(global_dir)
    project_dir = config_manager.project_config_dir
    if project_dir is not None and project_dir.resolve() not in {directory.resolve() for directory in directories}:
        directories.append(project_dir)
    return directories


def migrate_config_directories(*, config_dirs: list[Path], dry_run: bool) -> MigrationReport:
    """Replay every surface's shipped ledger over every claimed file in the given directories.

    The registry and the ledger directory are the package's own, which is what makes this the
    real run rather than a gate's rehearsal over synthetic models.
    """
    return migrate_directories(
        registry=build_config_surface_registry(),
        migration_dir=packaged_migration_dir(),
        config_dirs=config_dirs,
        dry_run=dry_run,
    )


def scan_config_surface(*, surface_id: str) -> MigrationReport:
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
    """
    return migrate_directories(
        registry=build_config_surface_registry(),
        migration_dir=packaged_migration_dir(),
        config_dirs=config_directories_to_migrate(),
        dry_run=True,
        only_surface_id=surface_id,
    )
