from typing import Literal

from typing_extensions import override

from pipelex.cogt.search.search_depth import SearchDepth
from pipelex.cogt.search.search_setting import SearchModelChoice
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint


class PipeSearchBlueprint(PipeBlueprint):
    type: Literal["PipeSearch"] = "PipeSearch"
    pipe_category: Literal["PipeOperator"] = "PipeOperator"
    model: SearchModelChoice | None = None
    depth: SearchDepth | None = None
    include_images: bool | None = None
    max_results: int | None = None
    from_date: str | None = None
    to_date: str | None = None
    include_domains: list[str] | None = None
    exclude_domains: list[str] | None = None

    @override
    def validate_inputs(self):
        nb_inputs = self.nb_inputs
        if self.inputs is None or nb_inputs != 1:
            msg = f"Exactly one input must be provided for PipeSearch, and it must be a Text concept. {nb_inputs} inputs were provided."
            raise ValueError(msg)
