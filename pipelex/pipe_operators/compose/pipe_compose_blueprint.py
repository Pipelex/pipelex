from typing import Literal

from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.tools.templating.jinja2_blueprint import Jinja2Blueprint


class PipeComposeBlueprint(PipeBlueprint, Jinja2Blueprint):
    type: Literal["PipeCompose"] = "PipeCompose"
    category: Literal["PipeOperator"] = "PipeOperator"
