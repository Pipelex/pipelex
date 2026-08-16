import typer
from rich import box
from rich.table import Table

from pipelex.interpreter_plugins.builtins import BUILTIN_PLUGINS, CORE_UNCONDITIONAL_PLUGIN_NAMES, ENTRY_POINT_GROUPS
from pipelex.plugins.discovery import build_registrar
from pipelex.runtime_hub import get_console
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.configuration.configs import PipelexConfig

plugins_app = typer.Typer(no_args_is_help=True)


@plugins_app.command(name="list", help="List discovered plugins (built-in and external), what each registered, and denylist state")
def plugins_list_command() -> None:
    """Discover plugins and print what each contributed.

    Runs the pure ``build_registrar`` against the loaded config — the same
    discovery the runtime uses at boot — so the listing reflects exactly what
    would be wired in (and what the ``plugins.disabled`` denylist turns off).
    """
    console = get_console()
    config = config_manager.load_config_validated(config_cls=PipelexConfig)
    registrar = build_registrar(
        config=config,
        builtin_plugins=BUILTIN_PLUGINS,
        core_unconditional_plugin_names=CORE_UNCONDITIONAL_PLUGIN_NAMES,
        entry_point_groups=ENTRY_POINT_GROUPS,
    )

    table = Table(title="Pipelex plugins", show_header=True, header_style="bold cyan", box=box.SQUARE_DOUBLE_HEAD)
    table.add_column("Name", style="green")
    table.add_column("Origin", style="blue")
    table.add_column("Group", style="magenta")
    table.add_column("Status", style="yellow")
    table.add_column("API", justify="right")
    table.add_column("Contributions")

    for discovery in registrar.discoveries:
        contributions = "\n".join(discovery.contributions) if discovery.contributions else (discovery.detail or "—")
        targets_api = str(discovery.targets_api) if discovery.targets_api is not None else "—"
        # Built-ins arrive under no entry-point group — they are filed by layer in-tree instead.
        group = discovery.group or "—"
        table.add_row(discovery.name, discovery.origin, group, discovery.status, targets_api, contributions)

    console.print(table)
