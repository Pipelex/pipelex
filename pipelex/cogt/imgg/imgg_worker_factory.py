# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Any, Dict, Optional

from pipelex.cogt.exceptions import CogtError, MissingDependencyError
from pipelex.cogt.imgg.imgg_engine_abstract import ImggEngineAbstract
from pipelex.cogt.imgg.imgg_worker_abstract import ImggWorkerAbstract
from pipelex.cogt.imgg.imgg_worker_models import ImggSDKHandle
from pipelex.cogt.inference.inference_report_delegate import InferenceReportDelegate
from pipelex.hub import get_secret
from pipelex.tools.secrets.secrets_errors import SecretNotFoundError


class FalCredentialsError(CogtError):
    pass


class ImggWorkerFactory:
    def __init__(self) -> None:
        self.imgg_sdk_instances: Dict[ImggSDKHandle, Any] = {}

    def get_imgg_sdk_instance(self, imgg_sdk_handle: ImggSDKHandle) -> Optional[Any]:
        imgg_sdk_instance = self.imgg_sdk_instances.get(imgg_sdk_handle)
        return imgg_sdk_instance

    def set_imgg_sdk_instance(self, imgg_sdk_handle: ImggSDKHandle, imgg_sdk_instance: Any) -> Any:
        self.imgg_sdk_instances[imgg_sdk_handle] = imgg_sdk_instance
        return imgg_sdk_instance

    def make_imgg_worker(
        self,
        imgg_engine: ImggEngineAbstract,
        report_delegate: Optional[InferenceReportDelegate] = None,
    ) -> ImggWorkerAbstract:
        imgg_worker: ImggWorkerAbstract
        try:
            import fal_client  # noqa: F401
        except ImportError as exc:
            raise MissingDependencyError("fal-client", "fal", "The fal-client SDK is required to use FAL models (generation of images).") from exc

        from pipelex.cogt.fal.fal_engine import FalEngine

        if isinstance(imgg_engine, FalEngine):
            fal_engine = imgg_engine
            imgg_sdk_handle = ImggSDKHandle.FAL_ASYNC
            try:
                fal_api_key = get_secret(secret_id="FAL_API_KEY")
            except SecretNotFoundError as exc:
                raise FalCredentialsError("FAL_API_KEY not found") from exc

            from fal_client import AsyncClient

            from pipelex.cogt.fal.fal_worker import FalWorker

            imgg_sdk_instance = self.get_imgg_sdk_instance(imgg_sdk_handle=imgg_sdk_handle) or self.set_imgg_sdk_instance(
                imgg_sdk_handle=imgg_sdk_handle,
                imgg_sdk_instance=AsyncClient(key=fal_api_key),
            )

            imgg_worker = FalWorker(
                sdk_instance=imgg_sdk_instance,
                fal_engine=fal_engine,
                report_delegate=report_delegate,
            )
        else:
            raise ValueError(f"Unsupported imgg_engine: {imgg_engine}")

        return imgg_worker
