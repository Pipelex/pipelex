from datetime import timedelta

from citadel.config_citadel import get_config
from deep_flow.tprl_content_generation.content_generator_child import ContentGeneratorChild
from temporalio.common import RetryPolicy


class ContentGeneratorChildFactory:
    @classmethod
    def make_content_generator_child(
        cls,
        task_queue: str | None = None,
        workflow_execution_timeout: timedelta | None = None,
        retry_policy: RetryPolicy | None = None,
        run_timeout: timedelta | None = None,
        task_timeout: timedelta | None = None,
        start_delay: timedelta | None = None,
        rpc_timeout: timedelta | None = None,
    ) -> ContentGeneratorChild:
        config = get_config().deep_flow.worker_config

        return ContentGeneratorChild(
            task_queue=task_queue or config.task_queue,
            workflow_execution_timeout=workflow_execution_timeout or config.workflow_execution_timeout,
            retry_policy=retry_policy or config.retry_policy,
            run_timeout=run_timeout or config.run_timeout,
            task_timeout=task_timeout or config.task_timeout,
            start_delay=start_delay or config.start_delay,
            rpc_timeout=rpc_timeout or config.rpc_timeout,
        )
