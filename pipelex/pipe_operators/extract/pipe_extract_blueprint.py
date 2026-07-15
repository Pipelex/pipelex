from typing import Literal

from typing_extensions import override

from pipelex.cogt.extract.extract_setting import ExtractModelChoice
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.core.pipes.variable_multiplicity import parse_concept_with_multiplicity
from pipelex.core.qualified_ref import QualifiedRef


class PipeExtractBlueprint(PipeBlueprint):
    type: Literal["PipeExtract"] = "PipeExtract"
    pipe_category: Literal["PipeOperator"] = "PipeOperator"
    model: ExtractModelChoice | None = None
    max_page_images: int | None = None
    page_image_captions: bool | None = None
    page_views: bool | None = None
    page_views_dpi: int | None = None
    render_js: bool | None = None
    include_raw_html: bool | None = None

    @override
    def validate_inputs(self):
        nb_inputs = self.nb_inputs
        msg = (
            "Exactly one input must be provided for the PipeExtract, and it must be a Document or an Image or a concept that refines one of them."
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
        # PipeExtract mechanically produces native Pages: the declared output is exactly a
        # variable-length list of `native.Page` — no refinement of it, since an output declaration is
        # a promise to downstream consumers and the operator cannot make its pages any more specific.
        # This compares the *parsed* ref and multiplicity rather than the authoring spelling "Page[]",
        # so it still holds once crate normalization qualifies the ref to "native.Page[]". The
        # authoritative check on the resolved concept lives in PipeExtract.validate_output_with_library.
        output_parse_result = parse_concept_with_multiplicity(self.output)
        output_ref = QualifiedRef.parse(output_parse_result.concept_ref_or_code)
        is_native_page = output_ref.local_code == NativeConceptCode.PAGE and (
            output_ref.domain_path is None or SpecialDomain.is_native(domain_code=output_ref.domain_path)
        )
        if not is_native_page or output_parse_result.multiplicity is not True:
            msg = (
                f"PipeExtract output must be '{NativeConceptCode.PAGE.as_output_multiple_indeterminate}' — "
                f"a variable-length list of native Pages — but is '{self.output}'."
            )
            raise ValueError(msg)
