from temporalio import workflow
from temporalio.exceptions import ActivityError, ApplicationError
from typing_extensions import override

from pipelex import log
from pipelex.base_exceptions import PipelexError
from pipelex.cogt.content_generation.assignment_models import ObjectAssignment, TextThenObjectAssignment

with workflow.unsafe.imports_passed_through():
    from pydantic import BaseModel

    from pipelex import log
    from pipelex.cogt.content_generation.assignment_models import (
        ObjectAssignment,
        TextThenObjectAssignment,
    )
    from pipelex.config import get_config
    from pipelex.deep_flow.log_temporal import workflow_log
    from pipelex.deep_flow.tprl.temporal_error import TemporalError
    from pipelex.deep_flow.tprl.workflow_caller import WorkflowClass
    from pipelex.deep_flow.tprl_content_generation.act_llm_generate import (
        act_llm_gen_object,
        act_llm_gen_object_list,
        act_llm_gen_text,
    )


@workflow.defn(name="wf_make_object")
class WfMakeObject(WorkflowClass[ObjectAssignment, BaseModel]):
    @override
    @workflow.run
    async def run(
        self,
        workflow_arg: ObjectAssignment,
    ) -> BaseModel:
        workflow_log.debug("Workflow start")
        worker_config = get_config().deep_flow.worker_config
        try:
            obj = await workflow.start_activity(  # pyright: ignore[reportUnknownMemberType, reportAssignmentType]
                activity=act_llm_gen_object,
                arg=workflow_arg,
                start_to_close_timeout=worker_config.workflow_execution_timeout,
                retry_policy=worker_config.retry_policy,
            )
        except ActivityError as exc:
            log.error(f"ActivityError caused by: {exc.cause}")
            if isinstance(exc.cause, ApplicationError):
                raise TemporalError.from_app_error(exc=exc.cause) from exc
            raise
        workflow_log.debug("Workflow complete")
        return obj


@workflow.defn(name="wf_make_object_list")
class WfMakeObjectList(WorkflowClass[ObjectAssignment, list[BaseModel]]):
    @override
    @workflow.run
    async def run(
        self,
        workflow_arg: ObjectAssignment,
    ) -> list[BaseModel]:
        workflow_log.debug("Workflow start")
        worker_config = get_config().deep_flow.worker_config
        try:
            obj_list: list[BaseModel] = await workflow.start_activity(  # pyright: ignore[reportUnknownMemberType, reportAssignmentType]
                activity=act_llm_gen_object_list,
                arg=workflow_arg,
                start_to_close_timeout=worker_config.workflow_execution_timeout,
                retry_policy=worker_config.retry_policy,
            )
        except ActivityError as exc:
            log.error(f"ActivityError caused by: {exc.cause}")
            if isinstance(exc.cause, ApplicationError):
                raise TemporalError.from_app_error(exc=exc.cause) from exc
            raise
        workflow_log.debug("Workflow complete")
        return obj_list


@workflow.defn(name="wf_make_text_then_object")
class WfMakeTextThenObject(WorkflowClass[TextThenObjectAssignment, BaseModel]):
    @override
    @workflow.run
    async def run(
        self,
        workflow_arg: TextThenObjectAssignment,
    ) -> BaseModel:
        workflow_log.debug("Workflow start")
        worker_config = get_config().deep_flow.worker_config
        try:
            preliminary_text = await workflow.start_activity(  # pyright: ignore[reportUnknownMemberType, reportAssignmentType]
                activity=act_llm_gen_text,
                arg=workflow_arg.llm_assignment_for_text,
                start_to_close_timeout=worker_config.workflow_execution_timeout,
                retry_policy=worker_config.retry_policy,
            )

            log.dev(f"preliminary_text: {preliminary_text}")

            fup_llm_assignment = await workflow_arg.llm_assignment_factory_to_object.make_llm_assignment(
                preliminary_text=preliminary_text,
            )

            fup_obj_assignment = ObjectAssignment(
                llm_assignment_for_object=fup_llm_assignment,
                object_class_name=workflow_arg.object_class_name,
            )

            obj: BaseModel = await workflow.start_activity(  # pyright: ignore[reportUnknownMemberType, reportAssignmentType]
                activity=act_llm_gen_object,
                arg=fup_obj_assignment,
                start_to_close_timeout=worker_config.workflow_execution_timeout,
                retry_policy=worker_config.retry_policy,
            )
        except PipelexError as exc:
            raise TemporalError.from_message_exception(exc) from exc
        except ActivityError as exc:
            log.error(f"ActivityError caused by: {exc.cause}")
            if isinstance(exc.cause, ApplicationError):
                raise TemporalError.from_app_error(exc=exc.cause) from exc
            raise
        workflow_log.debug("Workflow complete")
        return obj


@workflow.defn(name="wf_make_text_then_object_list")
class WfMakeTextThenObjectList(WorkflowClass[TextThenObjectAssignment, list[BaseModel]]):
    @override
    @workflow.run
    async def run(
        self,
        workflow_arg: TextThenObjectAssignment,
    ) -> list[BaseModel]:
        workflow_log.debug("Workflow start")
        worker_config = get_config().deep_flow.worker_config
        try:
            preliminary_text = await workflow.start_activity(  # pyright: ignore[reportUnknownMemberType, reportAssignmentType]
                activity=act_llm_gen_text,
                arg=workflow_arg.llm_assignment_for_text,
                start_to_close_timeout=worker_config.workflow_execution_timeout,
                retry_policy=worker_config.retry_policy,
            )

            workflow_log.debug(f"preliminary_text: {preliminary_text}")

            llm_assignment_for_object = await workflow_arg.llm_assignment_factory_to_object.make_llm_assignment(
                preliminary_text=preliminary_text,
            )

            object_assignment = ObjectAssignment(
                object_class_name=workflow_arg.object_class_name,
                llm_assignment_for_object=llm_assignment_for_object,
            )

            obj_list: list[BaseModel] = await workflow.start_activity(  # pyright: ignore[reportUnknownMemberType, reportAssignmentType]
                activity=act_llm_gen_object_list,
                arg=object_assignment,
                start_to_close_timeout=worker_config.workflow_execution_timeout,
                retry_policy=worker_config.retry_policy,
            )
        except PipelexError as exc:
            raise TemporalError.from_message_exception(exc) from exc
        except ActivityError as exc:
            log.error(f"ActivityError caused by: {exc.cause}")
            if isinstance(exc.cause, ApplicationError):
                raise TemporalError.from_app_error(exc=exc.cause) from exc
            raise

        workflow_log.debug(f"obj_list: {obj_list}")
        workflow_log.debug("Workflow complete")
        return obj_list
