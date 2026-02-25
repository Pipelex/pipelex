import typer

from pipelex.cli.commands.build.inputs.app import build_inputs_app
from pipelex.cli.commands.build.output.app import build_output_app
from pipelex.cli.commands.build.pipe_cmd import build_pipe_cmd
from pipelex.cli.commands.build.runner.app import build_runner_app
from pipelex.cli.commands.build.structures_cmd import build_structures_command

build_app = typer.Typer(help="Build working pipelines from natural language requirements", no_args_is_help=True)

# inputs, output, runner are now Typer groups with method/pipe subcommands
build_app.add_typer(build_inputs_app, name="inputs", help="Generate example input JSON for a pipe")
build_app.add_typer(build_output_app, name="output", help="Generate example output representation for a pipe (JSON, Python, or TypeScript)")
build_app.command("pipe", help="Build a Pipelex bundle with one validation/fix loop correcting deterministic issues")(build_pipe_cmd)
build_app.add_typer(build_runner_app, name="runner", help="Build the Python code to run a pipe with the necessary inputs")
build_app.command("structures", help="Generate Python structure files from concept definitions in MTHDS files")(build_structures_command)
