# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Dict, Optional, Self, Set

import shortuuid
from pydantic import model_validator
from typing_extensions import override

from pipelex import log
from pipelex.config import get_config
from pipelex.core.pipe import PipeAbstract, update_job_metadata_for_pipe
from pipelex.core.pipe_output import PipeOutput
from pipelex.core.pipe_run_params import PipeRunParams
from pipelex.core.working_memory import WorkingMemory
from pipelex.exceptions import PipeConditionError, PipeDefinitionError, PipeExecutionError, PipeInputError, WorkingMemoryStuffNotFoundError
from pipelex.hub import get_pipe_router
from pipelex.job_history import job_history
from pipelex.job_metadata import JobCategory, JobMetadata
from pipelex.pipe_controllers.pipe_condition_details import PipeConditionDetails
from pipelex.pipe_operators.pipe_jinja2 import PipeJinja2
from pipelex.tools.utils.validation_utils import has_exactly_one_among_attributes_from_list


class PipeCondition(PipeAbstract):
    expression_jinja2: Optional[str]
    expression: Optional[str]
    pipe_map: Dict[str, str]
    default_pipe_code: Optional[str] = None
    add_alias_from_expression_to: Optional[str] = None

    @model_validator(mode="after")
    def validate_expression(self) -> Self:
        if not has_exactly_one_among_attributes_from_list(self, attributes_list=["expression_jinja2", "expression"]):
            raise PipeDefinitionError("PipeCondition should have exactly one of expression_jinja2 or expression")
        return self

    @property
    def applied_expression_jinja2(self) -> str:
        if self.expression_jinja2:
            return self.expression_jinja2
        elif self.expression:
            return "{{ " + self.expression + " }}"
        else:
            raise PipeExecutionError("No expression or expression_jinja2 provided")

    def _make_pipe_condition_details(self, evaluated_expression: str, chosen_pipe_code: str) -> PipeConditionDetails:
        return PipeConditionDetails(
            code=shortuuid.uuid()[:5],
            test_expression=self.expression or self.applied_expression_jinja2,
            pipe_map=self.pipe_map,
            default_pipe_code=self.default_pipe_code,
            evaluated_expression=evaluated_expression,
            chosen_pipe_code=chosen_pipe_code,
        )

    @override
    def pipe_dependencies(self) -> Set[str]:
        pipe_codes = list(self.pipe_map.values())
        if self.default_pipe_code:
            pipe_codes.append(self.default_pipe_code)
        return set(pipe_codes)

    @override
    @update_job_metadata_for_pipe
    async def run_pipe(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        pipe_code: str,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: Optional[str] = None,
    ) -> PipeOutput:
        log.dev(f"{self.class_name} generating a '{self.output_concept_code}'")

        # TODO: restore pipe_stack feature
        # pipe_run_params.push_pipe_code(pipe_code=pipe_code)

        pipe_jinja2 = PipeJinja2(
            domain=self.domain,
            jinja2=self.applied_expression_jinja2,
        )
        jinja2_job_metadata = job_metadata.copy_with_update(
            updated_metadata=JobMetadata(
                session_id=get_config().session_id,
                job_category=JobCategory.JINJA2_JOB,
            )
        )
        log.debug(f"Jinja2 expression: {self.applied_expression_jinja2}")
        evaluated_expression = (
            await pipe_jinja2.run_pipe(
                pipe_code=PipeJinja2.adhoc_pipe_code,
                job_metadata=jinja2_job_metadata,
                working_memory=working_memory,
                pipe_run_params=pipe_run_params,
            )
        ).rendered_text.strip()

        if not evaluated_expression or evaluated_expression == "None":
            error_msg = f"Conditional expression returned an empty string in pipe {pipe_code}:"
            error_msg += f"\n\nExpression: {self.applied_expression_jinja2}"
            raise PipeConditionError(error_msg)
        log.debug(f"evaluated_expression: '{evaluated_expression}'")

        log.debug(f"add_alias: {evaluated_expression} -> {self.add_alias_from_expression_to}")
        if self.add_alias_from_expression_to:
            working_memory.add_alias(
                alias=evaluated_expression,
                target=self.add_alias_from_expression_to,
            )

        chosen_pipe_code = self.pipe_map.get(evaluated_expression, self.default_pipe_code)
        if not chosen_pipe_code:
            error_msg = f"No pipe code found for evaluated expression '{evaluated_expression}' in pipe {pipe_code}:"
            error_msg += f"\n\nExpression: {self.applied_expression_jinja2}"
            error_msg += f"\n\nPipe map: {self.pipe_map}"
            raise PipeConditionError(error_msg)

        condition_details = self._make_pipe_condition_details(
            evaluated_expression=evaluated_expression,
            chosen_pipe_code=chosen_pipe_code,
        )
        required_variables = pipe_jinja2.required_variables()
        log.debug(required_variables, title=f"Required variables for PipeCondition '{pipe_code}'")
        required_stuff_names = set([required_variable for required_variable in required_variables if not required_variable.startswith("_")])
        try:
            required_stuffs = working_memory.get_stuffs(names=required_stuff_names)
        except WorkingMemoryStuffNotFoundError as exc:
            error_details = f"PipeCondition '{pipe_code}', stack: {pipe_run_params.pipe_stack}, required_variables: {required_variables}"
            raise PipeInputError(f"Some required stuff(s) not found - {error_details}") from exc

        for required_stuff in required_stuffs:
            job_history.add_condition_step(
                from_stuff=required_stuff,
                to_condition=condition_details,
                condition_expression=self.expression or self.applied_expression_jinja2,
                pipe_stack=pipe_run_params.pipe_stack,
                comment="PipeCondition required for condition",
            )

        log.debug(f"Chosen pipe: {chosen_pipe_code}")
        pipe_output: PipeOutput = await get_pipe_router().run_pipe_code(
            pipe_code=chosen_pipe_code,
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=pipe_run_params,
            output_name=output_name,
        )
        job_history.add_choice_step(
            from_condition=condition_details,
            to_stuff=pipe_output.main_stuff,
            pipe_stack=pipe_run_params.pipe_stack,
            comment="PipeCondition chosen pipe",
        )
        return pipe_output
