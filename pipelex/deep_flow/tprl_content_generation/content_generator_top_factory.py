from datetime import timedelta

from temporalio.common import RetryPolicy

from pipelex.config import get_config
from pipelex.deep_flow.temporal_manager import TemporalWorkerEnvironment
from pipelex.deep_flow.tprl_content_generation.content_generator_top import ContentGeneratorTop


class ContentGeneratorTopFactory:
    @classmethod
    def make_content_generator_top(
        cls,
        workflow_execution_timeout: timedelta | None = None,
        retry_policy: RetryPolicy | None = None,
        task_queue: str | None = None,
        worker_environment: TemporalWorkerEnvironment = TemporalWorkerEnvironment.EXTERNAL,
    ) -> ContentGeneratorTop:
        """This factory is only passing your settings or using defaults from pipelex.deep_flow's config.
        Don't hesitate to create your own factory or your own TopCrafter according to your needs and context.
        """
        worker_config = get_config().deep_flow.worker_config
        return ContentGeneratorTop(
            task_queue=task_queue or worker_config.task_queue,
            workflow_execution_timeout=workflow_execution_timeout or worker_config.workflow_execution_timeout,
            retry_policy=retry_policy or worker_config.retry_policy_config.make_retry_policy(),
            should_auto_connect_temporal=True,
            worker_environment=worker_environment,
        )

    # @classmethod
    # async def make_content_generator_top_connected_to_temporal(
    #     cls,
    #     task_queue: Optional[str] = None,
    #     workflow_execution_timeout: Optional[timedelta] = None,
    #     retry_policy: Optional[RetryPolicy] = None,
    #     worker_environment: TemporalWorkerEnvironment = TemporalWorkerEnvironment.EXTERNAL,
    # ) -> TopCrafterTemporal:
    #     """
    #     This factory uses above make_top_crafter but then also makes sure that the temporal client is connected.
    #     """
    #     top_crafter_temporal = cls.make_top_crafter_temporal(
    #         task_queue=task_queue,
    #         workflow_execution_timeout=workflow_execution_timeout,
    #         retry_policy=retry_policy,
    #         worker_environment=worker_environment,
    #     )
    #     await top_crafter_temporal.temporal_client()
    #     return top_crafter_temporal
