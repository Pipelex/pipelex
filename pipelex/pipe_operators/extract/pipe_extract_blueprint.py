from typing import Literal

from typing_extensions import override

from pipelex.cogt.extract.extract_setting import ExtractModelChoice
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint


class PipeExtractBlueprint(PipeBlueprint):
    type: Literal["PipeExtract"] = "PipeExtract"
    pipe_category: Literal["PipeOperator"] = "PipeOperator"
    model: ExtractModelChoice | None = None
    max_page_images: int | None = None
    page_image_captions: bool | None = None
    page_views: bool | None = None
    page_views_dpi: int | None = None

    @override
    def validate_inputs(self):
        nb_inputs = self.nb_inputs
        msg = (
            "Exactly one input must be provided for the PipeExtract, and it must be a pdf or an image or a concept that refines one of them."
            f"{nb_inputs} inputs were provided."
        )
        if self.inputs is None:
            raise ValueError(msg)
        if nb_inputs > 1:
            msg = f"Too many inputs provided for PipeExtract: {self.input_names}. Only one input is allowed."
            raise ValueError(msg)
        if nb_inputs < 1:
            msg = f"Missing input provided for PipeExtract: {self.input_names}. Only one input is allowed."
            raise ValueError(msg)

    @override
    def validate_output(self):
        if self.output != "Page[]":
            msg = f"PipeExtract output should be a 'native.Page[]' concept, but is {self.output}"
            raise ValueError(msg)
