from typing import Literal

from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.tools.templating.jinja2_blueprint import Jinja2Blueprint


class PipeJinja2Blueprint(PipeBlueprint, Jinja2Blueprint):
    type: Literal["PipeJinja2"] = "PipeJinja2"
