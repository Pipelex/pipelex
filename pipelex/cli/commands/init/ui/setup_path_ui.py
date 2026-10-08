"""The question `pipelex init` asks first: where should runs execute?"""

from rich.console import Console, Group
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from pipelex.cli.commands.init.setup_path import SetupPath

#: The question, as the panel titles it.
SETUP_PATH_QUESTION = "Where should your runs execute?"

# The options in the order they are listed and numbered, the default first.
_SETUP_PATH_OPTIONS: tuple[tuple[SetupPath, str], ...] = (
    (SetupPath.HOSTED, "On the hosted Pipelex API, with a Pipelex API key"),
    (SetupPath.LOCAL, "On this machine, with your own provider keys"),
)


def _option_number(*, setup_path: SetupPath) -> str:
    for index, (option, _) in enumerate(_SETUP_PATH_OPTIONS, start=1):
        if option == setup_path:
            return str(index)
    msg = f"No option lists the setup path {setup_path!r}"
    raise ValueError(msg)


def build_setup_path_panel(*, default: SetupPath) -> Panel:
    """The two places a run can execute, numbered, the default marked."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="bold cyan", justify="right", width=4)
    table.add_column(style="bold")
    table.add_column(style="dim")
    for index, (setup_path, label) in enumerate(_SETUP_PATH_OPTIONS, start=1):
        table.add_row(f"[{index}]", label, "default" if setup_path == default else "")

    description = Text(
        "The hosted API runs your methods with no provider account of your own: you sign in once and get a Pipelex API key.\n"
        "This machine runs them on the AI providers you choose, with your own keys or local models.\n"
        "Either way, a single run can still go the other way with --hosted or --local.",
        style="dim",
    )
    return Panel(
        Group(description, Text(""), table),
        title=f"[bold yellow]{SETUP_PATH_QUESTION}[/bold yellow]",
        border_style="yellow",
        padding=(1, 2),
    )


def prompt_setup_path(*, console: Console, default: SetupPath = SetupPath.HOSTED) -> SetupPath:
    """Ask where runs execute, Enter (an empty answer) taking the default.

    Accepts the option's number, or its name (`hosted`, `local`). Asks again on anything else.
    """
    console.print(build_setup_path_panel(default=default))
    by_answer: dict[str, SetupPath] = {}
    for index, (setup_path, _) in enumerate(_SETUP_PATH_OPTIONS, start=1):
        by_answer[str(index)] = setup_path
        by_answer[setup_path.value] = setup_path
    while True:
        answer = Prompt.ask("[bold]Enter your choice[/bold]", default=_option_number(setup_path=default), console=console)
        if not answer.strip():
            return default
        chosen = by_answer.get(answer.strip().lower())
        if chosen is not None:
            return chosen
        console.print(f"[red]Invalid choice: {escape(repr(answer))}.[/red] Enter 1 for the hosted Pipelex API or 2 for this machine.\n")
