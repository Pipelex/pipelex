import typer

from pipelex.cli.commands.build.inputs_cmd import generate_inputs_cmd
from pipelex.cli.commands.build.pipe_cmd import build_pipe_cmd
from pipelex.cli.commands.build.runner_cmd import prepare_runner_cmd
from pipelex.cli.commands.build.structures_cmd import build_structures_command

build_app = typer.Typer(help="Build working pipelines from natural language requirements", no_args_is_help=True)

# Register commands explicitly
build_app.command("inputs", help="Generate example input JSON for a pipe")(generate_inputs_cmd)
build_app.command("pipe", help="Build a Pipelex bundle with one validation/fix loop correcting deterministic issues")(build_pipe_cmd)
build_app.command("runner", help="Build the Python code to run a pipe with the necessary inputs")(prepare_runner_cmd)
build_app.command("structures", help="Generate Python structure files from concept definitions in PLX files")(build_structures_command)
